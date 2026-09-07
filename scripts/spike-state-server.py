"""Opt-in IronPython 2 monitor service for neutral SPIKE state.

Include this file, then run ``spike_state_start 127.0.0.1 8765 @config.json``.
Including it never opens a listener, and no general monitor command is exposed.
"""

import json
from System import Array, Byte
from System.Net import IPAddress
from System.Net.Sockets import TcpListener
from System.Text import Encoding
from System.Threading import Thread
from threading import Lock, RLock

_state_server = None
_MAX_LINE, _READ_SIZE = 256 * 1024, 16 * 1024


def _resolve(path):
    if path.startswith("external:"):
        return externals[path[9:]]
    return monitor.Machine[path[8:] if path.startswith("machine:") else path]


def _optional(paths, role):
    try:
        return _resolve(paths[role]) if role in paths else None
    except:
        return None


def _kind(device):
    if device is None:
        return None
    if hasattr(device, "SpeedPercent") and hasattr(device, "EncoderDegrees"):
        return "motor"
    if hasattr(device, "DistanceMillimeters"):
        return "distance"
    return "unknown:" + device.GetType().Name[:48]


def _snapshot(config, seq, generation):
    paths, ports, motors, sensors, topology = config["paths"], [], [], [], 0
    for port_id in "ABCDEF":
        port = _optional(paths, "port" + port_id)
        device = port.Device if port is not None else None
        kind = _kind(device)
        if port is not None:
            topology = max(topology, int(port.TopologyGeneration))
        ports.append({"id": port_id, "attached": device is not None, "kind": kind})
        if kind == "motor":
            motors.append({"port": port_id, "speed": float(device.SpeedPercent),
                           "position": float(device.EncoderDegrees)})
        elif kind == "distance":
            sensors.append({"port": port_id, "kind": kind,
                            "values": {"distanceMillimeters": int(device.DistanceMillimeters)}})
    display, pixels, width, height, semantics = _optional(paths, "display"), [], 0, 0, "unavailable"
    if display is not None and hasattr(display, "Matrix"):
        pixels, width, height, semantics = list(display.Matrix), 5, 5, "grayscale-16bit"
    elif display is not None and hasattr(display, "RenderedModuleSnapshot"):
        modules = [list(module) for module in display.RenderedModuleSnapshot]
        pixels = [value for module in modules for value in module]
        width, height, semantics = 3, len(modules), "rgb-components-8bit"
    power = _optional(paths, "power")
    millivolts = int(power.BatteryMillivolts) if power is not None else 0
    identity = dict(config["identity"])
    identity["capabilities"] = ["model-observation", "bounded-command-dispatch"]
    identity["limitations"] = ["state is model output, not physical hardware"]
    clock = int(emulationManager.CurrentEmulation.MasterTimeSource.ElapsedVirtualTime.Ticks) * 100
    return {"schemaVersion": 1, "type": "snapshot", "seq": seq, "clockNs": clock,
            "target": identity, "lifecycle": {"phase": "ready", "generation": topology,
            "connectionGeneration": generation}, "ports": ports, "motors": motors,
            "sensors": sensors, "display": {"width": width, "height": height,
            "pixels": pixels, "semantics": semantics}, "buttons": {},
            "battery": {"percent": max(0, min(100, round((millivolts - 6000) / 24))),
            "millivolts": millivolts}, "power": {"state": "on" if power is not None and
            power.PowerHold else "off", "chargerConnected": bool(power is not None and
            power.ChargerConnected)}, "imu": {"acceleration": {"x": 0, "y": 0, "z": 0},
            "angularVelocity": {"x": 0, "y": 0, "z": 0}}, "audio": {"active": False,
            "bufferedBytes": 0}, "storage": {"ready": _optional(paths, "storage") is not None},
            "bluetooth": {"state": "modeled" if _optional(paths, "bluetooth") is not None
            else "unavailable", "transport": identity["transport"]}}


def _dispatch(config, command):
    paths, name, args = config["paths"], command["command"], command["arguments"]
    if name == "power.set-battery-millivolts":
        value = args.get("value")
        if not isinstance(value, (int, long)) or isinstance(value, bool) or not 0 <= value <= 20000:
            raise ValueError("value is outside the supported range")
        _resolve(paths["power"]).SetBatteryMillivolts(value)
    elif name == "power.set-charger-connected":
        if not isinstance(args.get("connected"), bool):
            raise ValueError("connected must be boolean")
        _resolve(paths["power"]).SetChargerConnected(args["connected"])
    elif name == "imu.advance-sample":
        _resolve(paths["imu"]).AdvanceSample()
    elif name in ("lpf2.detach", "lpf2.attach", "lpf2.advance-microseconds"):
        port = str(args.get("port", "")).upper()
        if len(port) != 1 or port not in "ABCDEF":
            raise ValueError("invalid LPF2 port")
        model = _resolve(paths["port" + port])
        if name == "lpf2.detach":
            model.Detach()
        elif name == "lpf2.attach":
            device = args.get("device")
            if device not in ("none", "ultrasonic", "medium-motor", "motor"):
                raise ValueError("unsupported LPF2 device")
            model.Attach("motor" if device == "medium-motor" else device)
        else:
            elapsed = args.get("microseconds")
            if not isinstance(elapsed, (int, long)) or isinstance(elapsed, bool) or not 0 <= elapsed <= 60000000:
                raise ValueError("microseconds is outside the supported range")
            model.AdvanceEmulatedTime(elapsed)
    else:
        raise ValueError("unknown command")


