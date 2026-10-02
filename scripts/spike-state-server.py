"""Opt-in IronPython 2 monitor service for neutral SPIKE state.

Include this file, then run ``spike_state_start 127.0.0.1 8765 @config.json``.
Including it never opens a listener, and no general monitor command is exposed.
"""

import json
import os
import sys
import clr
clr.AddReference("System.Net.Primitives")
clr.AddReference("System.Net.Sockets")
from System import Array, Byte
from System.Net import IPAddress
from System.Net.Sockets import SocketOptionLevel, SocketOptionName, TcpListener
from System.Text import Encoding
from System.Threading import Thread, ThreadStart
from threading import Lock, RLock

_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _tools not in sys.path:
    sys.path.insert(0, _tools)
from spike_state_monitor_protocol import split_frames, validate_command, validate_config
import ev3_state_observer
from spike_arena_inputs import apply_arena_inputs
import spike_arena_mailbox
import spike_nuttx_mailbox

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
    if hasattr(device, "ColorId"):
        return "color"
    if hasattr(device, "ForcePercent"):
        return "force"
    if hasattr(device, "DistanceMillimeters"):
        return "distance"
    return "unknown:" + device.GetType().Name[:48]


def _snapshot(config, seq, generation):
    if config["identity"].get("firmware") == "brickwright-arena-demo":
        bus = monitor.Machine.SystemBus
        try:
            data = spike_arena_mailbox.read_state(lambda address, count: bus.ReadBytes(address, count), bus.ReadDoubleWord)
        except ValueError as error:
            if str(error) != 'arena guest frame changed during observation': raise
            # Timer-driven programs can change during all bounded optimistic reads.
            # A pause can land inside the guest's publication interrupt, with
            # its output sequence still odd. Release between bounded attempts
            # so normal execution can finish publishing. Never step guest time,
            # issue a GDB halt, or accept an incomplete/mixed frame.
            for attempt in range(3):
                paused = monitor.Machine.ObtainPausedState(True)
                try:
                    try:
                        data = spike_arena_mailbox.read_state(lambda address, count: bus.ReadBytes(address, count), bus.ReadDoubleWord)
                        break
                    except ValueError as retry_error:
                        if str(retry_error) != 'arena guest frame changed during observation' or attempt == 2: raise
                finally:
                    paused.Dispose()
                Thread.Sleep(1)
        return spike_arena_mailbox.snapshot(data, config["identity"], seq, generation)
    if config["identity"]["board"] == "ev3":
        clock = int(emulationManager.CurrentEmulation.MasterTimeSource.ElapsedVirtualTime.Ticks) * 100
        return ev3_state_observer.observe(config, _resolve, seq, clock, generation)
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
                           "position": float(device.PositionDegrees if hasattr(device, "PositionDegrees") else device.EncoderDegrees),
                           "speedDps": float(device.AngularVelocityDegreesPerSecond), "stalled": bool(device.Stalled),
                           "demandDirection": -1 if device.Power < 0 else int(device.Power > 0)})
        elif kind == "distance":
            sensors.append({"port": port_id, "kind": kind,
                            "values": {"distanceMillimeters": int(device.DistanceMillimeters)}})
        elif kind == "color":
            sensors.append({"port": port_id, "kind": kind, "values": {
                "colorId": int(device.ColorId), "reflectionPercent": int(device.ReflectionPercent),
                "ambientPercent": int(device.AmbientPercent)}})
        elif kind == "force":
            sensors.append({"port": port_id, "kind": kind, "values": {
                "forcePercent": int(device.ForcePercent), "pressed": bool(device.Pressed)}})
    display, pixels, width, height, semantics = _optional(paths, "display"), [], 0, 0, "unavailable"
    if display is not None and hasattr(display, "Matrix"):
        pixels, width, height, semantics = [int(value) for value in display.Matrix], 5, 5, "grayscale-16bit"
    elif display is not None and hasattr(display, "RenderedModuleSnapshot"):
        modules = [[int(value) for value in module] for module in display.RenderedModuleSnapshot]
        pixels = [value for module in modules for value in module]
        width, height, semantics = 3, len(modules), "rgb-components-8bit"
    power = _optional(paths, "power")
    millivolts = int(power.BatteryMillivolts) if power is not None else 0
    identity = dict(config["identity"])
    identity["capabilities"] = ["model-observation", "bounded-command-dispatch", "state-sample/v1"]
    if identity.get("firmware") == "brickwright-nuttx" and identity.get("transport") == "none" and any(_optional(paths, "port" + p) is not None for p in "ABCDEF"):
        identity["capabilities"].append("arena-inputs/v1")
    lifecycle = {"phase": "ready", "generation": topology, "connectionGeneration": generation}
    if identity.get("firmware") == "brickwright-nuttx" and identity.get("transport") == "none":
        if "arena-inputs/v1" in identity["capabilities"]:
            identity["capabilities"].extend(["arena-clock/v1", "guest-motor-output/v1"])
        if "programMailbox" in config:
            bus = monitor.Machine.SystemBus
            base = config["programMailbox"]
            if int(bus.ReadDoubleWord(base + 60)) != 0:
                lifecycle["nuttxProgram"] = spike_nuttx_mailbox.status(base, bus.ReadDoubleWord, bus.ReadBytes)
                sequence = int(bus.ReadDoubleWord(base + 36))
                if sequence:
                    lifecycle["nuttxProgramReply"] = spike_nuttx_mailbox.reply(base, sequence, bus.ReadDoubleWord, bus.ReadBytes)
                if "pythonOutputMailbox" in config:
                    lifecycle["nuttxProgramOutput"] = spike_nuttx_mailbox.output(config["pythonOutputMailbox"], bus.ReadDoubleWord, bus.ReadBytes)
                identity["capabilities"].append("nuttx-program/v1")
    identity["limitations"] = ["state is model output, not physical hardware"]
    clock = int(emulationManager.CurrentEmulation.MasterTimeSource.ElapsedVirtualTime.Ticks) * 100
    return {"schemaVersion": 1, "type": "snapshot", "seq": seq, "clockNs": clock,
            "target": identity, "lifecycle": lifecycle, "ports": ports, "motors": motors,
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
    if config["identity"]["board"] == "ev3":
        return ev3_state_observer.dispatch(config, _resolve, command)
    paths, name, args = config["paths"], command["command"], command["arguments"]
    if name == "state.sample":
        if args: raise ValueError("state.sample takes no arguments")
        return
    if name == "nuttx.program.packet":
        if config["identity"].get("firmware") != "brickwright-nuttx" or config["identity"].get("transport") != "none" or "programMailbox" not in config:
            raise ValueError("program packet requires our full simulation firmware")
        if set(args) != set(("bytes",)):
            raise ValueError("program packet takes bytes only")
        bus = monitor.Machine.SystemBus
        paused = monitor.Machine.ObtainPausedState(True)
        try:
            sequence = spike_nuttx_mailbox.submit(config["programMailbox"], args["bytes"], bus.ReadDoubleWord, bus.WriteDoubleWord)
        finally:
            paused.Dispose()
        # The existing running firmware acknowledges the request. Never execute
        # client instructions in the monitor or advance its simulated time here.
        for unused in range(1500):
            if spike_nuttx_mailbox.reply(config["programMailbox"], sequence, bus.ReadDoubleWord, bus.ReadBytes) is not None:
                return
            Thread.Sleep(1)
        raise ValueError("full firmware did not acknowledge program packet")
    if name == "arena.program.load":
        if config["identity"].get("firmware") != "brickwright-arena-demo" or config["identity"].get("transport") != "none":
            raise ValueError("arena program requires our simulation guest")
        paused = monitor.Machine.ObtainPausedState(True)
        try:
            bus = monitor.Machine.SystemBus
            spike_arena_mailbox.write_program(args, bus.ReadDoubleWord, bus.WriteDoubleWord)
        finally:
            paused.Dispose()
        return
    if name == "arena.inputs":
        if config["identity"].get("firmware") == "brickwright-arena-demo" and config["identity"].get("transport") == "none":
            bus = monitor.Machine.SystemBus
            spike_arena_mailbox.write_inputs(args, bus.ReadDoubleWord, bus.WriteDoubleWord)
            return
        if config["identity"].get("firmware") != "brickwright-nuttx" or config["identity"].get("transport") != "none":
            raise ValueError("arena input requires our simulation firmware")
        apply_arena_inputs(args, lambda port: _resolve(paths["port" + port]).Device)
        return
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
            if device not in ("none", "ultrasonic", "medium-motor", "motor", "color", "force"):
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
        if port < 0 or port > 65535 or clients != 1 or self.limit < 256 or self.limit > _MAX_LINE or self.timeout < 50 or self.timeout > 60000:
            raise ValueError("endpoint or resource limit is outside the supported range")
        self.config, self.running, self.generation = validate_config(config), True, 0
        self.last_error = ""
        self.stream, self.seq, self.write_lock, self.state_lock = None, 0, Lock(), RLock()
        self.listener = TcpListener(address, port)
        self.listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, True)
        self.listener.Start(clients)
        self.thread = Thread(ThreadStart(self._run)); self.thread.IsBackground = True; self.thread.Start()

    def close(self):
        self.running = False; self.listener.Stop()

    def _send(self, stream, message):
        wire = Encoding.UTF8.GetBytes(json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n")
        if wire.Length > self.limit:
            raise ValueError("outbound line exceeds configured limit")
        with self.write_lock:
            stream.Write(wire, 0, wire.Length)

    def _synchronized(self, callback):
        # The demo mailbox's sequence protocol provides coherent frames without
        # pausing guest time or adding asynchronous GDB stop notifications.
        if self.config["identity"].get("firmware") == "brickwright-arena-demo":
            with self.state_lock: return callback()
        for attempt in range(4):
            paused = monitor.Machine.ObtainPausedState(True)
            try:
                return callback()
            except ValueError as error:
                if str(error) != "full-firmware publication is not ready or changed" or attempt == 3:
                    raise
            finally:
                paused.Dispose()
            Thread.Sleep(1)

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
            try:
                self._client(client, self.generation)
            except Exception as exception:
                self.last_error = str(exception)
                print("SPIKE state client error: {0}".format(exception))
            finally:
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
            chunk = Encoding.UTF8.GetString(buffer, 0, count)
            try:
                lines, pending = split_frames(pending, chunk, self.limit, _READ_SIZE)
            except ValueError:
                return
            for line in lines:
                accepted, error = True, None
                try:
                    command = validate_command(json.loads(line))
                    request = command["requestId"]
                except Exception as exception:
                    command, request, accepted, error = None, "invalid", False, str(exception)
                if accepted and (request in seen or command.get("expectedSeq", self.seq - 1) != self.seq - 1): accepted, error = False, "duplicate requestId or expectedSeq mismatch"
                else:
                    if accepted:
                        seen.append(request)
                        if len(seen) > 256: seen.pop(0)
                        try:
                            if command["command"] == "nuttx.program.packet":
                                _dispatch(self.config, command)
                            else:
                                self._synchronized(lambda: _dispatch(self.config, command))
                        except Exception as exception: accepted, error = False, str(exception)
                result = {"schemaVersion": 1, "type": "result", "requestId": request, "accepted": accepted, "seq": self.seq - 1}
                if error is not None: result["error"] = error
                self._send(stream, result); self.sample()


def mc_spike_state_start(host, port, config_path):
    global _state_server
    if _state_server is not None: raise RuntimeError("SPIKE state server is already running")
    with open(str(config_path).lstrip("@"), "r") as stream: config = json.load(stream)
    _state_server = _Server(str(host), int(port), config)
    print("SPIKE state server listening on {0}".format(_state_server.listener.LocalEndpoint))


def mc_spike_state_stop():
    global _state_server
    if _state_server is not None: _state_server.close(); _state_server = None


def mc_spike_state_port():
    if _state_server is None: raise RuntimeError("SPIKE state server is stopped")
    print(_state_server.listener.LocalEndpoint.Port)


def mc_spike_state_sample():
    if _state_server is None or not _state_server.sample():
        raise RuntimeError("SPIKE state server has no connected client")


def mc_spike_state_error():
    print(_state_server.last_error if _state_server is not None else "state server is stopped")
