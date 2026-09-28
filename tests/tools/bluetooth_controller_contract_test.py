#!/usr/bin/env python3
"""Contract tests for transport-neutral Bluetooth protocol boundaries.

SPDX-License-Identifier: MIT
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from bluetooth_controller import ControllerConfig, L2capChannel, L2capRouter


class Echo:
    def receive(self, payload: bytes) -> list[bytes]:
        return [payload[::-1]]


class ContractTests(unittest.TestCase):
    def test_configuration_requires_six_byte_address(self):
        with self.assertRaisesRegex(ValueError, "six bytes"):
            ControllerConfig(address=b"short")

    def test_l2cap_router_is_transport_independent(self):
        router = L2capRouter()
        router.bind(L2capChannel(0x0040, Echo()))
        packet = L2capRouter.frame(0x0040, b"abc")
        self.assertEqual(router.receive(packet), [L2capRouter.frame(0x0040, b"cba")])

    def test_l2cap_router_rejects_malformed_and_duplicate_channels(self):
        router = L2capRouter()
        router.bind(L2capChannel(4, Echo()))
        with self.assertRaisesRegex(ValueError, "already bound"):
            router.bind(L2capChannel(4, Echo()))
        with self.assertRaisesRegex(ValueError, "length"):
            router.receive(b"\x02\x00\x04\x00x")


if __name__ == "__main__":
    unittest.main()