class _Server(object):
    def __init__(self, host, port, config):
        address, clients = IPAddress.Parse(host), int(config.get("maxClients", 1))
        self.limit, self.timeout = int(config.get("maxLineBytes", _MAX_LINE)), int(float(config.get("socketTimeoutSeconds", 5)) * 1000)
        if not IPAddress.IsLoopback(address):
            raise ValueError("the monitor service binds loopback only")
        if port < 1 or port > 65535 or clients != 1 or self.limit < 256 or self.limit > _MAX_LINE or self.timeout < 50 or self.timeout > 60000:
            raise ValueError("endpoint or resource limit is outside the supported range")
        self.config, self.running, self.generation = config, True, 0
        self.stream, self.seq, self.write_lock, self.state_lock = None, 0, Lock(), RLock()
        self.listener = TcpListener(address, port)
        self.listener.Start(clients)
        self.thread = Thread(self._run); self.thread.IsBackground = True; self.thread.Start()

    def close(self):
        self.running = False; self.listener.Stop()

    def _send(self, stream, message):
        wire = Encoding.UTF8.GetBytes(json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n")
        if wire.Length > self.limit:
            raise ValueError("outbound line exceeds configured limit")
        with self.write_lock:
            stream.Write(wire, 0, wire.Length)

    def _synchronized(self, callback):
        paused = monitor.Machine.ObtainPausedState(True)
        try:
            return callback()
        finally:
            paused.Dispose()

    def sample(self):
        with self.state_lock:
            if self.stream is None:
                return False
            snapshot = self._synchronized(lambda: _snapshot(self.config, self.seq, self.generation))
            self._send(self.stream, snapshot)
            self.seq += 1
            return True

    def _run(self):
        while self.running:
            try:
                client = self.listener.AcceptTcpClient()
            except:
                if self.running: continue
                break
            self.generation += 1
            try: self._client(client, self.generation)
            except: pass
            self.stream = None
            client.Close()

    def _client(self, client, generation):
        stream, pending, seen = client.GetStream(), "", []
        self.stream, self.seq = stream, 0
        stream.ReadTimeout, stream.WriteTimeout = self.timeout, self.timeout
        self.sample()
        buffer = Array.CreateInstance(Byte, _READ_SIZE)
        while self.running:
            count = stream.Read(buffer, 0, buffer.Length)
            if count == 0: return
            pending += Encoding.UTF8.GetString(buffer, 0, count)
            if Encoding.UTF8.GetByteCount(pending) > self.limit: return
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                if not line or "\r" in line or Encoding.UTF8.GetByteCount(line) > self.limit: return
                command, accepted, error = json.loads(line), True, None
                request = command.get("requestId", "invalid")
                if command.get("schemaVersion") != 1 or command.get("type") != "command": accepted, error = False, "invalid command envelope"
                elif request in seen or command.get("expectedSeq", self.seq - 1) != self.seq - 1: accepted, error = False, "duplicate requestId or expectedSeq mismatch"
                else:
                    seen.append(request)
                    if len(seen) > 256: seen.pop(0)
                    try: self._synchronized(lambda: _dispatch(self.config, command))
                    except Exception as exception: accepted, error = False, str(exception)
                result = {"schemaVersion": 1, "type": "result", "requestId": request, "accepted": accepted, "seq": self.seq - 1}
                if error is not None: result["error"] = error
                self._send(stream, result); self.sample()


def mc_spike_state_start(host, port, config_path):
    global _state_server
    if _state_server is not None: raise RuntimeError("SPIKE state server is already running")
    with open(str(config_path).lstrip("@"), "r") as stream: config = json.load(stream)
    _state_server = _Server(str(host), int(port), config)
    print("SPIKE state server listening on {0}:{1}".format(host, port))


def mc_spike_state_stop():
    global _state_server
    if _state_server is not None: _state_server.close(); _state_server = None


def mc_spike_state_sample():
    if _state_server is None or not _state_server.sample():
        raise RuntimeError("SPIKE state server has no connected client")
