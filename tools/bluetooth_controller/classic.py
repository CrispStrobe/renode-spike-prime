"""Classic Bluetooth L2CAP signaling and SDP channel establishment.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocols import AclProtocol, L2capChannel, L2capReply, L2capRouter


@dataclass
class _DynamicChannel:
    remote_cid: int
    protocol: AclProtocol

    def receive(self, payload: bytes) -> list[L2capReply]:
        return [L2capReply(self.remote_cid, response) for response in self.protocol.receive(payload)]


class SdpServer:
    """Deterministic SDP ServiceSearchAttribute responder.

    ``attribute_list`` is an encoded SDP data element sequence chosen by the
    embedding application. This keeps LEGO-specific UUIDs and records outside
    the generic controller.
    """

    def __init__(self, attribute_list: bytes = b"\x35\x00") -> None:
        self.attribute_list = bytes(attribute_list)

    def receive(self, request: bytes) -> list[bytes]:
        if len(request) < 5:
            return []
        pdu, transaction = request[0], request[1:3]
        size = int.from_bytes(request[3:5], "big")
        if len(request) != size + 5:
            return []
        if pdu != 0x06:
            parameters = b"\x00\x03"  # invalid request syntax
            return [b"\x01" + transaction + len(parameters).to_bytes(2, "big") + parameters]
        parameters = len(self.attribute_list).to_bytes(2, "big") + self.attribute_list + b"\x00"
        return [b"\x07" + transaction + len(parameters).to_bytes(2, "big") + parameters]


class ClassicL2capSignaling:
    """Establishes basic-mode SDP (PSM 1) and RFCOMM (PSM 3) channels."""

    def __init__(self, router: L2capRouter, rfcomm: AclProtocol,
                 sdp: AclProtocol | None = None, first_dynamic_cid: int = 0x0040) -> None:
        self.router = router
        self.protocols = {1: sdp or SdpServer(), 3: rfcomm}
        self.next_cid = first_dynamic_cid
        self.channels: dict[int, int] = {}

    def receive(self, payload: bytes) -> list[bytes]:
        responses = []
        offset = 0
        while offset + 4 <= len(payload):
            code, identifier = payload[offset], payload[offset + 1]
            length = int.from_bytes(payload[offset + 2:offset + 4], "little")
            data = payload[offset + 4:offset + 4 + length]
            if len(data) != length:
                return []
            response = self._command(code, identifier, data)
            if response:
                responses.append(response)
            offset += 4 + length
        return responses if offset == len(payload) else []

    def _command(self, code: int, identifier: int, data: bytes) -> bytes | None:
        if code == 0x02 and len(data) == 4:  # Connection Request
            psm, remote_cid = int.from_bytes(data[:2], "little"), int.from_bytes(data[2:], "little")
            protocol = self.protocols.get(psm)
            if protocol is None:
                result, local_cid = 0x0002, 0  # PSM not supported
            else:
                local_cid, result = self.next_cid, 0
                self.next_cid += 1
                self.channels[local_cid] = remote_cid
                self.router.bind(L2capChannel(local_cid, _DynamicChannel(remote_cid, protocol)))
            body = local_cid.to_bytes(2, "little") + remote_cid.to_bytes(2, "little") + result.to_bytes(2, "little") + b"\0\0"
            return self._response(0x03, identifier, body)
        if code == 0x04 and len(data) >= 4:  # Configuration Request
            local_cid = int.from_bytes(data[:2], "little")
            remote_cid = self.channels.get(local_cid)
            if remote_cid is None:
                return self._response(0x01, identifier, b"\x02\0")
            return self._response(0x05, identifier, remote_cid.to_bytes(2, "little") + b"\0\0\0\0")
        if code == 0x06 and len(data) == 4:  # Disconnection Request
            local_cid, remote_cid = int.from_bytes(data[:2], "little"), int.from_bytes(data[2:], "little")
            if self.channels.get(local_cid) == remote_cid:
                self.router.unbind(local_cid)
                del self.channels[local_cid]
            return self._response(0x07, identifier, data)
        return self._response(0x01, identifier, b"\0\0")

    @staticmethod
    def _response(code: int, identifier: int, data: bytes) -> bytes:
        return bytes([code, identifier]) + len(data).to_bytes(2, "little") + data
