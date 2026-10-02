#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise the actual closed dispatcher without a CPU or network listener."""
import ast
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location('mailbox', ROOT/'tools/spike_nuttx_mailbox.py')
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.base, self.marker = 0x20021000, 0x08061234
        self.memory = bytearray(mb.SIZE)
        struct.pack_into('<II', self.memory, 0, mb.MAGIC, 1)
        struct.pack_into('<I', self.memory, 60, 2)
        self.marker_value, self.writes, self.sleeps, self.paused = 1, [], [], False
        self.bus = SimpleNamespace(ReadDoubleWord=self.read, WriteDoubleWord=self.write,
                                   ReadBytes=lambda address,size:self.memory[address-self.base:address-self.base+size])
        self.machine = SimpleNamespace(SystemBus=self.bus, ObtainPausedState=self.pause)
        tree = ast.parse((ROOT/'scripts/spike-state-server.py').read_text())
        dispatch = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_dispatch')
        class Watch:
            def __init__(self): self.elapsed = 0
            @property
            def ElapsedMilliseconds(self):
                # Simulate expensive polling: iteration counts are insufficient.
                self.elapsed += 500
                return self.elapsed
        env = {'monitor': SimpleNamespace(Machine=self.machine), 'spike_nuttx_mailbox': mb,
               'Thread': SimpleNamespace(Sleep=self.sleeps.append),
               'Stopwatch': SimpleNamespace(StartNew=Watch)}
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), 'actual-dispatch', 'exec'), env)
        self.dispatch = env['_dispatch']
        self.config = {'identity': {'board':'spike-prime','firmware':'brickwright-nuttx','transport':'none'},
                       'paths': {}, 'programMailbox': self.base, 'programStorageAbiAddress': self.marker}

    def read(self, address):
        return self.marker_value if address == self.marker else struct.unpack_from('<I', self.memory, address-self.base)[0]

    def write(self, address, value):
        assert self.paused
        self.writes.append((address, value))
        struct.pack_into('<I', self.memory, address-self.base, value)

    def pause(self, unused):
        self.paused = True
        owner = self
        class Paused:
            def Dispose(self): owner.paused = False
        return Paused()

    def command(self, op=8, deferred=True, ident=42):
        return {'command':'nuttx.program.storage.submit' if deferred else 'nuttx.program.packet',
                'arguments':{'bytes':list(struct.pack('<4BI', 0x70, 1, op, 0, ident))}}

    def test_storage_submission_returns_without_ack_wait(self):
        self.dispatch(self.config, self.command())
        self.assertEqual(self.read(self.base+8), 2)
        self.assertEqual(self.read(self.base+36), 0)
        self.assertFalse(self.paused)
        self.assertEqual(self.sleeps, [])
        before = list(self.writes)
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.dispatch(self.config, self.command())
        self.assertEqual(self.writes, before)

    def test_storage_only_and_capability_gate_before_writes(self):
        for op in (3, 4, 5, 6):
            with self.assertRaises(ValueError): self.dispatch(self.config, self.command(op))
        self.marker_value = 0
        with self.assertRaisesRegex(ValueError, 'not supported'):
            self.dispatch(self.config, self.command())
        self.assertEqual(self.writes, [])

    def test_legacy_polling_uses_wall_deadline(self):
        with self.assertRaisesRegex(ValueError, 'did not acknowledge'):
            self.dispatch(self.config, self.command(deferred=False))
        self.assertEqual(len(self.sleeps), 2)
        self.assertFalse(self.paused)


if __name__ == '__main__': unittest.main()
