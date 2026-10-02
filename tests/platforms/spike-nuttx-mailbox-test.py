#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('mailbox', Path(__file__).parents[2] / 'tools/spike_nuttx_mailbox.py')
mailbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mailbox)


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.base = 0x20021000
        self.memory = bytearray(mailbox.SIZE)
        self.writes = []
        self.put(0, mailbox.MAGIC)
        self.put(4, 1)
        self.put(60, 2)

    def put(self, offset, value):
        struct.pack_into('<I', self.memory, offset, value)

    def read(self, address):
        return struct.unpack_from('<I', self.memory, address - self.base)[0]

    def write(self, address, value):
        self.writes.append((address, value))
        self.put(address - self.base, value)

    def bytes(self, address, count):
        return self.memory[address - self.base:address - self.base + count]

    def test_packet_bounds_fail_before_any_write(self):
        for packet in ([0x70, 1, 5, 0, 0, 0, 0], [0x70, 1, 3, 0, 0, 0, 0, 0],
                       [0x70, 1, 5, 0, False, 0, 0, 0], [0x70, 1, 0, 0, 1, 0, 0, 0]):
            with self.assertRaises(ValueError):
                mailbox.submit(self.base, packet, self.read, self.write)
        for base in (0x20000000, 0x20040000 - 108, self.base + 1, True):
            with self.assertRaises(ValueError):
                mailbox.validate_base(base)
        self.assertEqual(self.writes, [])

    def test_storage_operations_have_no_path_or_extra_payload(self):
        for op in (8, 9):
            packet = [0x70, 1, op, 0, 42, 0, 0, 0]
            self.assertEqual(list(mailbox.validate_packet(packet)), packet)
            for bad in (packet + [0], packet[:7], packet[:4] + [0]*4):
                with self.assertRaises(ValueError):
                    mailbox.validate_packet(bad)
        with self.assertRaises(ValueError):
            mailbox.validate_packet([0x70, 1, 10, 0, 42, 0, 0, 0])

    def test_transaction_and_reply_correlation(self):
        packet = [0x70, 1, 5, 0, 0, 0, 0, 0]
        seq = mailbox.submit(self.base, packet, self.read, self.write)
        self.assertEqual(seq, 2)
        self.assertEqual(self.writes[0], (self.base + 8, 1))
        self.assertEqual(self.writes[-1], (self.base + 8, 2))
        self.assertEqual(list(self.memory[16:36]), packet + [0] * 12)
        self.assertIsNone(mailbox.reply(self.base, seq, self.read, self.bytes))
        writes = list(self.writes)
        with self.assertRaises(ValueError):
            mailbox.submit(self.base, packet, self.read, self.write)
        self.assertEqual(self.writes, writes)
        self.put(36, seq)
        self.memory[40:60] = bytes([0x71, 1, 5, 1] + [0] * 16)
        self.assertEqual(mailbox.reply(self.base, seq, self.read, self.bytes)[3], 1)

    def test_unready_worker_and_sequence_wrap(self):
        packet = [0x70, 1, 5, 0, 0, 0, 0, 0]
        self.put(60, 0)
        with self.assertRaises(ValueError):
            mailbox.submit(self.base, packet, self.read, self.write)
        self.assertEqual(self.writes, [])
        self.put(60, 2)
        self.put(8, 0xfffffffe)
        self.put(36, 0xfffffffe)
        self.assertEqual(mailbox.submit(self.base, packet, self.read, self.write), 2)

    def test_coherent_signed_status_and_partial_publication(self):
        self.memory[60:112] = struct.pack('<6I6iI', 10, 1234, 5, 42, 3, 0xfffffffb,
                                        -90, 180, -300, 0, -5000, 0, 3)
        status = mailbox.status(self.base, self.read, self.bytes)
        self.assertEqual(status['error'], -5)
        self.assertEqual(status['positions'], [-90, 180])
        self.assertEqual(status['speeds'], [-300, 0])
        self.assertEqual(status['duties'], [-5000, 0])
        self.put(60, 11)
        with self.assertRaises(ValueError):
            mailbox.status(self.base, self.read, self.bytes)
        self.put(60, 10)
        reads = [10, 12] * 3
        def changing(address):
            return reads.pop(0) if address == self.base + 60 else self.read(address)
        with self.assertRaises(ValueError):
            mailbox.status(self.base, changing, self.bytes)


class OutputTests(unittest.TestCase):
    def test_bounded_utf8_output_and_partial_publication(self):
        base = 0x20021000
        raw = bytearray(struct.pack('<III', 2, 5, 1) + 'hi ☀'.encode('utf-8') + bytes(1024))
        read = lambda address: struct.unpack_from('<I', raw, address - base)[0]
        read_bytes = lambda address, count: raw[address - base:address - base + count]
        result = mailbox.output(base, read, read_bytes)
        self.assertEqual(result['text'], 'hi �')
        self.assertTrue(result['truncated'])
        struct.pack_into('<I', raw, 4, 6)
        self.assertEqual(mailbox.output(base, read, read_bytes)['text'], 'hi ☀')
        struct.pack_into('<I', raw, 4, 1025)
        with self.assertRaises(ValueError): mailbox.output(base, read, read_bytes)
        struct.pack_into('<II', raw, 0, 3, 6)
        with self.assertRaises(ValueError): mailbox.output(base, read, read_bytes)
        with self.assertRaises(ValueError): mailbox.validate_output_base(0x20040000-1024)


if __name__ == '__main__':
    unittest.main()
