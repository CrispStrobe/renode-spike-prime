#!/usr/bin/env python3
"""End-to-end raw TCP adapter test. SPDX-License-Identifier: MIT"""

import pathlib
import socket
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "tools" / "spike-bluetooth-controller.py"


def receive_exact(connection, length):
    data = b""
    while len(data) < length:
        data += connection.recv(length - len(data))
    return data


class SocketTest(unittest.TestCase):
    def test_fragmented_h4_over_tcp(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            process = subprocess.Popen([
                sys.executable, str(CONTROLLER), "--acknowledge-vendor-commands",
                "127.0.0.1", str(listener.getsockname()[1]),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            connection, _ = listener.accept()
            with connection:
                connection.sendall(bytes.fromhex("0105"))
                connection.sendall(bytes.fromhex("ff01aa01030c00"))
                self.assertEqual(receive_exact(connection, 7), bytes.fromhex("040e040105ff00"))
                self.assertEqual(receive_exact(connection, 7), bytes.fromhex("040e0401030c00"))
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual((process.returncode, stdout, stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
