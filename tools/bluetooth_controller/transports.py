"""Byte-stream adapters for the transport-neutral controller.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import socket


class MemoryTransport:
    """Collects complete H4 frames for deterministic tests and embedding."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def send(self, frame: bytes) -> None:
        self.frames.append(bytes(frame))


class SocketTransport:
    """Writes complete frames to a connected stream socket."""

    def __init__(self, connection: socket.socket) -> None:
        self.connection = connection

    def send(self, frame: bytes) -> None:
        self.connection.sendall(frame)
