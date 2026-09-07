"""Deterministic transport-neutral dual-mode Bluetooth controller.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .protocols import L2capRouter

FrameSink = Callable[[bytes], None]
H4_COMMAND, H4_ACL, H4_EVENT = 1, 2, 4
UNKNOWN_COMMAND, INVALID_PARAMETERS = 1, 0x12


@dataclass(frozen=True)
class ControllerConfig:
    address: bytes = bytes.fromhex("060504030201")
    acknowledge_vendor_commands: bool = False
    acl_payload_size: int = 1021
    acl_packets: int = 8
    h4_input_limit: int = 65540
    l2cap_reassembly_limit: int = 65539

    def __post_init__(self) -> None:
        if len(self.address) != 6:
            raise ValueError("Bluetooth address must contain exactly six bytes")
        if not 1 <= self.acl_payload_size <= 0xFFFF or not 1 <= self.acl_packets <= 0xFFFF:
            raise ValueError("ACL capacity must be nonzero and fit the HCI response")
        if self.h4_input_limit < 5 or self.l2cap_reassembly_limit < 4:
            raise ValueError("stream limits are too small for protocol headers")


class BluetoothController:
    """H4/HCI core whose only dependency is a complete-frame output callback."""

    def __init__(self, sink: FrameSink, config: ControllerConfig | None = None) -> None:
        self.sink = sink
        self.config = config or ControllerConfig()
        self.l2cap = L2capRouter()
        self._input = bytearray()
        self.reset_state()

    def reset_state(self) -> None:
        self.advertising = False
        self.advertising_data = b""
        self.scan_response_data = b""
        self.classic_connectable = False
        self.connected = False
        self.classic = False
        self.handle = 1
        self.peer_address = bytes(6)
        self._acl_fragments = bytearray()

    def feed(self, data: bytes) -> None:
        """Incrementally consume any number of H4 commands or ACL frames."""
        self._input.extend(data)
        if len(self._input) > self.config.h4_input_limit:
            self._input.clear()
            raise ValueError("H4 input exceeds configured resource limit")
        while self._input:
            packet_type = self._input[0]
            if packet_type == H4_COMMAND:
                if len(self._input) < 4:
                    return
                frame_length = 4 + self._input[3]
            elif packet_type == H4_ACL:
                if len(self._input) < 5:
                    return
                frame_length = 5 + int.from_bytes(self._input[3:5], "little")
            else:
                del self._input[0]
                raise ValueError(f"unsupported host H4 packet type 0x{packet_type:02x}")
            if len(self._input) < frame_length:
                return
            frame = bytes(self._input[1:frame_length])
            del self._input[:frame_length]
            self._command(frame) if packet_type == H4_COMMAND else self._acl(frame)

    def _emit(self, packet_type: int, payload: bytes) -> None:
        self.sink(bytes([packet_type]) + payload)

    def _complete(self, opcode: int, status: int = 0, result: bytes = b"") -> None:
        parameters = bytes([1]) + opcode.to_bytes(2, "little") + bytes([status]) + result
        self._emit(H4_EVENT, bytes([0x0E, len(parameters)]) + parameters)

    def _status(self, opcode: int, status: int = 0) -> None:
        self._emit(H4_EVENT, bytes([0x0F, 4, status, 1]) + opcode.to_bytes(2, "little"))

    def _command(self, frame: bytes) -> None:
        opcode = int.from_bytes(frame[0:2], "little")
        parameters = frame[3:]
        if opcode & 0xFC00 == 0xFC00:
            self._complete(opcode, 0 if self.config.acknowledge_vendor_commands else UNKNOWN_COMMAND)
            return
        if opcode == 0x0C03 and not parameters:
            self.reset_state()
            self._complete(opcode)
            return
        empty_results = {
            0x1002: bytes(64), 0x1003: bytes([0, 0, 0, 0, 0x40, 0, 0, 0]),
            0x1001: bytes([0x08, 1, 0, 0x08, 0x98, 0x05, 1, 0]),
            0x1005: self.config.acl_payload_size.to_bytes(2, "little") + b"\0" + self.config.acl_packets.to_bytes(2, "little") + b"\0\0",
            0x1009: self.config.address,
            0x2002: min(self.config.acl_payload_size, 0xFB).to_bytes(2, "little") + bytes([min(self.config.acl_packets, 0xFF)]),
            0x2003: bytes(8), 0x080E: b"\0\0", 0x0C23: bytes([0, 8, 0]),
        }
        if opcode in empty_results:
            self._complete(opcode, INVALID_PARAMETERS if parameters else 0,
                           b"" if parameters else empty_results[opcode])
            return
        lengths = {0x0C01: 8, 0x2001: 8, 0x0C6D: 2, 0x0C56: 1,
                   0x0C45: 1, 0x0C18: 2, 0x080F: 2, 0x0C24: 3,
                   0x0C13: 248, 0x2006: 15}
        if opcode in lengths:
            self._complete(opcode, 0 if len(parameters) == lengths[opcode] else INVALID_PARAMETERS)
            return
        if opcode in (0x2008, 0x2009):
            valid = len(parameters) == 32 and parameters[0] <= 31
            if valid:
                value = parameters[1:1 + parameters[0]]
                if opcode == 0x2008:
                    self.advertising_data = value
                else:
                    self.scan_response_data = value
            self._complete(opcode, 0 if valid else INVALID_PARAMETERS)
            return
        if opcode == 0x200A:
            valid = len(parameters) == 1 and parameters[0] <= 1
            if valid:
                self.advertising = bool(parameters[0])
            self._complete(opcode, 0 if valid else INVALID_PARAMETERS)
            return
        if opcode == 0x0C1A:
            valid = len(parameters) == 1 and parameters[0] <= 3
            if valid:
                self.classic_connectable = bool(parameters[0] & 2)
            self._complete(opcode, 0 if valid else INVALID_PARAMETERS)
            return
        if opcode == 0x0409 and len(parameters) == 7 and not self.connected and parameters[:6] == self.peer_address:
            self._status(opcode)
            self.connected, self.classic = True, True
            body = b"\0" + self.handle.to_bytes(2, "little") + self.peer_address + b"\x01\0"
            self._emit(H4_EVENT, bytes([0x03, len(body)]) + body)
            return
        self._complete(opcode, UNKNOWN_COMMAND)

    def _acl(self, frame: bytes) -> None:
        handle_flags = int.from_bytes(frame[0:2], "little")
        handle, boundary = handle_flags & 0x0FFF, (handle_flags >> 12) & 3
        payload = frame[4:]
        if not self.connected or handle != self.handle:
            raise ValueError("ACL packet uses an inactive connection handle")
        if boundary in (0, 2):
            self._acl_fragments = bytearray(payload)
        elif boundary == 1:
            self._acl_fragments.extend(payload)
        else:
            raise ValueError("reserved ACL packet-boundary flag")
        if len(self._acl_fragments) > self.config.l2cap_reassembly_limit:
            self._acl_fragments.clear()
            raise ValueError("L2CAP reassembly exceeds configured resource limit")
        if len(self._acl_fragments) >= 4:
            expected = int.from_bytes(self._acl_fragments[:2], "little") + 4
            if len(self._acl_fragments) > expected:
                raise ValueError("ACL fragments exceed one L2CAP packet")
            if len(self._acl_fragments) == expected:
                for response in self.l2cap.receive(bytes(self._acl_fragments)):
                    self.send_acl(response)
                self._acl_fragments.clear()
        completed = bytes([1]) + self.handle.to_bytes(2, "little") + b"\x01\0"
        self._emit(H4_EVENT, bytes([0x13, len(completed)]) + completed)

    def connect_le(self, peer_address: bytes) -> None:
        if len(peer_address) != 6 or not self.advertising or self.connected:
            raise ValueError("LE connection requires advertising and a six-byte peer")
        self.connected, self.classic, self.advertising = True, False, False
        self.peer_address = bytes(peer_address)
        body = bytes([1, 0]) + self.handle.to_bytes(2, "little") + b"\x01\0" + self.peer_address + bytes.fromhex("18000000f40100")
        self._emit(H4_EVENT, bytes([0x3E, len(body)]) + body)

    def request_classic_connection(self, peer_address: bytes) -> None:
        if len(peer_address) != 6 or not self.classic_connectable or self.connected:
            raise ValueError("Classic request requires page scan and a six-byte peer")
        self.peer_address = bytes(peer_address)
        body = self.peer_address + bytes([0, 8, 0, 1])
        self._emit(H4_EVENT, bytes([0x04, len(body)]) + body)

    def disconnect(self, reason: int = 0x13) -> None:
        if not self.connected:
            raise ValueError("no active connection")
        body = b"\0" + self.handle.to_bytes(2, "little") + bytes([reason])
        self.connected = self.classic = False
        self._acl_fragments.clear()
        self._emit(H4_EVENT, bytes([0x05, len(body)]) + body)

    def send_acl(self, l2cap_packet: bytes) -> None:
        if not self.connected or len(l2cap_packet) > self.config.acl_payload_size:
            raise ValueError("ACL response requires an active connection and available capacity")
        header = (self.handle | 0x2000).to_bytes(2, "little") + len(l2cap_packet).to_bytes(2, "little")
        self._emit(H4_ACL, header + l2cap_packet)
