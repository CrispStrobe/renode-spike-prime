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


    def test_reset_requires_both_opcode_bytes(self):
        memory = image.read_hex(self.valid_hex().encode())
        del memory[0x08010009]
        with self.assertRaises(ValueError):
            image.vectors(memory, 0x08010000)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        # A Thumb self-loop can execute the full budget without changing PC.
        self.memory = {0x08010008: 0xfe, 0x08010009: 0xe7}
        self.state = {"instructionsBefore": 17, "instructionsAfter": 2017,
                      "pc": 0x08010008, "sp": 0x2004fff8, "icsr": 0}

    def test_same_pc_with_exact_instruction_delta_is_valid(self):
        image.validate_observation(self.state, self.memory, 2000)

    def test_nonfault_exception_and_unrelated_icsr_bits_are_valid(self):
        self.state["icsr"] = 0x04000000 | 15  # SysTick active, pending bit set.
        image.validate_observation(self.state, self.memory, 2000)

    def test_missing_and_wrong_observation_types(self):
        for field in self.state:
            for value in (None, True, False, 1.0, "1", [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    image.validate_observation({**self.state, field: value}, self.memory, 2000)
            missing = dict(self.state)
            del missing[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                image.validate_observation(missing, self.memory, 2000)
        for value in (None, [], True):
            with self.assertRaises(ValueError):
                image.validate_observation(value, self.memory, 2000)

    def test_wrong_or_negative_instruction_counts(self):
        for before, after in ((17, 17), (17, 2016), (17, 2018), (-1, 1999), (17, -1)):
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                image.validate_observation({**self.state, "instructionsBefore": before,
                                            "instructionsAfter": after}, self.memory, 2000)

    def test_uint64_instruction_counter_boundary(self):
        maximum = (1 << 64) - 1
        image.validate_observation({**self.state, "instructionsBefore": maximum - 2000,
                                    "instructionsAfter": maximum}, self.memory, 2000)
        for before, after in ((maximum - 1999, maximum + 1),
                              (maximum + 1, maximum + 2001), (maximum - 1000, 999)):
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                image.validate_observation({**self.state, "instructionsBefore": before,
                                            "instructionsAfter": after}, self.memory, 2000)

    def test_final_pc_must_be_even_and_originally_loaded(self):
        for pc in (0x08010009, 0x0801000a, 0x20000000, -2):
            with self.subTest(pc=pc), self.assertRaises(ValueError):
                image.validate_observation({**self.state, "pc": pc}, self.memory, 2000)
        with self.assertRaises(ValueError):
            image.validate_observation(self.state, {0x08010008: 0xfe}, 2000)

    def test_invalid_final_stack(self):
        for sp in (0x20000000, 0x20050008, 0x2004fffc, -8):
            with self.subTest(sp=sp), self.assertRaises(ValueError):
                image.validate_observation({**self.state, "sp": sp}, self.memory, 2000)

    def test_active_faults_and_invalid_icsr_are_rejected(self):
        for icsr in (3, 4, 5, 6, 0x04000003, -1, 0x100000000):
            with self.subTest(icsr=icsr), self.assertRaises(ValueError):
                image.validate_observation({**self.state, "icsr": icsr}, self.memory, 2000)


if __name__ == "__main__":
    unittest.main()
