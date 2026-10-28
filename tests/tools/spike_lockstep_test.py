#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Robot Lab lockstep (#58) through the actual monitor service code.

The IronPython service script runs here under CPython with fake .NET
modules, a fake emulation clock and port models that follow the Infra
LegoLpf2ElectricalPort contract (1 kHz bridge samples, external shaft
extrapolated from its anchor, TakeDriveAverage). No emulator or listener.
"""
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import spike_lockstep
from spike_lockstep import Lockstep, validate_step

DIGEST = 'a' * 64


# --- Infra contract stand-ins -------------------------------------------------

class Average(object):
    def __init__(self, mean, last, braking, ticks):
        self.MeanDrive, self.LastDrive, self.BrakingTicks, self.Ticks = mean, last, braking, ticks


class Motor(object):
    """LegoLpf2ElectricalPort's Lpf2ElectricalMotor, external-shaft part."""
    def __init__(self):
        self.external, self.position, self.speed, self.anchor, self.ms = False, 0.0, 0.0, 0.0, 0
        self.duty, self.LoadPercent, self.pos_reports = 0, 0, []
    SpeedPercent = property(lambda self: int(self.speed / 11.1))
    PositionDegrees = property(lambda self: self.position)
    EncoderDegrees = property(lambda self: int(round(self.position)))
    AngularVelocityDegreesPerSecond = property(lambda self: self.speed)
    Stalled = property(lambda self: not self.external and self.duty != 0 and self.LoadPercent == 100)
    Power = property(lambda self: int(self.duty / 100))
    def SetLoad(self, value):
        if self.external: raise ValueError('InvalidOperationException')
        self.LoadPercent = value
    def EnableExternalShaft(self):
        self.external, self.anchor, self.ms = True, self.position, 0
    def SetShaft(self, position, speed):
        if not self.external: raise ValueError('InvalidOperationException')
        self.position = self.anchor = position
        self.speed, self.ms = speed, 0
    def advance_ms(self):
        self.ms += 1
        self.position = self.anchor + self.speed * self.ms / 1000.0


class Port(object):
    def __init__(self, device, drive=lambda ms: (0, False)):
        self.Device, self.drive, self.TopologyGeneration = device, drive, 1
        self.external = False
        self.reset()
    def reset(self):
        self.sum, self.ticks, self.braking, self.last = 0, 0, 0, getattr(self, 'last', 0)
    ExternalShaft = property(lambda self: self.external)
    def EnableExternalShaft(self):
        self.external = True
        if isinstance(self.Device, Motor): self.Device.EnableExternalShaft()
    def SetShaft(self, position, speed):
        if not isinstance(self.Device, Motor): raise ValueError('no motor')
        self.Device.SetShaft(position, speed)
    def TakeDriveAverage(self):
        result = Average(self.sum / float(self.ticks) if self.ticks else 0.0, self.last, self.braking, self.ticks)
        self.reset()
        return result
    def tick(self, ms):
        if not isinstance(self.Device, Motor): return
        drive, braking = self.drive(ms)
        self.Device.duty = drive
        self.sum += drive; self.ticks += 1; self.braking += int(braking); self.last = drive
        self.Device.advance_ms()
        if ms % 10 == 0:  # the motor's 10 ms POS report, as the firmware reads it
            self.Device.pos_reports.append((ms, int(round(self.Device.position))))


class OldPort(object):
    """A port model from before #37: no external shaft."""
    def __init__(self, device): self.Device, self.TopologyGeneration = device, 1


class Color(object):
    ColorId, ReflectionPercent, AmbientPercent = 255, 0, 0
    def SetReading(self, color, reflection, ambient):
        self.ColorId, self.ReflectionPercent, self.AmbientPercent = color, reflection, ambient


