#!/usr/bin/env python3
"""Byte-exact H4 and HCI controller tests. SPDX-License-Identifier: MIT"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from bluetooth_controller import BluetoothController, ControllerConfig, L2capChannel, L2capRouter


def command(opcode: int, parameters: bytes = b"") -> bytes:
    return b"\x01" + opcode.to_bytes(2, "little") + bytes([len(parameters)]) + parameters


class Echo:
    def receive(self, payload):
        return [payload.upper()]


class HciTests(unittest.TestCase):
    def setUp(self):
        self.frames = []
        self.controller = BluetoothController(self.frames.append)

    def test_fragmented_and_coalesced_commands(self):
        stream = command(0x0C03) + command(0x1009)
        self.controller.feed(stream[:2])
        self.assertEqual(self.frames, [])
        self.controller.feed(stream[2:])
        self.assertEqual(self.frames[0], bytes.fromhex("040e0401030c00"))
        self.assertEqual(self.frames[1], bytes.fromhex("040e0a01091000060504030201"))

    def test_vendor_policy_is_explicit(self):
        self.controller.feed(command(0xFF05, b"opaque"))
        self.assertEqual(self.frames[-1][-1], 1)
        enabled = BluetoothController(self.frames.append, ControllerConfig(acknowledge_vendor_commands=True))
        enabled.feed(command(0xFF05, b"opaque"))
        self.assertEqual(self.frames[-1], bytes.fromhex("040e040105ff00"))

    def test_le_advertising_connection_and_acl_routing(self):
        self.controller.feed(command(0x2008, bytes([3]) + b"abc" + bytes(28)))
        self.controller.feed(command(0x200A, b"\x01"))
        self.assertEqual(self.controller.advertising_data, b"abc")
        self.controller.l2cap.bind(L2capChannel(4, Echo()))
        self.controller.connect_le(bytes.fromhex("010203040506"))
        self.assertEqual(self.frames[-1][:4], bytes.fromhex("043e1301"))
        packet = L2capRouter.frame(4, b"hello")
        acl = b"\x02\x01\x20" + len(packet).to_bytes(2, "little") + packet
        self.controller.feed(acl[:7])
        self.controller.feed(acl[7:])
        self.assertEqual(self.frames[-2], b"\x02\x01\x20\x09\x00" + L2capRouter.frame(4, b"HELLO"))
        self.assertEqual(self.frames[-1], bytes.fromhex("0413050101000100"))

    def test_classic_request_accept_disconnect(self):
        peer = bytes.fromhex("010203040506")
        self.controller.feed(command(0x0C1A, b"\x02"))
        self.controller.request_classic_connection(peer)
        self.assertEqual(self.frames[-1], b"\x04\x04\x0a" + peer + bytes.fromhex("00080001"))
        self.controller.feed(command(0x0409, peer + b"\0"))
        self.assertTrue(self.controller.connected and self.controller.classic)
        self.assertEqual(self.frames[-2], bytes.fromhex("040f0400010904"))
        self.controller.disconnect()
        self.assertEqual(self.frames[-1], bytes.fromhex("04050400010013"))

    def test_rejects_bad_h4_and_inactive_acl(self):
        with self.assertRaisesRegex(ValueError, "H4"):
            self.controller.feed(b"\x03")
        with self.assertRaisesRegex(ValueError, "inactive"):
            BluetoothController(list().append).feed(bytes.fromhex("0201200000"))


if __name__ == "__main__":
    unittest.main()
