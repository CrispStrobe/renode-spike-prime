#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Source/TCP-independent observation controls, never a firmware guest."""
import ast
import contextlib
import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location('mailbox_publication_control', ROOT / 'tools/spike_nuttx_mailbox.py')
mailbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mailbox)


class Memory:
    base, output_base = 0x20021000, 0x20022000
    storage_marker, distance_marker = 0x08060400, 0x08060404

    def __init__(self):
        self.data, self.out = bytearray(112), bytearray(1036)
        self.markers = {self.storage_marker: 1, self.distance_marker: 1}
        self.reads = []
        self.word(0, mailbox.MAGIC);self.word(4, 1)
        self.word(60, 2);self.word(64, 100);self.word(68, 3);self.word(72, 42)
        self.word(108, 3)
        struct.pack_into('<III', self.out, 0, 2, 6, 0)
        self.out[12:18] = b'before'
        self.config = {'identity': {'board': 'spike-prime', 'firmware': 'brickwright-nuttx',
            'transport': 'none', 'imageSha256': 'a' * 64}, 'paths': {'portA': 'portA'},
            'programMailbox': self.base, 'pythonOutputMailbox': self.output_base,
            'programStorageAbiAddress': self.storage_marker,
            'addressedSensorCapability': {'abi': 1, 'address': self.distance_marker,
                'userspaceSha256': 'a' * 64}}

    def word(self, offset, value):
        struct.pack_into('<I', self.data, offset, value)

    def read(self, address):
        self.reads.append(address)
        if address in self.markers:
            return self.markers[address]
        data, offset = (self.data, address - self.base) if address < self.output_base else (self.out, address - self.output_base)
        return struct.unpack_from('<I', data, offset)[0]

    def bytes(self, address, count):
        data, offset = (self.data, address - self.base) if address < self.output_base else (self.out, address - self.output_base)
        return data[offset:offset + count]

    ReadDoubleWord = read
    ReadBytes = bytes

    def ack(self, op=3, sequence=2):
        self.word(8, sequence);self.word(12, 8);self.word(36, sequence)
        self.data[16:24] = bytes([0x70, 1, op, 0, 42, 0, 0, 0])
        self.data[40:60] = bytes([0x71, 1, op, 2, 42, 0, 0, 0] + [0] * 12)

    def observe(self, allow=True):
        return mailbox.observe_program(self.config, self.read, self.bytes, allow)


def load_server_function(name, globals_, method=False):
    tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
    nodes = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_Server').body if method else tree.body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(ROOT / 'scripts/spike-state-server.py'), 'exec'), globals_)
    return globals_[name]


def snapshot_namespace(memory, clock=None):
    clock = clock or NS(TotalNanoseconds=0)
    port = NS(Device=None, TopologyGeneration=0)
    lockstep = NS(CAPABILITIES=['lockstep/v1'], DEFERRED_START_CAPABILITY='nuttx-program-control-deferred/v1',
        Lockstep=NS(supported=lambda ports: True))
    return {'spike_nuttx_mailbox': mailbox, 'spike_lockstep': lockstep,
        'monitor': NS(Machine=NS(SystemBus=memory)),
        'emulationManager': NS(CurrentEmulation=NS(MasterTimeSource=NS(ElapsedVirtualTime=clock))),
        '_optional': lambda paths, role: port if role == 'portA' else None,
        '_kind': lambda device: None, '_prime_hub_models': lambda *args: None,
        '_lockstep_profile': lambda config: True, '_electrical_ports': lambda config: {}}


