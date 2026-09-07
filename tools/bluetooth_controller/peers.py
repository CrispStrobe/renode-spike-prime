"""Minimal deterministic ATT/GATT and RFCOMM peers.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Attribute:
    handle: int
    uuid: int | bytes
    value: bytes
    readable: bool = True
    writable: bool = False

    @property
    def uuid_bytes(self) -> bytes:
        return self.uuid.to_bytes(2, "little") if isinstance(self.uuid, int) else self.uuid


class AttGattServer:
    """Small ATT bearer supporting deterministic discovery, reads, and writes."""

    def __init__(self, attributes: list[Attribute] | None = None, mtu: int = 247) -> None:
        self.attributes = sorted(attributes or [], key=lambda attribute: attribute.handle)
        self.maximum_mtu = mtu
        self.negotiated_mtu = 23

    def receive(self, request: bytes) -> list[bytes]:
        if not request:
            return []
        opcode = request[0]
        if opcode == 0x02 and len(request) == 3:
            client_mtu = int.from_bytes(request[1:3], "little")
            self.negotiated_mtu = max(23, min(client_mtu, self.maximum_mtu))
            return [b"\x03" + self.maximum_mtu.to_bytes(2, "little")]
        if opcode == 0x0A and len(request) == 3:
            handle = int.from_bytes(request[1:3], "little")
            attribute = self._find(handle)
            if attribute is None or not attribute.readable:
                return [self._error(opcode, handle, 0x0A if attribute else 0x01)]
            return [b"\x0b" + attribute.value[: self.negotiated_mtu - 1]]
        if opcode in (0x12, 0x52) and len(request) >= 3:
            handle = int.from_bytes(request[1:3], "little")
            attribute = self._find(handle)
            if attribute is None or not attribute.writable:
                return [] if opcode == 0x52 else [self._error(opcode, handle, 0x03 if attribute else 0x01)]
            attribute.value = bytes(request[3:])
            return [] if opcode == 0x52 else [b"\x13"]
        if opcode == 0x08 and len(request) in (7, 21):
            return [self._read_by_type(request)]
        if opcode == 0x10 and len(request) == 7 and request[5:7] == b"\x00\x28":
            return [self._primary_services(request)]
        return [self._error(opcode, 0, 0x06)]

    def _find(self, handle: int) -> Attribute | None:
        return next((attribute for attribute in self.attributes if attribute.handle == handle), None)

    def _read_by_type(self, request: bytes) -> bytes:
        start, end, uuid = int.from_bytes(request[1:3], "little"), int.from_bytes(request[3:5], "little"), request[5:]
        matches = [a for a in self.attributes if start <= a.handle <= end and a.uuid_bytes == uuid and a.readable]
        if not matches:
            return self._error(0x08, start, 0x0A)
        value_size = min(len(matches[0].value), self.negotiated_mtu - 4)
        entries = b"".join(a.handle.to_bytes(2, "little") + a.value[:value_size]
                           for a in matches if len(a.value) >= value_size)
        return bytes([0x09, value_size + 2]) + entries[: self.negotiated_mtu - 2]

    def _primary_services(self, request: bytes) -> bytes:
        start, end = int.from_bytes(request[1:3], "little"), int.from_bytes(request[3:5], "little")
        services = [a for a in self.attributes if start <= a.handle <= end and a.uuid == 0x2800 and len(a.value) in (2, 16)]
        if not services:
            return self._error(0x10, start, 0x0A)
        value_size = len(services[0].value)
        entries = bytearray()
        for index, service in enumerate(services):
            if len(service.value) != value_size:
                break
            following = services[index + 1].handle - 1 if index + 1 < len(services) else self.attributes[-1].handle
            entries.extend(service.handle.to_bytes(2, "little") + following.to_bytes(2, "little") + service.value)
        return bytes([0x11, value_size + 4]) + bytes(entries[: self.negotiated_mtu - 2])

    @staticmethod
    def _error(opcode: int, handle: int, error: int) -> bytes:
        return bytes([0x01, opcode]) + handle.to_bytes(2, "little") + bytes([error])


class RfcommSession:
    """One RFCOMM DLCI with SABM/UA, DISC/UA, and UIH data delivery."""

    def __init__(self, dlci: int = 1, receive_data: Callable[[bytes], bytes | None] | None = None) -> None:
        if not 0 < dlci < 64:
            raise ValueError("RFCOMM DLCI must be between 1 and 63")
        self.dlci = dlci
        self.receive_data = receive_data or (lambda data: data)
        self.open = False

    def receive(self, frame: bytes) -> list[bytes]:
        if len(frame) < 4 or frame[0] >> 2 != self.dlci:
            return []
        length_octet = frame[2]
        if not length_octet & 1:
            return []
        length = length_octet >> 1
        if len(frame) != length + 4:
            return []
        control, data = frame[1] & 0xEF, frame[3:-1]
        if control == 0x2F:  # SABM
            self.open = True
            return [self._frame(0x63)]  # UA
        if control == 0x43:  # DISC
            self.open = False
            return [self._frame(0x63)]
        if control == 0xEF and self.open:  # UIH
            response = self.receive_data(data)
            return [] if response is None else [self._frame(0xEF, response)]
        return []

    def _frame(self, control: int, data: bytes = b"") -> bytes:
        address = (self.dlci << 2) | 3
        header = bytes([address, control, (len(data) << 1) | 1])
        fcs_input = header[:2] if control & 0xEF == 0xEF else header
        return header + data + bytes([_rfcomm_fcs(fcs_input)])


def _rfcomm_fcs(data: bytes) -> int:
    value = 0xFF
    for octet in data:
        value ^= octet
        for _ in range(8):
            value = (value >> 1) ^ (0xE0 if value & 1 else 0)
    return 0xFF - value
