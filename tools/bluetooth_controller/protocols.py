"""Protocol extension contracts for the simulated controller.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AclProtocol(Protocol):
    """Consumes one complete L2CAP payload and optionally returns responses."""

    def receive(self, payload: bytes) -> list[bytes]:
        """Return zero or more complete response payloads."""


@dataclass(frozen=True)
class L2capChannel:
    """A fixed L2CAP channel binding."""

    cid: int
    protocol: AclProtocol


class L2capRouter:
    """Routes complete basic-mode L2CAP packets without knowing the transport."""

    def __init__(self) -> None:
        self._channels: dict[int, AclProtocol] = {}

    def bind(self, channel: L2capChannel) -> None:
        if not 0 < channel.cid <= 0xFFFF:
            raise ValueError("L2CAP CID must be between 1 and 65535")
        if channel.cid in self._channels:
            raise ValueError(f"L2CAP CID 0x{channel.cid:04x} is already bound")
        self._channels[channel.cid] = channel.protocol

    def receive(self, packet: bytes) -> list[bytes]:
        if len(packet) < 4:
            raise ValueError("truncated L2CAP header")
        length = int.from_bytes(packet[0:2], "little")
        cid = int.from_bytes(packet[2:4], "little")
        if len(packet) != length + 4:
            raise ValueError("L2CAP length does not match packet")
        protocol = self._channels.get(cid)
        if protocol is None:
            return []
        return [self.frame(cid, payload) for payload in protocol.receive(packet[4:])]

    @staticmethod
    def frame(cid: int, payload: bytes) -> bytes:
        return len(payload).to_bytes(2, "little") + cid.to_bytes(2, "little") + payload
