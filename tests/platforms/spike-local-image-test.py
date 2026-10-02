#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic import checks; no firmware downloads or private inputs."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("local_image", Path(__file__).parents[2] / "tools/spike_local_image.py")
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)


def record(kind, address, payload=b""):
    data = bytes([len(payload)]) + address.to_bytes(2, "big") + bytes([kind]) + payload
    return ":" + (data + bytes([-sum(data) % 256])).hex() + "\n"


class ImportTests(unittest.TestCase):
    def valid_hex(self):
        return record(4, 0, b"\x08\x01") + record(0, 0, struct.pack("<II", 0x2004fff8, 0x08010009) + b"\x00\xbf") + record(1, 0)

    def test_valid_application(self):
        memory = image.read_hex(self.valid_hex().encode())
        self.assertEqual(image.vectors(memory, 0x08010000), (0x2004fff8, 0x08010009))

    def test_corruption_and_eof(self):
        value = self.valid_hex()
        for bad in (value.replace("02000004", "03000004"), value[:-12], value + record(0, 0, b"a"), "garbage\n" + value):
            with self.assertRaises(ValueError):
                image.read_hex(bad.encode())

    def test_outside_physical_flash(self):
        for high in (0x07ff, 0x0810, 0x2000):
            with self.assertRaises(ValueError):
                image.read_hex((record(4, 0, high.to_bytes(2, "big")) + record(0, 0, b"abc") + record(1, 0)).encode())

    def test_overlap(self):
        value = self.valid_hex().replace(record(1, 0), record(0, 0, b"wrong") + record(1, 0))
        with self.assertRaises(ValueError):
            image.read_hex(value.encode())

    def test_reset_requires_loaded_code_and_valid_stack(self):
        for sp, pc in ((0x20050008, 0x08010009), (0x2004fff9, 0x08010009), (0x2004fff8, 0x08010008), (0x2004fff8, 0x08020001)):
            memory = dict(enumerate(struct.pack("<II", sp, pc) + b"\x00\xbf", 0x08010000))
            with self.assertRaises(ValueError):
                image.vectors(memory, 0x08010000)
        with self.assertRaises(ValueError):
            image.vectors({}, 0x08010001)


if __name__ == "__main__":
    unittest.main()
