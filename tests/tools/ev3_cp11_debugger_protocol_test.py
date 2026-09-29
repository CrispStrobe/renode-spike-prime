#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Protocol fragmentation and disconnect regressions for the CP11 receipt."""
import unittest
from ev3_cp11_debugger_test import exchange


class FragmentedSocket:
    def __init__(self, response):
        self.response = bytearray(response)
        self.sent = []

    def recv(self, length):
        # Even a two-byte checksum read may return only one byte.
        if not self.response:
            return b""
        return bytes([self.response.pop(0)])

    def sendall(self, data):
        self.sent.append(data)


class ProtocolTests(unittest.TestCase):
    def test_fragmented_checksum(self):
        connection = FragmentedSocket(b"+$S05#b8")
        self.assertEqual(exchange(connection, "?"), "S05")
        self.assertEqual(connection.sent, [b"$?#3f", b"+"])

    def test_eof_before_marker(self):
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            exchange(FragmentedSocket(b"+"), "?")

    def test_eof_within_checksum(self):
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            exchange(FragmentedSocket(b"$S05#b"), "?")

    def test_bounded_marker(self):
        with self.assertRaisesRegex(RuntimeError, "marker exceeds limit"):
            exchange(FragmentedSocket(b"+" * 65536), "?")


if __name__ == "__main__":
    unittest.main()
