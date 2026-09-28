#!/usr/bin/env python3
"""ATT/GATT and RFCOMM peer tests. SPDX-License-Identifier: MIT"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from bluetooth_controller import (
    Attribute, AttGattServer, ClassicL2capSignaling, L2capChannel,
    L2capRouter, RfcommSession, SdpServer,
)


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

    def test_att_builds_bounded_telemetry_notification_and_indication(self):
        self.assertEqual(self.gatt.notification(3), b"\x1b\x03\x00SPIKE")
        self.assertEqual(self.gatt.indication(3, b"state"), b"\x1d\x03\x00state")
        with self.assertRaisesRegex(ValueError, "not present"):
            self.gatt.notification(99)

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

    def test_classic_signaling_establishes_and_removes_rfcomm_channel(self):
        router = L2capRouter()
        rfcomm = RfcommSession(1)
        signaling = ClassicL2capSignaling(router, rfcomm)
        router.bind(L2capChannel(1, signaling))
        connect = bytes.fromhex("0201040003004100")
        response = router.receive(L2capRouter.frame(1, connect))[0]
        self.assertEqual(response, L2capRouter.frame(1, bytes.fromhex("030108004000410000000000")))
        config = bytes.fromhex("0402040040000000")
        self.assertEqual(router.receive(L2capRouter.frame(1, config))[0],
                         L2capRouter.frame(1, bytes.fromhex("05020600410000000000")))
        ua = router.receive(L2capRouter.frame(0x40, rfcomm._frame(0x2F)))[0]
        self.assertEqual(int.from_bytes(ua[2:4], "little"), 0x41)
        disconnect = bytes.fromhex("0603040040004100")
        router.receive(L2capRouter.frame(1, disconnect))
        self.assertEqual(router.receive(L2capRouter.frame(0x40, rfcomm._frame(0x2F))), [])

    def test_sdp_service_search_attribute_response_is_configurable(self):
        server = SdpServer(bytes.fromhex("3503191101"))
        # The generic server intentionally treats the search patterns as opaque.
        response = server.receive(bytes.fromhex("0612340000"))[0]
        self.assertEqual(response, bytes.fromhex("07123400080005350319110100"))


if __name__ == "__main__":
    unittest.main()