class Emulation(object):
    """Renode's Emulation/MasterTimeSource: RunFor advances exactly, ticks at 1 kHz."""
    def __init__(self, ports, clock_ns=1000000000):
        self.ns, self.IsStarted, self.ports, self.runs = clock_ns, True, ports, []
        self.MasterTimeSource = self
    @property
    def ElapsedVirtualTime(self):
        return types.SimpleNamespace(TotalNanoseconds=self.ns)
    def PauseAll(self): self.IsStarted = False
    def RunFor(self, interval):
        if self.IsStarted: raise RuntimeError('This action is not available when emulation is already started')
        self.runs.append(interval.us)
        end = self.ns + interval.us * 1000
        while self.ns < end:
            self.ns += 1000000
            for port in self.ports.values(): port.tick(self.ns // 1000000)


# --- the actual monitor script under CPython ------------------------------------

class Wire(bytes):
    Length = property(len)


class Buffer(bytearray):
    Length = property(len)


class Stream(object):
    def __init__(self, lines):
        self.input = ''.join(json.dumps(line) + '\n' for line in lines).encode()
        self.output = b''
    def Read(self, buffer, offset, count):
        chunk, self.input = self.input[:min(count, 64)], self.input[min(count, 64):]
        buffer[offset:offset + len(chunk)] = chunk
        return len(chunk)
    def Write(self, wire, offset, count): self.output += bytes(wire[offset:offset + count])
    def messages(self): return [json.loads(line) for line in self.output.decode().splitlines()]


def fake_dotnet():
    ns = types.SimpleNamespace
    utf8 = ns(GetBytes=lambda text: Wire(text.encode()), GetString=lambda b, o, c: bytes(b[o:o + c]).decode())
    modules = {
        'clr': ns(AddReference=lambda name: None),
        'System': ns(Array=ns(CreateInstance=lambda kind, n: Buffer(n)), Byte=int, UInt64=int),
        'System.Net': ns(IPAddress=None), 'System.Net.Sockets': ns(SocketOptionLevel=None, SocketOptionName=None, TcpListener=None),
        'System.Text': ns(Encoding=ns(UTF8=utf8)), 'System.Threading': ns(Thread=None, ThreadStart=None),
        'System.Diagnostics': ns(Stopwatch=None),
        'Antmicro': ns(), 'Antmicro.Renode': ns(),
        'Antmicro.Renode.Time': ns(TimeInterval=ns(FromMicroseconds=lambda us: ns(us=us))),
    }
    sys.modules.update(modules)


def load_server(externals, emulation, cpu_mode='Continuous'):
    fake_dotnet()
    path = ROOT / 'scripts/spike-state-server.py'
    env = {'__file__': str(path), '__name__': 'spike_state_server_under_test', 'externals': externals,
           'emulationManager': types.SimpleNamespace(CurrentEmulation=emulation),
           'monitor': types.SimpleNamespace(Machine=types.SimpleNamespace(
               ObtainPausedState=lambda flag: types.SimpleNamespace(Dispose=lambda: None),
               SystemBus=types.SimpleNamespace(GetCPUs=lambda: [types.SimpleNamespace(ExecutionMode=cpu_mode)])))}
    exec(compile(path.read_text(), str(path), 'exec'), env)
    return env


def config(paths):
    return {'identity': {'board': 'spike-prime', 'firmware': 'brickwright-nuttx', 'transport': 'none',
                         'imageSha256': DIGEST}, 'paths': paths}


def command(request, name, arguments, expected=None):
    value = {'schemaVersion': 1, 'type': 'command', 'requestId': request, 'command': name, 'arguments': arguments}
    if expected is not None: value['expectedSeq'] = expected
    return value


def step(request, expect, shafts=(), sensors=(), quantum=5000):
    return command(request, 'lockstep.step', {'quantumUs': quantum, 'expectClockNs': expect,
                                              'shafts': list(shafts), 'sensors': list(sensors)})


class Session(object):
    """One client connection through the actual _Server._client loop."""
    def __init__(self, ports, cpu_mode='Continuous'):
        self.ports = ports
        self.emulation = Emulation(ports)
        self.env = load_server(dict(('port' + k, v) for k, v in ports.items()), self.emulation, cpu_mode)
        server = object.__new__(self.env['_Server'])
        server.config = config(dict(('port' + k, 'external:port' + k) for k in ports))
        server.running, server.generation, server.last_error, server.limit = True, 1, '', 256 * 1024
        server.stream, server.seq, server.checkpoint, server.program_uart = None, 0, None, None
        server.timeout = 5000
        lock = types.SimpleNamespace(__enter__=lambda *a: None, __exit__=lambda *a: None)
        import threading
        server.write_lock, server.state_lock = threading.Lock(), threading.RLock()
        server.lockstep = Lockstep(self.env['_LockstepEmulator'](server.config, None))
        self.server = server

    def run(self, lines):
        stream = Stream(lines)
        self.server._client(types.SimpleNamespace(GetStream=lambda: stream), 1)
        messages = stream.messages()
        snapshots = [m for m in messages if m['type'] == 'snapshot']
        results = [m for m in messages if m['type'] == 'result']
        return snapshots, results


def bridge(ms):
    """Firmware-like drive: 2 ms at 0, then 4000/6000 alternating per ms, brake every 7th ms."""
    if ms % 7 == 0: return 0, True
    return (0 if ms % 5 < 2 else 4000 + 2000 * (ms % 2)), False


def default_ports():
    return {'A': Port(Motor(), bridge), 'B': Port(Motor()), 'C': Port(Color())}


class LockstepServiceTests(unittest.TestCase):
    def test_capabilities_and_unchanged_snapshots_before_lockstep(self):
        session = Session(default_ports())
        snapshots, _ = session.run([])
        target = snapshots[0]['target']
        for capability in spike_lockstep.CAPABILITIES:
            self.assertIn(capability, target['capabilities'])
        for motor in snapshots[0]['motors']:
            self.assertNotIn('positionSource', motor)
            self.assertNotIn('drive', motor)
        old = Session({'A': OldPort(Motor()), 'B': OldPort(Motor())})
        snapshots, _ = old.run([])
        self.assertFalse(set(spike_lockstep.CAPABILITIES) & set(snapshots[0]['target']['capabilities']))
        snapshots, results = old.run([command('b', 'lockstep.begin', {'quantumUs': 5000})])
        self.assertFalse(results[0]['accepted'])

    def test_n_steps_advance_exactly_with_one_seq_each_and_integrated_drive(self):
        session = Session(default_ports())
        t0 = session.emulation.ns
        n, quantum = 40, 5000
        lines = [command('begin', 'lockstep.begin', {'quantumUs': quantum})]
        for k in range(n):
            lines.append(step('s%d' % k, t0 + k * quantum * 1000,
                              shafts=[{'port': 'A', 'positionMdeg': 1000000 + 1800 * k, 'speedMdps': 360000},
                                      {'port': 'B', 'positionMdeg': -5, 'speedMdps': 0}],
                              sensors=[{'port': 'C', 'kind': 'color', 'values': {
                                  'colorId': 3, 'reflectionPercent': 40, 'ambientPercent': 0}}]))
        lines.append(command('end', 'lockstep.end', {}))
        snapshots, results = session.run(lines)
        self.assertTrue(all(r['accepted'] for r in results), results)
        self.assertFalse(session.emulation.IsStarted, 'begin paused the free-running emulation')
        self.assertEqual(session.emulation.runs, [quantum] * n)
        begin = results[0]['data']
        self.assertEqual(begin['clockNs'], t0)
        steps = [r['data'] for r in results[1:-1]]
        for k, frame in enumerate(steps):
            self.assertEqual(frame['clockNs'], t0 + (k + 1) * quantum * 1000)
            self.assertEqual(frame['seq'], begin['seq'] + k + 1)
            # The reply's snapshot is the stream's next snapshot, not a re-read.
            self.assertEqual(snapshots[k + 2], frame)
            motors = dict((m['port'], m) for m in frame['motors'])
            self.assertEqual(motors['A']['positionSource'], 'external')
            drive = motors['A']['drive']
            ticks = range(1 + (t0 // 1000000) + 5 * k, 1 + (t0 // 1000000) + 5 * (k + 1))
            samples = [bridge(ms) for ms in ticks]
            self.assertEqual(drive['ticks'], 5)
            self.assertAlmostEqual(drive['mean'], sum(d for d, _ in samples) / 5.0)
            self.assertEqual(drive['last'], samples[-1][0])
            self.assertEqual(drive['brakingTicks'], sum(int(b) for _, b in samples))
            self.assertEqual(motors['B']['drive'], {'mean': 0.0, 'last': 0, 'brakingTicks': 0, 'ticks': 5})
            # End of the quantum: the anchor plus 5 ms at the injected speed.
            self.assertAlmostEqual(motors['A']['position'], 1000.0 + 1.8 * k + 360.0 * 0.005)
            self.assertEqual(motors['A']['speedDps'], 360.0)
        self.assertEqual(steps[-1]['clockNs'] - t0, n * quantum * 1000)
        # The 10 ms POS reports the firmware reads carry the injected shaft.
        for ms, reported in session.ports['A'].Device.pos_reports:
            k = (ms - t0 // 1000000 - 1) // 5
            self.assertEqual(reported, int(round(1000.0 + 1.8 * k + 0.36 * (ms - t0 // 1000000 - 5 * k))))
        self.assertEqual(session.ports['C'].Device.ColorId, 3)
        self.assertEqual(len(session.ports['A'].Device.pos_reports), n // 2)
        end = results[-1]['data']
        self.assertNotIn('drive', end['motors'][0])
        self.assertEqual(end['motors'][0]['positionSource'], 'external')

    def test_wrong_clock_is_refused_before_any_model_changes(self):
        session = Session(default_ports())
        t0 = session.emulation.ns
        shaft = [{'port': 'A', 'positionMdeg': 90000, 'speedMdps': 0}]
        snapshots, results = session.run([
            command('begin', 'lockstep.begin', {'quantumUs': 5000}),
            step('early', t0 - 1, shaft), step('late', t0 + 1, shaft),
            step('ok', t0, shaft)])
        self.assertEqual([r['accepted'] for r in results], [True, False, False, True])
        self.assertIn('expectClockNs', results[1]['error'])
        self.assertEqual(session.emulation.runs, [5000])
        self.assertEqual(results[3]['data']['clockNs'], t0 + 5000000)

    def test_free_run_dispatch_is_refused_while_active_and_admitted_after_end(self):
        session = Session(default_ports())
        inputs = {'sensors': [], 'loads': [{'port': 'A', 'percent': 100}]}
        snapshots, results = session.run([
            command('begin', 'lockstep.begin', {'quantumUs': 10000}),
            command('advance', 'lpf2.advance-microseconds', {'port': 'A', 'microseconds': 1000}),
            command('packet', 'nuttx.program.packet', {'bytes': [0x70, 1, 3, 0, 1, 0, 0, 0]}),
            command('inputs', 'arena.inputs', inputs),
            command('sample', 'state.sample', {}),
            command('again', 'lockstep.begin', {'quantumUs': 10000}),
            step('quantum', session.emulation.ns, quantum=5000),
            command('end', 'lockstep.end', {}),
            command('end2', 'lockstep.end', {}),
            step('after', session.emulation.ns, quantum=10000),
            command('inputs2', 'arena.inputs', {'sensors': [{'port': 'C', 'kind': 'color', 'values': {
                'colorId': 5, 'reflectionPercent': 1, 'ambientPercent': 0}}], 'loads': []})])
        accepted = [r['accepted'] for r in results]
        self.assertEqual(accepted, [True, False, False, False, True, False, False, True, False, False, True])
        self.assertTrue(all('lockstep is active' in r['error'] for r in results[1:4]))
        self.assertEqual(session.emulation.runs, [])
        # Every command still yields exactly one snapshot with the next seq.
        self.assertEqual([s['seq'] for s in snapshots], list(range(len(results) + 1)))

    def test_malformed_steps_are_refused_by_the_closed_validator(self):
        good = {'quantumUs': 5000, 'expectClockNs': 0, 'shafts': [{'port': 'A', 'positionMdeg': 1, 'speedMdps': 2}], 'sensors': []}
        validate_step(good)
        def changed(**kw):
            value = json.loads(json.dumps(good)); value.update(kw); return value
        bad = [changed(quantumUs=7000), changed(expectClockNs=-1), changed(expectClockNs=1.0), changed(extra=1),
               changed(shafts=[{'port': 'G', 'positionMdeg': 1, 'speedMdps': 2}]),
               changed(shafts=[{'port': 'A', 'positionMdeg': 1.5, 'speedMdps': 2}]),
               changed(shafts=[{'port': 'A', 'positionMdeg': 2 ** 31, 'speedMdps': 2}]),
               changed(shafts=[{'port': 'A', 'positionMdeg': 1, 'speedMdps': 2000001}]),
               changed(shafts=[{'port': 'A', 'positionMdeg': True, 'speedMdps': 2}]),
               changed(shafts=[{'port': 'A', 'positionMdeg': 1, 'speedMdps': 2, 'x': 0}]),
               changed(shafts=[good['shafts'][0], good['shafts'][0]]),
               changed(sensors=[{'port': 'A', 'kind': 'force', 'values': {'forcePercent': 1, 'pressed': False}}])]
        for value in bad:
            with self.assertRaises(ValueError, msg=value): validate_step(value)

    def test_begin_refuses_a_debugger_halted_cpu_at_the_first_step(self):
        session = Session(default_ports(), cpu_mode='SingleStep')
        t0 = session.emulation.ns
        _, results = session.run([command('begin', 'lockstep.begin', {'quantumUs': 5000}), step('s', t0)])
        self.assertTrue(results[0]['accepted'])
        self.assertFalse(results[1]['accepted'])
        self.assertIn('debugger', results[1]['error'])

    def test_resumed_emulation_voids_the_lockstep_clock(self):
        session = Session(default_ports())
        t0 = session.emulation.ns
        lockstep = session.server.lockstep
        lockstep.begin({'quantumUs': 5000})
        session.emulation.IsStarted = True
        with self.assertRaises(ValueError): lockstep.step(step('s', t0)['arguments'])
        self.assertEqual(session.emulation.runs, [])

    def test_sensor_failure_leaves_shafts_untouched(self):
        ports = default_ports()
        ports['D'] = Port(Color())
        session = Session(ports)
        t0 = session.emulation.ns
        session.server.lockstep.begin({'quantumUs': 5000})
        before = ports['A'].Device.position
        with self.assertRaises(ValueError):
            session.server.lockstep.step(step('s', t0, shafts=[{'port': 'A', 'positionMdeg': 777000, 'speedMdps': 0}],
                sensors=[{'port': 'D', 'kind': 'distance', 'values': {'distanceMillimeters': 10}}])['arguments'])
        self.assertEqual(ports['A'].Device.position, before)
        self.assertEqual(session.emulation.runs, [])


class DeferredControlTests(unittest.TestCase):
    def test_start_and_stop_return_at_once_and_other_packets_are_refused(self):
        import struct
        import spike_nuttx_mailbox as mailbox
        base = 0x20021000
        memory = bytearray(112)
        struct.pack_into('<I', memory, 0, mailbox.MAGIC)
        struct.pack_into('<I', memory, 4, 1)
        struct.pack_into('<I', memory, 60, 2)
        def read(address): return struct.unpack_from('<I', memory, address - base)[0]
        def write(address, value): struct.pack_into('<I', memory, address - base, value)
        env = load_server({}, Emulation({}))
        env['monitor'].Machine.SystemBus = types.SimpleNamespace(ReadDoubleWord=read, WriteDoubleWord=write,
            ReadBytes=lambda address, count: memory[address - base:address - base + count])
        cfg = config({})
        cfg['programMailbox'] = base
        dispatch = env['_dispatch']
        name = spike_lockstep.DEFERRED_CONTROL_COMMAND
        start = [0x70, 1, 3, 0, 1, 0, 0, 0]
        self.assertEqual(dispatch(cfg, {'command': name, 'arguments': {'bytes': start}}), {'requestSeq': 2})
        self.assertEqual(read(base + 8), 2)
        write(base + 36, 2)  # firmware acknowledged
        stop = [0x70, 1, 4, 0, 1, 0, 0, 0]
        self.assertEqual(dispatch(cfg, {'command': name, 'arguments': {'bytes': stop}}), {'requestSeq': 4})
        write(base + 36, 4)
        for packet in ([0x70, 1, 2, 0, 1, 0, 0, 0], [0x70, 1, 8, 0, 1, 0, 0, 0], [0x70, 1, 0, 0, 1, 0, 0, 0] + [0] * 8):
            with self.assertRaises(ValueError):
                dispatch(cfg, {'command': name, 'arguments': {'bytes': packet}})
        self.assertEqual(read(base + 8), 4)
        self.assertIn(name, spike_lockstep.ALLOWED_DURING_LOCKSTEP)


class ConnectionOwnershipTests(unittest.TestCase):
    """R04: a lockstep and its commands belong to the connection that began them."""

    def connections(self, server, *clients):
        """Serve each line list as one accepted connection through _Server._run."""
        streams, pending = [], list(clients)

        def accept():
            if not pending:
                server.running = False
                raise IOError('listener stopped')
            stream = Stream(pending.pop(0))
            streams.append(stream)
            return types.SimpleNamespace(GetStream=lambda: stream, Close=lambda: None)

        server.listener = types.SimpleNamespace(AcceptTcpClient=accept)
        server._run()
        return [[m for m in s.messages() if m['type'] == 'result'] for s in streams]

    def test_a_lost_client_does_not_hand_its_lockstep_to_the_next(self):
        session = Session(default_ports())
        # The first stream ends without lockstep.end: that client is gone.
        first, second = self.connections(
            session.server, [command('begin', 'lockstep.begin', {'quantumUs': 5000})],
            [command('begin2', 'lockstep.begin', {'quantumUs': 10000})])
        self.assertTrue(first[0]['accepted'])
        self.assertTrue(second[0]['accepted'], second[0].get('error'))
        self.assertEqual(session.server.lockstep.quantum, 10000)
        self.assertFalse(session.emulation.IsStarted)  # paused, as after lockstep.end
        self.assertFalse(session.server.lockstep.active)

    def test_a_command_read_after_close_is_not_dispatched(self):
        session = Session(default_ports())
        server = session.server

        class Racing(Stream):
            def Read(self, buffer, offset, count):
                # close() runs on the monitor thread while this read is
                # blocked; the whole command line then arrives in one read.
                server.running = False
                chunk, self.input = self.input, b''
                buffer[offset:offset + len(chunk)] = chunk
                return len(chunk)

        stream = Racing([command('begin', 'lockstep.begin', {'quantumUs': 5000})])
        server._client(types.SimpleNamespace(GetStream=lambda: stream), 1)
        self.assertEqual([m for m in stream.messages() if m['type'] == 'result'], [])
        self.assertFalse(server.lockstep.active)
        self.assertTrue(session.emulation.IsStarted)

    def test_close_closes_the_connected_stream(self):
        session = Session(default_ports())
        server, closed = session.server, []
        server.listener = types.SimpleNamespace(Stop=lambda: closed.append('listener'))
        server.stream = types.SimpleNamespace(Close=lambda: closed.append('stream'))
        server.close()
        self.assertEqual(closed, ['listener', 'stream'])
        self.assertFalse(server.running)


if __name__ == '__main__':
    unittest.main()
