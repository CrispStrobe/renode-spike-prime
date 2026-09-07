#!/usr/bin/env python3
"""Run the deterministic controller against a raw H4 TCP terminal.

SPDX-License-Identifier: MIT
"""

import argparse
import pathlib
import socket
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bluetooth_controller import BluetoothController, ControllerConfig
from bluetooth_controller.transports import SocketTransport


def connect_retry(host: str, port: int, attempts: int) -> socket.socket:
    last_error = None
    for _ in range(attempts):
        try:
            return socket.create_connection((host, port), timeout=1)
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise ConnectionError(f"cannot connect to {host}:{port}") from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--address", default="060504030201", help="six-byte controller address in HCI byte order")
    parser.add_argument("--acknowledge-vendor-commands", action="store_true")
    parser.add_argument("--connect-attempts", type=int, default=100)
    arguments = parser.parse_args()
    try:
        address = bytes.fromhex(arguments.address)
        connection = connect_retry(arguments.host, arguments.port, arguments.connect_attempts)
        with connection:
            controller = BluetoothController(
                SocketTransport(connection).send,
                ControllerConfig(address, arguments.acknowledge_vendor_commands),
            )
            while data := connection.recv(4096):
                controller.feed(data)
    except (OSError, ValueError, ConnectionError) as error:
        print(f"controller: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
