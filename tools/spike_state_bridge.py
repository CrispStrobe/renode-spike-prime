#!/usr/bin/env python3
"""Bounded NDJSON boundary between Renode-facing code and Brickwright clients."""

from __future__ import annotations

import json
from collections import deque

SCHEMA_VERSION = 1
MAX_LINE_BYTES = 256 * 1024
MAX_QUEUE_ITEMS = 256
FIRMWARE_BY_BOARD = {
    "spike-prime": {"lego-prime-v2", "lego-prime-v3", "pybricks-prime",
                    "spike-nx", "brickwright-nuttx"},
    "spike-essential": {"lego-essential", "pybricks-essential"},
}


class ProtocolError(ValueError):
    pass


def canonical_bytes(message: dict) -> bytes:
    validate_message(message)
    try:
        encoded = json.dumps(message, ensure_ascii=True, allow_nan=False,
                             separators=(",", ":"), sort_keys=True).encode("ascii")
    except (TypeError, ValueError) as error:
        raise ProtocolError("message is not safely serializable") from error
    if len(encoded) > MAX_LINE_BYTES:
        raise ProtocolError("message exceeds line limit")
    return encoded


def parse_line(line: bytes | str) -> dict:
    raw = line.encode("utf-8") if isinstance(line, str) else line
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or len(raw) > MAX_LINE_BYTES or b"\n" in raw or b"\r" in raw:
        raise ProtocolError("invalid NDJSON line size or framing")
    try:
        message = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("invalid JSON") from error
    validate_message(message)
    return message


def _required(message: dict, names: tuple[str, ...]) -> None:
    missing = [name for name in names if name not in message]
    if missing:
        raise ProtocolError("missing required fields: " + ", ".join(missing))


def validate_message(message: dict) -> None:
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    if message.get("schemaVersion") != SCHEMA_VERSION:
        raise ProtocolError("unsupported schemaVersion")
    kind = message.get("type")
    if kind == "snapshot":
        _required(message, ("seq", "clockNs", "target", "lifecycle", "ports",
                            "motors", "sensors", "display", "buttons", "battery",
                            "power", "imu", "audio", "storage", "bluetooth"))
        if not isinstance(message["seq"], int) or message["seq"] < 0:
            raise ProtocolError("seq must be a non-negative integer")
        target = message["target"]
        if not isinstance(target, dict):
            raise ProtocolError("target must be an object")
        _required(target, ("board", "firmware", "transport", "imageSha256",
                           "capabilities", "limitations"))
        if target.get("firmware") not in FIRMWARE_BY_BOARD.get(target.get("board"), set()):
            raise ProtocolError("unsupported board/firmware identity")
        display = message["display"]
        if not isinstance(display, dict) or len(display.get("pixels", [])) > 4096:
            raise ProtocolError("invalid display")
        for name in ("ports", "motors", "sensors"):
            if not isinstance(message[name], list) or len(message[name]) > 16:
                raise ProtocolError(f"invalid {name}")
    elif kind == "command":
        _required(message, ("requestId", "command", "arguments"))
        if not isinstance(message["requestId"], str) or not message["requestId"]:
            raise ProtocolError("invalid requestId")
        if "expectedSeq" in message and (not isinstance(message["expectedSeq"], int)
                                         or message["expectedSeq"] < 0):
            raise ProtocolError("invalid expectedSeq")
        if (not isinstance(message["command"], str) or not message["command"] or
                not isinstance(message["arguments"], dict)):
            raise ProtocolError("invalid command")
    elif kind == "result":
        _required(message, ("requestId", "accepted"))
        if not isinstance(message["requestId"], str) or not isinstance(message["accepted"], bool):
            raise ProtocolError("invalid result")
    elif kind == "gap":
        _required(message, ("firstDroppedSeq", "nextSeq", "dropped"))
        if (message["dropped"] < 1 or
                message["nextSeq"] != message["firstDroppedSeq"] + message["dropped"]):
            raise ProtocolError("invalid gap")
    else:
        raise ProtocolError("unknown message type")


class SnapshotQueue:
    """Bounded producer queue which makes every overflow observable."""

    def __init__(self, capacity: int = MAX_QUEUE_ITEMS):
        if capacity < 2 or capacity > MAX_QUEUE_ITEMS:
            raise ValueError("capacity must be between 2 and MAX_QUEUE_ITEMS")
        self._items = deque(maxlen=capacity)
        self._last_seq = None
        self._dropped = 0
        self._first_dropped = None

    def publish(self, snapshot: dict) -> None:
        validate_message(snapshot)
        if snapshot["type"] != "snapshot":
            raise ProtocolError("queue accepts snapshots only")
        seq = snapshot["seq"]
        if self._last_seq is not None and seq != self._last_seq + 1:
            raise ProtocolError("snapshot sequence is not contiguous")
        self._last_seq = seq
        if len(self._items) == self._items.maxlen:
            dropped = self._items.popleft()
            self._first_dropped = dropped["seq"] if self._first_dropped is None else self._first_dropped
            self._dropped += 1
        self._items.append(snapshot)

    def drain(self) -> list[dict]:
        result = []
        if self._dropped:
            first = self._items[0]["seq"]
            result.append({"schemaVersion": 1, "type": "gap",
                           "firstDroppedSeq": self._first_dropped,
                           "nextSeq": first, "dropped": self._dropped})
        result.extend(self._items)
        self._items.clear()
        self._dropped = 0
        self._first_dropped = None
        return result


class CommandGate:
    """Reject stale and replayed control requests before emulator dispatch."""

    def __init__(self, request_window: int = MAX_QUEUE_ITEMS):
        self.seq = 0
        self._seen = deque(maxlen=request_window)

    def accept(self, command: dict) -> dict:
        validate_message(command)
        request_id = command["requestId"]
        if request_id in self._seen:
            return self._result(request_id, False, "duplicate requestId")
        self._seen.append(request_id)
        if command.get("expectedSeq", self.seq) != self.seq:
            return self._result(request_id, False, "expectedSeq mismatch")
        self.seq += 1
        return self._result(request_id, True)

    def _result(self, request_id: str, accepted: bool, error: str | None = None) -> dict:
        result = {"schemaVersion": 1, "type": "result", "requestId": request_id,
                  "accepted": accepted, "seq": self.seq}
        if error:
            result["error"] = error
        return result
