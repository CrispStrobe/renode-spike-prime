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


class RenodeModelObserver:
    """Read only public properties from the SPIKE models registered in a machine.

    `paths` is explicit because Prime and Essential have different platform
    topology. Missing models remain visible as limitations; they are never
    represented as working hardware.
    """

    def __init__(self, machine, identity: dict, paths: dict[str, str]):
        self.machine = machine
        self.identity = dict(identity)
        self.paths = dict(paths)
        self.generation = 0

    def _get(self, role):
        path = self.paths.get(role)
        if not path:
            return None
        try:
            return self.machine[path]
        except (KeyError, IndexError):
            return None

    def observe(self, seq: int, clock_ns: int) -> dict:
        power, imu, display, audio = (self._get(x) for x in
                                      ("power", "imu", "display", "audio"))
        ports, motors, sensors = [], [], []
        topology = []
        for port_id in "ABCDEF":
            port = self._get("port" + port_id)
            device = getattr(port, "Device", None) if port else None
            kind = self._device_kind(device)
            generation = int(getattr(port, "TopologyGeneration", 0)) if port else 0
            topology.append(generation)
            ports.append({"id": port_id, "attached": device is not None, "kind": kind})
            if kind == "motor":
                motors.append({"port": port_id, "speed": float(device.SpeedPercent),
                               "position": float(device.EncoderDegrees)})
            elif kind == "distance":
                sensors.append({"port": port_id, "kind": kind,
                                "values": {"distanceMillimeters": int(device.DistanceMillimeters)}})
            elif kind is not None:
                sensors.append({"port": port_id, "kind": kind, "values": {}})
        self.generation = max(topology, default=self.generation)
        registers = list(getattr(imu, "RegisterSnapshot", bytes(0)))
        def i16(offset):
            return int.from_bytes(bytes(registers[offset:offset + 2]), "little", signed=True) if len(registers) > offset + 1 else 0
        display_state = self._display_state(display)
        capabilities = ["model-observation", "bounded-command-dispatch"]
        limitations = ["display values are deterministic model output, not optical light physics"]
        if not any(self._get("port" + p) for p in "ABCDEF"):
            limitations.append("LPF2 ports are not present in this platform overlay")
        target = dict(self.identity)
        target["capabilities"] = capabilities
        target["limitations"] = limitations
        millivolts = int(getattr(power, "BatteryMillivolts", 0))
        percent = max(0, min(100, round((millivolts - 6000) / 24))) if power else 0
        return {"schemaVersion": 1, "type": "snapshot", "seq": seq,
                "clockNs": clock_ns, "target": target,
                "lifecycle": {"phase": "ready", "generation": self.generation},
                "ports": ports, "motors": motors, "sensors": sensors,
                "display": display_state,
                "buttons": {}, "battery": {"percent": percent, "millivolts": millivolts},
                "power": {"state": "on" if getattr(power, "PowerHold", False) else "off",
                          "chargerConnected": bool(getattr(power, "ChargerConnected", False))},
                "imu": {"acceleration": {"x": i16(0x28), "y": i16(0x2a), "z": i16(0x2c)},
                        "angularVelocity": {"x": i16(0x22), "y": i16(0x24), "z": i16(0x26)}},
                "audio": {"active": bool(getattr(audio, "Enabled", False)),
                          "bufferedBytes": int(getattr(audio, "BufferedBytes", 0))},
                "storage": {"ready": self._get("storage") is not None},
                "bluetooth": {"state": "modeled" if self._get("bluetooth") else "unavailable",
                              "transport": target["transport"]}}

    def dispatch(self, command: str, arguments: dict) -> None:
        if command == "power.set-battery-millivolts":
            value = self._bounded_int(arguments, "value", 0, 20000)
            self._require("power").SetBatteryMillivolts(value)
        elif command == "power.set-charger-connected":
            if not isinstance(arguments.get("connected"), bool):
                raise ProtocolError("connected must be boolean")
            self._require("power").SetChargerConnected(arguments["connected"])
        elif command == "imu.advance-sample":
            self._require("imu").AdvanceSample()
        elif command == "lpf2.attach":
            device = arguments.get("device")
            if device not in {"none", "ultrasonic", "medium-motor", "motor"}:
                raise ProtocolError("unsupported LPF2 device")
            self._require_port(arguments).Attach("motor" if device == "medium-motor" else device)
        elif command == "lpf2.detach":
            self._require_port(arguments).Detach()
        elif command == "lpf2.advance-microseconds":
            elapsed = self._bounded_int(arguments, "microseconds", 0, 60_000_000)
            self._require_port(arguments).AdvanceEmulatedTime(elapsed)
        else:
            raise ProtocolError("unknown command")

    def _require(self, role):
        model = self._get(role)
        if model is None:
            raise ProtocolError(f"capability unavailable: {role}")
        return model

    def _require_port(self, arguments):
        port = str(arguments.get("port", "")).upper()
        if port not in "ABCDEF" or len(port) != 1:
            raise ProtocolError("invalid LPF2 port")
        return self._require("port" + port)

    @staticmethod
    def _device_kind(device):
        if device is None:
            return None
        if hasattr(device, "SpeedPercent") and hasattr(device, "EncoderDegrees"):
            return "motor"
        if hasattr(device, "DistanceMillimeters"):
            return "distance"
        get_type = getattr(device, "GetType", None)
        name = str(get_type().Name if get_type else device.__class__.__name__)
        return "unknown:" + name[:48]

    @staticmethod
    def _display_state(display):
        if display is None:
            return {"width": 0, "height": 0, "pixels": [], "semantics": "unavailable"}
        if hasattr(display, "Matrix"):
            return {"width": 5, "height": 5, "pixels": list(display.Matrix),
                    "semantics": "grayscale-16bit"}
        if hasattr(display, "RenderedModuleSnapshot"):
            modules = [list(module) for module in display.RenderedModuleSnapshot]
            return {"width": 3, "height": len(modules),
                    "pixels": [component for module in modules for component in module],
                    "semantics": "rgb-components-8bit"}
        return {"width": 0, "height": 0, "pixels": [], "semantics": "unsupported-model"}

    @staticmethod
    def _bounded_int(arguments, name, minimum, maximum):
        value = arguments.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ProtocolError(f"{name} is outside the supported range")
        return value