class PublicationTests(unittest.TestCase):
    def test_sequences_bind_real_status_and_reply_bytes(self):
        m = Memory();m.ack()
        observed, caps = m.observe()
        self.assertEqual(observed['nuttxProgram']['publicationSeq'], 2)
        self.assertEqual(observed['nuttxProgram']['state'], 3)
        self.assertEqual(observed['nuttxProgramReplySeq'], 2)
        self.assertEqual(observed['nuttxProgramReply'], list(m.data[40:60]))
        self.assertIn(mailbox.PUBLICATION_CAPABILITY, caps)

    def test_unavailable_status_is_not_cached_and_does_not_hide_output_or_ack(self):
        m = Memory();m.ack();self.assertIn('nuttxProgram', m.observe()[0])
        m.word(60, 3)
        observed, caps = m.observe()
        self.assertNotIn('nuttxProgram', observed)
        self.assertEqual(observed['nuttxProgramOutput']['text'], 'before')
        self.assertEqual(observed['nuttxProgramReplySeq'], 2)
        self.assertIn('nuttx-program/v1', caps)
        self.assertIn('nuttx-addressed-distance/v1', caps)
        with self.assertRaises(mailbox.PublicationNotReady) as error:
            m.observe(False)
        self.assertEqual(error.exception.publication, 'status')

    def test_unavailable_output_is_independent_and_never_replays_previous_text(self):
        m = Memory();self.assertEqual(m.observe()[0]['nuttxProgramOutput']['text'], 'before')
        struct.pack_into('<I', m.out, 0, 3);m.out[12:18] = b'broken'
        observed, unused = m.observe()
        self.assertIn('nuttxProgram', observed)
        self.assertNotIn('nuttxProgramOutput', observed)
        with self.assertRaises(mailbox.PublicationNotReady) as error:
            m.observe(False)
        self.assertEqual(error.exception.publication, 'output')

    def test_changing_sequence_is_transient_without_accepting_mixed_bytes(self):
        for kind, address in [('status', Memory.base + 60), ('output', Memory.output_base)]:
            m = Memory();calls = [0]
            def changing(value):
                if value == address:
                    calls[0] += 1
                    return 2 if calls[0] % 2 else 4
                return m.read(value)
            observed, unused = mailbox.observe_program(m.config, changing, m.bytes, True)
            self.assertNotIn('nuttxProgram' if kind == 'status' else 'nuttxProgramOutput', observed)

    def test_malformed_data_remains_fatal_in_sparse_mode(self):
        def bad_status(m): m.word(68, 6)
        def bad_output(m): struct.pack_into('<I', m.out, 4, 1025)
        def bad_reply(m): m.ack();m.data[40] = 0
        def bad_header(m): m.word(0, 0);m.word(60, 3)
        def bad_storage(m): m.ack(8);m.word(12, 9)
        def bad_identity(m): m.config['addressedSensorCapability']['userspaceSha256'] = 'b' * 64
        for corrupt in [bad_status, bad_output, bad_reply, bad_header, bad_storage, bad_identity]:
            with self.subTest(corrupt=corrupt.__name__):
                m = Memory();corrupt(m)
                with self.assertRaises(ValueError) as error: m.observe()
                self.assertNotIsInstance(error.exception, mailbox.PublicationNotReady)

    def test_zero_publication_or_wrong_marker_does_not_admit_support(self):
        m = Memory();m.word(60, 0)
        self.assertEqual(m.observe(), ({}, []))
        m = Memory();m.markers[m.distance_marker] = 0
        self.assertNotIn('nuttx-addressed-distance/v1', m.observe()[1])
        # The old ordinary readiness guard is retained unchanged.
        for version in (0, 1, 3):
            m = Memory();m.word(60, version)
            self.assertFalse(mailbox.supports_addressed_distance(m.base,
                m.config['addressedSensorCapability'], 'a' * 64, m.read))
            self.assertNotIn(m.distance_marker, m.reads)

    def test_odd_ack_is_not_read_and_storage_transience_is_typed(self):
        m = Memory();m.ack(8);m.word(36, 3)
        self.assertIsNone(mailbox.reply(m.base, 3, m.read,
            lambda *args: self.fail('partial reply bytes were read')))
        observed, unused = m.observe()
        self.assertNotIn('nuttxProgramReply', observed)
        self.assertNotIn('nuttxProgramReplySeq', observed)
        self.assertNotIn('nuttxProgramStorage', observed)
        self.assertIn('nuttxProgram', observed)

    def test_reply_replacement_never_emits_old_sequence_with_new_bytes(self):
        m = Memory();m.ack(4, 2);m.word(8, 4)
        # A new START is being copied while reply_seq still names the old STOP.
        m.data[42] = 3
        observed, unused = m.observe()
        self.assertNotIn('nuttxProgramReply', observed)
        self.assertNotIn('nuttxProgramReplySeq', observed)
        m.word(36, 4)
        observed, unused = m.observe()
        self.assertEqual(observed['nuttxProgramReplySeq'], 4)
        self.assertEqual(observed['nuttxProgramReply'][2], 3)

    def test_reply_read_rechecks_request_ownership(self):
        m = Memory();m.ack()
        def replacing(address, count):
            data = m.bytes(address, count)
            if address == m.base + 40:
                m.word(8, 4)
            return data
        observed, unused = mailbox.observe_program(m.config, m.read, replacing, True)
        self.assertNotIn('nuttxProgramReply', observed)
        self.assertNotIn('nuttxProgramReplySeq', observed)

    def test_completed_storage_requires_its_actual_matching_reply(self):
        m = Memory();m.ack(8)
        self.assertFalse(m.observe()[0]['nuttxProgramStorage']['pending'])
        with patch.object(mailbox, 'reply', return_value=None):
            self.assertNotIn('nuttxProgramStorage', m.observe()[0])
            with self.assertRaises(mailbox.PublicationNotReady): m.observe(False)
        m.data[42] = 9
        with self.assertRaisesRegex(ValueError, 'inconsistent'): m.observe()

    def test_lockstep_paused_publication_keeps_exact_step(self):
        m = Memory();m.word(60, 3)
        clock = NS(TotalNanoseconds=0);g = snapshot_namespace(m, clock)
        load_server_function('_snapshot', g)
        command = load_server_function('_lockstep_command', g, True)
        calls = []
        def step(args):
            calls.append(args);clock.TotalNanoseconds += 5000000;return {}
        server = NS(config=m.config, seq=1, generation=1, checkpoint=None,
            program_uart=None, state_lock=contextlib.nullcontext(), lockstep=NS(step=step))
        frame = command(server, {'command': 'lockstep.step', 'arguments': {'microseconds': 5000}})
        self.assertEqual(calls, [{'microseconds': 5000}])
        self.assertEqual(frame['clockNs'], 5000000)
        self.assertNotIn('nuttxProgram', frame['lifecycle'])
        self.assertIn('nuttxProgramOutput', frame['lifecycle'])

    def test_missing_storage_omits_coupled_checkpoint_only_in_lockstep(self):
        m = Memory();m.ack(8);m.word(36, 3)
        g = snapshot_namespace(m);snapshot = load_server_function('_snapshot', g)
        checkpoint = NS(status=lambda: {'phase': 'pending'})
        frame = snapshot(m.config, 1, 1, checkpoint, allow_unavailable=True)
        self.assertIn('nuttx-flash-checkpoint/v1', frame['target']['capabilities'])
        self.assertNotIn('nuttxProgramStorage', frame['lifecycle'])
        self.assertNotIn('nuttxFlashCheckpoint', frame['lifecycle'])

    def test_only_active_accepted_deferred_control_uses_sparse_trailing_sample(self):
        for active, name, expected in [(True, 'nuttx.program.control.submit', True),
                (False, 'nuttx.program.control.submit', False), (True, 'nuttx.program.packet', False)]:
            with self.subTest(active=active, name=name):
                request = {'requestId': 'control-1', 'expectedSeq': 0, 'command': name, 'arguments': {}}
                raw = (json.dumps(request) + '\n').encode()
                class Stream:
                    count = 0
                    def Read(self, buffer, offset, limit):
                        self.count += 1
                        if self.count > 1: return 0
                        buffer[:len(raw)] = raw;return len(raw)
                stream = Stream();samples = []
                lockstep = NS(active=active, allowed=lambda command: True)
                server = NS(config={}, running=True, lockstep=lockstep, checkpoint=None,
                    program_uart=None, _send=lambda *args: None)
                def sample(snapshot=None, allow_unavailable=False):
                    samples.append(allow_unavailable);server.seq += 1
                server.sample = sample
                class Buffer(bytearray):
                    @property
                    def Length(self): return len(self)
                g = {'Array': NS(CreateInstance=lambda *args: Buffer(4096)), 'Byte': int,
                    '_READ_SIZE': 4096, 'Encoding': NS(UTF8=NS(GetString=lambda b, o, n: bytes(b[o:o+n]).decode())),
                    'split_frames': lambda pending, chunk, *args: (chunk.splitlines(), ''),
                    'validate_command': lambda value: value, 'json': json,
                    'spike_lockstep': NS(COMMANDS=(), DEFERRED_CONTROL_COMMAND='nuttx.program.control.submit'),
                    'PROGRAM_UART_COMMANDS': (), '_dispatch': lambda *args: {'requestSeq': 2}}
                server.limit, server.timeout = 65536, 5000
                client = NS(GetStream=lambda: stream)
                load_server_function('_client', g, True)(server, client, 1)
                self.assertEqual(samples, [False, expected])


if __name__ == '__main__':
    unittest.main()
