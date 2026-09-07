#!/usr/bin/env python3
"""Deterministic Bluetooth fault and reset soak gates. SPDX-License-Identifier: MIT"""

import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from bluetooth_controller import BluetoothController, ControllerConfig


def command(opcode: int, parameters: bytes = b"") -> bytes:
    return b"\x01" + opcode.to_bytes(2, "little") + bytes([len(parameters)]) + parameters


class BluetoothFaultSoakTests(unittest.TestCase):
    def test_malformed_streams_are_bounded_and_recover_after_each_fault(self):
        rng = random.Random(0x5350494B45)
        frames = []
        controller = BluetoothController(
            frames.append,
            ControllerConfig(h4_input_limit=64, l2cap_reassembly_limit=32),
        )

        for _ in range(256):
            declared = rng.randrange(61, 256)
            with self.assertRaisesRegex(ValueError, "resource limit"):
                controller.feed(b"\x01\x13\x0c" + bytes([declared]) + bytes(61))
            self.assertEqual(controller.pending_h4_bytes, 0)
            controller.feed(command(0x0C03))
            self.assertLessEqual(controller.pending_h4_bytes, 64)

        self.assertEqual(len(frames), 256)
        self.assertEqual(frames[-1], bytes.fromhex("040e0401030c00"))

    def test_repeated_connect_disconnect_reset_has_stable_protocol_ceilings(self):
        frames = []
        controller = BluetoothController(frames.append, ControllerConfig(acl_packets=2))
        peer = bytes.fromhex("010203040506")

        for _ in range(512):
            before = len(frames)
            controller.feed(command(0x200A, b"\x01"))
            controller.connect_le(peer)
            controller.disconnect()
            controller.feed(command(0x0C03))
            self.assertEqual(len(frames) - before, 4)
            self.assertFalse(controller.connected)
            self.assertEqual(controller.pending_h4_bytes, 0)
            self.assertEqual(controller.pending_acl_bytes, 0)

        self.assertEqual(len(frames), 2048)

    def test_acl_exhaustion_and_malformed_boundaries_clear_reassembly(self):
        controller = BluetoothController(
            list().append,
            ControllerConfig(h4_input_limit=32, l2cap_reassembly_limit=12),
        )
        controller.feed(command(0x200A, b"\x01"))
        controller.connect_le(bytes(6))

        fragment = b"\x0c\x00\x04\x00" + bytes(9)
        with self.assertRaisesRegex(ValueError, "reassembly"):
            controller.feed(b"\x02\x01\x20" + len(fragment).to_bytes(2, "little") + fragment)
        self.assertEqual(controller.pending_acl_bytes, 0)
        with self.assertRaisesRegex(ValueError, "packet-boundary"):
            controller.feed(bytes.fromhex("0201300000"))
        self.assertLessEqual(controller.pending_h4_bytes, 32)


if __name__ == "__main__":
    unittest.main()