class LiveStateSession:
    """One bounded transport session; socket implementations can wrap it."""

    def __init__(self, observer, queue_capacity=MAX_QUEUE_ITEMS):
        self.observer = observer
        self.queue = SnapshotQueue(queue_capacity)
        self.gate = CommandGate()
        self.connected = False
        self.connection_generation = 0
        self.next_seq = 0
        self.clock_ns = 0

    def connect(self):
        if self.connected:
            raise ProtocolError("session is already connected")
        self.connection_generation += 1
        self.connected = True

    def disconnect(self):
        self.connected = False

    def sample(self, clock_ns: int):
        if not self.connected:
            raise ProtocolError("session is disconnected")
        if clock_ns < self.clock_ns:
            raise ProtocolError("emulated clock moved backwards")
        self.clock_ns = clock_ns
        snapshot = self.observer.observe(self.next_seq, clock_ns)
        snapshot["lifecycle"]["connectionGeneration"] = self.connection_generation
        self.queue.publish(snapshot)
        self.next_seq += 1
        return snapshot

    def command(self, command: dict) -> dict:
        if not self.connected:
            raise ProtocolError("session is disconnected")
        self.gate.seq = self.next_seq - 1 if self.next_seq else 0
        result = self.gate.accept(command)
        if not result["accepted"]:
            return result
        try:
            self.observer.dispatch(command["command"], command["arguments"])
        except (KeyError, TypeError, ValueError, ProtocolError) as error:
            result["accepted"] = False
            result["error"] = str(error)
        return result
