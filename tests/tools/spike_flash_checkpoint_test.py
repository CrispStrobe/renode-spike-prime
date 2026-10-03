#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise the actual checkpoint coordinator without an emulator/listener."""
import ast
import json
import os
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
from unittest.mock import patch
from threading import RLock
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_FlashCheckpoint')
        env = dict(os=os, json=json, RLock=RLock, _CHECKPOINT_INTEGERS=(int,))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-checkpoint', 'exec'), env)
        self.kind = env['_FlashCheckpoint']
        # Coordinator bounds tested separately; small bytes avoid32MiB per unit case.
        self.kind.SIZE = 8
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jobs = []
        self.clock = 0
        self.reply = [0x71, 1, 8, 1, 23, 0, 0, 0] + [0] * 12
        self.exports = 0
        self.on_sleep = lambda: None
        def export():
            self.exports += 1
            return b'flashdata'
        def sleep():
            self.clock += 0.25
            self.on_sleep()
        self.checkpoint = self.kind(self.tmp.name, 'a' * 64, export,
                                   lambda seq: self.reply, self.jobs.append,
                                   sleep, lambda: self.clock)
        self.checkpoint.SIZE = 9

    def receipt(self, **changes):
        data = dict(schema=1, imageSha256='a' * 64, requestSeq=2, programId=23, status='durable')
        data.update(changes)
        Path(self.tmp.name, 'receipt.json').write_text(json.dumps(data))

    def test_ack_alone_never_means_durable_and_export_is_async(self):
        self.checkpoint.begin(2, 23)
        self.assertTrue(self.checkpoint.busy())
        self.assertEqual(self.exports, 0)
        self.assertFalse(Path(self.tmp.name, 'export.json').exists())
        self.on_sleep = self.receipt
        self.jobs[0]()
        self.assertEqual(self.exports, 1)
        self.assertEqual(Path(self.tmp.name, 'flash.bin').read_bytes(), b'flashdata')
        metadata = json.loads(Path(self.tmp.name, 'export.json').read_text())
        self.assertEqual(metadata, dict(schema=1, imageSha256='a' * 64, requestSeq=2,
                                       programId=23, byteLength=9))
        self.assertEqual(self.checkpoint.status()['status'], 'durable')
        self.assertFalse(self.checkpoint.busy())

    def test_stale_sequence_identity_and_program_receipts_fail_closed(self):
        for changes in (dict(requestSeq=4), dict(programId=24), dict(imageSha256='b' * 64),
                        dict(status='exported'), dict(extra=True), dict(schema=True),
                        dict(requestSeq=2.0), dict(programId=23.0)):
            with self.subTest(changes=changes):
                self.checkpoint.current = None
                self.checkpoint.begin(2, 23)
                self.receipt(**changes)
                self.assertEqual(self.checkpoint.status()['status'], 'failed')
                self.assertTrue(self.checkpoint.busy())

    def test_firmware_error_never_exports(self):
        self.reply[8] = 22
        self.checkpoint.begin(2, 23)
        self.jobs[0]()
        self.assertEqual(self.exports, 0)
        self.assertEqual(self.checkpoint.status()['status'], 'failed')
        self.assertFalse(Path(self.tmp.name, 'export.json').exists())
        self.assertFalse(self.checkpoint.busy(), 'known firmware errno must permit another command')
        self.checkpoint.begin(4, 23)

    def test_wrong_save_id_never_exports(self):
        self.reply[4] = 24
        self.checkpoint.begin(2, 23)
        self.jobs[0]()
        self.assertEqual(self.exports, 0)
        self.assertEqual(self.checkpoint.status()['status'], 'failed')

    def test_waits_for_firmware_reply_and_then_host_receipt(self):
        good = self.reply
        self.reply = None
        def progress():
            if self.clock >= 0.5:
                self.reply = good
            if Path(self.tmp.name, 'export.json').exists():
                self.receipt()
        self.on_sleep = progress
        self.checkpoint.begin(2, 23)
        self.jobs[0]()
        self.assertGreaterEqual(self.clock, 0.5)
        self.assertEqual(self.checkpoint.status()['status'], 'durable')

    def test_host_timeout_blocks_replacement_until_close(self):
        self.checkpoint.begin(2, 23)
        self.jobs[0]()
        self.assertEqual(self.clock, 30)
        self.assertEqual(self.checkpoint.status()['status'], 'failed')
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.checkpoint.begin(4, 24)

    def test_wrong_export_length_never_publishes_metadata(self):
        self.checkpoint.export = lambda: b'short'
        self.checkpoint.begin(2, 23)
        self.jobs[0]()
        self.assertFalse(Path(self.tmp.name, 'export.json').exists())
        self.assertEqual(self.checkpoint.status()['status'], 'failed')

    def test_fixed_preboot_hook_restores_only_exact_flash(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        restore = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'mc_spike_flash_restore')
        writes = []
        env = dict(os=os, _FlashCheckpoint=self.kind,
                   _resolve=lambda path: SimpleNamespace(UnderlyingMemory=SimpleNamespace(
                       WriteBytes=lambda offset, data: writes.append((offset, data)))))
        exec(compile(ast.Module(body=[restore], type_ignores=[]), 'actual-preboot-hook', 'exec'), env)
        fake_io = SimpleNamespace(File=SimpleNamespace(ReadAllBytes=lambda path: Path(path).read_bytes()))
        with patch.dict(sys.modules, {'System': SimpleNamespace(), 'System.IO': fake_io}), \
                patch.dict(os.environ, {'BW_SPIKE_FLASH_JOB_DIR': self.tmp.name}):
            env['mc_spike_flash_restore']()
            self.assertEqual(writes, [])
            Path(self.tmp.name, 'restore.bin').write_bytes(b'short')
            with self.assertRaisesRegex(ValueError, 'size'):
                env['mc_spike_flash_restore']()
            self.assertEqual(writes, [])
            Path(self.tmp.name, 'restore.bin').write_bytes(b'12345678')
            env['mc_spike_flash_restore']()
            self.assertEqual(writes, [(0, b'12345678')])

    def test_service_factory_never_restores_mounted_flash(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_flash_checkpoint')
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr == 'WriteBytes'
                             for n in ast.walk(factory)))

    def test_dispatch_serializes_checkpoint_and_only_deferred_save_exports(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        dispatch = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_dispatch')
        submitted, began = [], []
        mailbox = SimpleNamespace(validate_packet=lambda packet: packet, supports_storage=lambda *args: True,
                                  submit=lambda *args: submitted.append(args[1]) or 42)
        machine = SimpleNamespace(SystemBus=SimpleNamespace(ReadDoubleWord=None, ReadBytes=None, WriteDoubleWord=None),
                                  ObtainPausedState=lambda value: SimpleNamespace(Dispose=lambda: None))
        env = dict(spike_nuttx_mailbox=mailbox, monitor=SimpleNamespace(Machine=machine))
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), 'actual-dispatch', 'exec'), env)
        config = dict(identity=dict(board='spike-prime', firmware='brickwright-nuttx', transport='none'),
                      paths={}, programMailbox=0x20021000)
        checkpoint = SimpleNamespace(busy=lambda: False, begin=lambda *args: began.append(args))
        command = dict(command='nuttx.program.storage.submit', arguments=dict(bytes=[0x70, 1, 8, 0, 23, 0, 0, 0]))
        env['_dispatch'](config, command, checkpoint)
        self.assertEqual(began, [(42, 23)])
        command['arguments']['bytes'][2] = 9
        env['_dispatch'](config, command, checkpoint)
        self.assertEqual(began, [(42, 23)], 'LOAD must not checkpoint or run')
        checkpoint.busy = lambda: True
        for op in (1, 4, 5, 8, 9):
            command['arguments']['bytes'][2] = op
            with self.assertRaisesRegex(ValueError, 'pending'):
                env['_dispatch'](config, command, checkpoint)
        self.assertEqual(len(submitted), 2, 'busy rejection must precede mailbox mutation')
        checkpoint.busy = lambda: False
        command['command'] = 'nuttx.program.packet'
        command['arguments']['bytes'][2] = 8
        with self.assertRaisesRegex(ValueError, 'deferred'):
            env['_dispatch'](config, command, checkpoint)
        self.assertEqual(len(submitted), 2)

    def test_production_flash_size_and_trusted_paths(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_FlashCheckpoint')
        size = next(n.value.value for n in cls.body if isinstance(n, ast.Assign) and n.targets[0].id == 'SIZE')
        self.assertEqual(size, 32 * 1024 * 1024)
        source = ast.unparse(tree)
        self.assertIn("os.environ.get('BW_SPIKE_FLASH_JOB_DIR')", source)
        self.assertIn("durable SAVE requires deferred storage submission", source)


if __name__ == '__main__':
    unittest.main()
