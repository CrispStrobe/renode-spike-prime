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
from System.Diagnostics import Stopwatch
from threading import Lock, RLock

_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _tools not in sys.path:
    sys.path.insert(0, _tools)
from spike_state_monitor_protocol import split_frames, validate_command, validate_config, integer_types
import ev3_state_observer
from spike_arena_inputs import apply_arena_inputs
import spike_arena_mailbox
import spike_nuttx_mailbox
PROGRAM_UART_COMMANDS = ('micropython.uart.write', 'micropython.uart.read', 'micropython.uart.close')

_state_server = None
FLASH_CHECKPOINT_ABI = 1
try:
    _CHECKPOINT_INTEGERS = (int, long)
except NameError:
    _CHECKPOINT_INTEGERS = (int,)
_MAX_LINE, _READ_SIZE = 256 * 1024, 16 * 1024


# Newly authored flash-checkpoint adapter: BSD-3-Clause.
# Copyright (c) 2026 Brickwright contributors.
class _FlashCheckpoint(object):
    """Fixed native-owned files; never accepts a path from a socket command.

    Firmware ACK is distinct from host durability. The native owner validates
    and commits the exported bytes, then publishes a correlated receipt.
    """
    SIZE = 0x2000000

    def __init__(self, directory, image, export, reply, launch, sleep, now):
        self.directory, self.image = directory, image
        self.export, self.reply, self.launch = export, reply, launch
        self.sleep, self.now, self.lock = sleep, now, RLock()
        self.current, self.blocked = None, False

    def _path(self, name):
        return os.path.join(self.directory, name)

    def _fail(self):
        with self.lock:
            if self.current is not None:
                self.current['status'] = 'failed'
                self.current['error'] = 'Host flash checkpoint failed; previous saved checkpoint retained'

    def status(self):
        with self.lock:
            if self.current is None:
                return None
            if self.current['status'] == 'pending' and os.path.exists(self._path('receipt.json')):
                try:
                    with open(self._path('receipt.json'), 'r') as stream:
                        receipt = json.loads(stream.read(2048))
                    expected = set(('schema', 'imageSha256', 'requestSeq', 'programId', 'status'))
                    if (set(receipt) != expected or
                        any(isinstance(receipt.get(key), bool) or not isinstance(receipt.get(key), _CHECKPOINT_INTEGERS)
                            for key in ('schema', 'requestSeq', 'programId')) or receipt['schema'] != 1 or
                        receipt['imageSha256'] != self.image or
                        receipt['requestSeq'] != self.current['requestSeq'] or
                        receipt['programId'] != self.current['programId'] or
                        receipt['status'] not in ('durable', 'failed')):
                        raise ValueError('invalid checkpoint receipt')
                    self.current['status'] = receipt['status']
                    if receipt['status'] == 'durable':
                        self.blocked = False
                    if receipt['status'] == 'failed':
                        self.current['error'] = 'Host flash checkpoint failed; previous saved checkpoint retained'
                except Exception:
                    self._fail()
            return dict(self.current)

    def busy(self):
        status = self.status()
        return status is not None and self.blocked

    def begin(self, sequence, program_id):
        with self.lock:
            if self.busy():
                raise ValueError('host flash checkpoint is pending')
            for name in ('receipt.json', 'export.json', 'flash.bin', 'flash.pending'):
                path = self._path(name)
                if os.path.lexists(path):
                    os.remove(path)
            self.current = {'requestSeq': sequence, 'programId': program_id, 'status': 'pending'}
            self.blocked = True
        self.launch(lambda: self._checkpoint(sequence, program_id))

    def _checkpoint(self, sequence, program_id):
        try:
            deadline = self.now() + 30
            while True:
                packet = self.reply(sequence)
                if packet is not None:
                    if (packet[2] != 8 or
                        sum(int(packet[4 + i]) << (8 * i) for i in range(4)) != program_id):
                        raise ValueError('checkpoint SAVE correlation mismatch')
                    if any(packet[8:12]):
                        # Correlated firmware rejection cannot have exported or
                        # committed host data, so the session remains reusable.
                        self._fail()
                        with self.lock:
                            self.blocked = False
                        return
                    break
                if self.now() >= deadline:
                    raise ValueError('firmware SAVE completion timed out')
                self.sleep()
            # The adapter pauses only while copying model memory. Disk writes
            # occur after releasing the pause and never on the socket thread.
            raw = self.export()
            if len(raw) != self.SIZE:
                raise ValueError('incorrect flash export length')
            with open(self._path('flash.pending'), 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(self._path('flash.pending'), self._path('flash.bin'))
            metadata = {'schema': 1, 'imageSha256': self.image,
                        'requestSeq': sequence, 'programId': program_id, 'byteLength': self.SIZE}
            with open(self._path('export.pending'), 'w') as stream:
                json.dump(metadata, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(self._path('export.pending'), self._path('export.json'))
            while self.status()['status'] == 'pending':
                if self.now() >= deadline:
                    raise ValueError('host checkpoint completion timed out')
                self.sleep()
        except Exception:
            self._fail()



def mc_spike_flash_restore():
    """Fixed native launch hook, called before firmware boot or LittleFS mount."""
    directory = os.environ.get('BW_SPIKE_FLASH_JOB_DIR')
    if not directory:
        return
    if not os.path.isabs(directory) or not os.path.isdir(directory):
        raise ValueError('invalid native flash restore context')
    restore = os.path.join(directory, 'restore.bin')
    if os.path.exists(restore):
        if os.path.getsize(restore) != _FlashCheckpoint.SIZE:
            raise ValueError('invalid native flash restore size')
        from System.IO import File
        storage = _resolve('machine:sysbus.spi2.primeStorageMux.primeStorage')
        storage.UnderlyingMemory.WriteBytes(0, File.ReadAllBytes(restore))


def _flash_checkpoint(config, state_lock):
    directory = os.environ.get('BW_SPIKE_FLASH_JOB_DIR')
    if not directory:
        return None
    image = os.environ.get('BW_SPIKE_FLASH_IMAGE_SHA256')
    if (not os.path.isabs(directory) or not os.path.isdir(directory) or
        config['identity'].get('firmware') != 'brickwright-nuttx' or
        config['identity'].get('transport') != 'none' or
        image != config['identity'].get('imageSha256') or not image or
        'programMailbox' not in config or config.get('hostFlashCheckpointAbi') != FLASH_CHECKPOINT_ABI):
        raise ValueError('invalid native flash checkpoint context')
    storage = _resolve('machine:sysbus.spi2.primeStorageMux.primeStorage')
    timer = Stopwatch.StartNew()
    def export():
        with state_lock:
            paused = monitor.Machine.ObtainPausedState(True)
            try:
                return bytearray(storage.UnderlyingMemory.ReadBytes(0, _FlashCheckpoint.SIZE))
            finally:
                paused.Dispose()
    def reply(sequence):
        with state_lock:
            paused = monitor.Machine.ObtainPausedState(True)
            try:
                bus = monitor.Machine.SystemBus
                return spike_nuttx_mailbox.reply(config['programMailbox'], sequence, bus.ReadDoubleWord, bus.ReadBytes)
            finally:
                paused.Dispose()
    def launch(callback):
        worker = Thread(ThreadStart(callback))
        worker.IsBackground = True
        worker.Start()
    return _FlashCheckpoint(directory, image, export, reply, launch,
                            lambda: Thread.Sleep(10), lambda: timer.ElapsedMilliseconds / 1000.0)


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


def _snapshot(config, seq, generation, checkpoint=None, program_uart=None):
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
        clock = int(emulationManager.CurrentEmulation.MasterTimeSource.ElapsedVirtualTime.TotalNanoseconds)
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
    if identity.get("firmware") in ("brickwright-nuttx", "micropython-prime") and identity.get("transport") == "none" and any(_optional(paths, "port" + p) is not None for p in "ABCDEF"):
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
                if config.get("motorPorts") == 6:
                    identity["capabilities"].append("nuttx-six-motors/v1")
                if spike_nuttx_mailbox.supports_storage(base, config.get("programStorageAbiAddress"), bus.ReadDoubleWord):
                    identity["capabilities"].extend(["nuttx-program-storage/v1", "nuttx-program-storage-deferred/v1"])
                    storage_request = spike_nuttx_mailbox.storage_request(base, bus.ReadDoubleWord, bus.ReadBytes)
                    if storage_request is not None:
                        lifecycle["nuttxProgramStorage"] = storage_request
    if checkpoint is not None:
        identity['capabilities'].append('nuttx-flash-checkpoint/v1')
        checkpoint_status = checkpoint.status()
        if checkpoint_status is not None:
            lifecycle['nuttxFlashCheckpoint'] = checkpoint_status
    if program_uart is not None:
        lifecycle['micropythonUart'] = program_uart.status()
        identity['capabilities'].append('micropython-uart/v1')
        # These capabilities describe observed electrical-model state, not robot
        # Python APIs. Require both drive encoders before offering arena motion.
        if 'arena-inputs/v1' in identity['capabilities'] and all(
                any(motor['port'] == port for motor in motors) for port in ('A', 'B')):
            identity['capabilities'].extend(['arena-clock/v1', 'guest-motor-output/v1'])
        uart = lifecycle['micropythonUart']
        uart_generation = uart.get('generation')
        if (identity.get('firmware') == 'micropython-prime' and config.get('motorPorts') == 6
                and uart.get('state') == 'ready'
                and isinstance(uart_generation, integer_types) and not isinstance(uart_generation, bool)
                and 1 <= uart_generation <= 9007199254740991
                and uart_generation == config.get('programUartGeneration')
                and len(motors) == 6 and all(
                    any(motor['port'] == port for motor in motors) for port in 'ABCDEF')
                and all(port['attached'] and port['kind'] == 'motor' for port in ports)):
            identity['capabilities'].append('micropython-six-motors/v1')
    identity["limitations"] = ["state is model output, not physical hardware"]
    clock = int(emulationManager.CurrentEmulation.MasterTimeSource.ElapsedVirtualTime.TotalNanoseconds)
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


def _dispatch(config, command, checkpoint=None, program_uart=None):
    if config["identity"]["board"] == "ev3":
        return ev3_state_observer.dispatch(config, _resolve, command)
    paths, name, args = config["paths"], command["command"], command["arguments"]
    if name in ('micropython.uart.write', 'micropython.uart.read', 'micropython.uart.close'):
        if program_uart is None or config['identity'].get('firmware') != 'micropython-prime':
            raise ValueError('program UART unavailable')
        return program_uart.dispatch(name, args)
    if name == "state.sample":
        if args: raise ValueError("state.sample takes no arguments")
        return
    if name in ("nuttx.program.packet", "nuttx.program.storage.submit"):
        if config["identity"].get("firmware") != "brickwright-nuttx" or config["identity"].get("transport") != "none" or "programMailbox" not in config:
            raise ValueError("program packet requires our full simulation firmware")
        if set(args) != set(("bytes",)):
            raise ValueError("program packet takes bytes only")
        bus = monitor.Machine.SystemBus
        packet = spike_nuttx_mailbox.validate_packet(args["bytes"])
        deferred = name == "nuttx.program.storage.submit"
        if checkpoint is not None and checkpoint.busy():
            raise ValueError('host flash checkpoint is pending')
        if checkpoint is not None and packet[2] == 8 and not deferred:
            raise ValueError('durable SAVE requires deferred storage submission')
        if deferred and (len(packet) != 8 or packet[2] not in (8, 9)):
            raise ValueError("storage submit requires a SAVE or LOAD packet")
        if packet[2] in (8, 9) and not spike_nuttx_mailbox.supports_storage(config["programMailbox"], config.get("programStorageAbiAddress"), bus.ReadDoubleWord):
            raise ValueError("program storage is not supported by this firmware")
        paused = monitor.Machine.ObtainPausedState(True)
        try:
            sequence = spike_nuttx_mailbox.submit(config["programMailbox"], args["bytes"], bus.ReadDoubleWord, bus.WriteDoubleWord)
        finally:
            paused.Dispose()
        if deferred:
            if checkpoint is not None and packet[2] == 8:
                ident = sum(int(packet[4 + i]) << (8 * i) for i in range(4))
                checkpoint.begin(sequence, ident)
            # Typed storage submissions return promptly; firmware completion is
            # exposed separately with the exact mailbox sequence and packet ID.
            return
        # The existing running firmware acknowledges the request. Never execute
        # client instructions in the monitor or advance its simulated time here.
        deadline = Stopwatch.StartNew()
        while deadline.ElapsedMilliseconds < 1500:
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
        if config["identity"].get("firmware") not in ("brickwright-nuttx", "micropython-prime") or config["identity"].get("transport") != "none":
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
        self.checkpoint = _flash_checkpoint(self.config, self.state_lock)
        self.program_uart = None
        if self.config['identity'].get('firmware') == 'micropython-prime':
            from spike_program_uart import ProgramUartBinding
            self.program_uart = ProgramUartBinding(self.config, _resolve, lambda data: Array[Byte](data))
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
            snapshot = self._synchronized(lambda: _snapshot(self.config, self.seq, self.generation, self.checkpoint, self.program_uart))
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
                accepted, error, data = True, None, None
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
                            if command["command"] in ("nuttx.program.packet", "nuttx.program.storage.submit") + PROGRAM_UART_COMMANDS:
                                data = _dispatch(self.config, command, self.checkpoint, self.program_uart)
                            else:
                                data = self._synchronized(lambda: _dispatch(self.config, command, self.checkpoint, self.program_uart))
                        except Exception as exception: accepted, error = False, str(exception)
                result = {"schemaVersion": 1, "type": "result", "requestId": request, "accepted": accepted, "seq": self.seq - 1}
                if error is not None: result["error"] = error
                if data is not None: result['data'] = data
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
