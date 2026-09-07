#!/usr/bin/env python3
"""ATT/GATT and RFCOMM peer tests. SPDX-License-Identifier: MIT"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from bluetooth_controller import Attribute, AttGattServer, RfcommSession


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.gatt = AttGattServer([
            Attribute(1, 0x2800, b"\x00\x18"),
            Attribute(2, 0x2803, b"\x0a\x03\x00\x00\x2a"),
            Attribute(3, 0x2A00, b"SPIKE"),
            Attribute(4, 0x2800, bytes.fromhex("12121212121212121212121212121212")),
            Attribute(5, 0xFFF1, b"initial", writable=True),
        ])

    def test_att_mtu_discovery_read_and_write(self):
        self.assertEqual(self.gatt.receive(bytes.fromhex("024000")), [bytes.fromhex("03f700")])
        self.assertEqual(self.gatt.receive(bytes.fromhex("100100ffff0028"))[0],
                         bytes.fromhex("1106010003000018"))
        self.assertEqual(self.gatt.receive(bytes.fromhex("0a0300")), [b"\x0bSPIKE"])
        self.assertEqual(self.gatt.receive(b"\x12\x05\x00changed"), [b"\x13"])
        self.assertEqual(self.gatt.attributes[-1].value, b"changed")

    def test_att_reports_missing_and_forbidden_values(self):
        self.assertEqual(self.gatt.receive(bytes.fromhex("0a9900")), [bytes.fromhex("010a990001")])
        self.assertEqual(self.gatt.receive(b"\x12\x03\x00x"), [bytes.fromhex("0112030003")])

    def test_rfcomm_session_lifecycle_and_data(self):
        session = RfcommSession(1, lambda data: b"reply:" + data)
        sabm = session._frame(0x2F)
        reply = session.receive(sabm)
        self.assertTrue(session.open)
        self.assertEqual(reply[0][1] & 0xEF, 0x63)
        data_reply = session.receive(session._frame(0xEF, b"hello"))
        self.assertEqual(data_reply[0][3:-1], b"reply:hello")
        session.receive(session._frame(0x43))
        self.assertFalse(session.open)


if __name__ == "__main__":
    unittest.main()
