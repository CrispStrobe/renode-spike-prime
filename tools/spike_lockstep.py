# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Robot Lab lockstep for the SPIKE state service (renode-spike-prime#58).

Python 2/3 compatible: runs inside Renode's IronPython monitor and under
CPython tests. Emulator access is injected, so this module holds only the
closed DTO checks and the session rules:

* ``lockstep.begin {quantumUs}`` pauses the emulation, switches every
  electrical port to the external shaft and clears the drive integrators.
* ``lockstep.step {quantumUs, expectClockNs, shafts, sensors, hub?}`` applies
  the shafts and sensors on the paused machine, advances virtual time by
  exactly one quantum with ``RunFor`` and returns the drive averages that the
  snapshot reports. A clock other than ``expectClockNs`` is refused before
  anything changes.
* ``lockstep.end {}`` leaves lockstep; the machine stays paused and the shafts
  stay external (the model never switches back).

While lockstep is active only the commands in ``ALLOWED_DURING_LOCKSTEP`` are
dispatched: nothing may run guest time outside a step.
"""
try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)

QUANTA_US = (5000, 10000)
PORT_TICK_US = 1000
PORTS = ('A', 'B', 'C', 'D', 'E', 'F')
MAX_POSITION_MDEG = 2 ** 31 - 1
MAX_SPEED_MDPS = 2000000
COMMANDS = ('lockstep.begin', 'lockstep.step', 'lockstep.end')
CAPABILITIES = ('lockstep/v1', 'motor-bridge-drive/v1', 'external-shaft/v1')
DEFERRED_START_CAPABILITY = 'nuttx-program-deferred-start/v1'
# Program control that returns at once; firmware replies in later snapshots.
DEFERRED_CONTROL_COMMAND = 'nuttx.program.control.submit'
DEFERRED_CONTROL_OPERATIONS = (3, 4)  # START, STOP
ALLOWED_DURING_LOCKSTEP = COMMANDS + (
    'state.sample', DEFERRED_CONTROL_COMMAND, 'nuttx.program.storage.submit',
    'micropython.uart.write', 'micropython.uart.read', 'micropython.uart.close')


def _integer(value):
    return isinstance(value, integer_types) and not isinstance(value, bool)


def validate_quantum(value):
    if not _integer(value) or value not in QUANTA_US:
        raise ValueError('quantumUs must be one of 5000, 10000')
    return int(value)


def validate_begin(arguments):
    if not isinstance(arguments, dict) or set(arguments) != set(('quantumUs',)):
        raise ValueError('lockstep.begin takes quantumUs only')
    return validate_quantum(arguments['quantumUs'])


def validate_step(arguments):
    """Closed step DTO; returns (quantumUs, expectClockNs, shafts, arena inputs)."""
    if not isinstance(arguments, dict):
        raise ValueError('lockstep.step arguments must be an object')
    keys = set(arguments)
    if keys not in (set(('quantumUs', 'expectClockNs', 'shafts', 'sensors')),
                    set(('quantumUs', 'expectClockNs', 'shafts', 'sensors', 'hub'))):
        raise ValueError('lockstep.step takes quantumUs, expectClockNs, shafts, sensors and optional hub')
    quantum = validate_quantum(arguments['quantumUs'])
    expect = arguments['expectClockNs']
    if not _integer(expect) or expect < 0 or expect > 2 ** 63 - 1:
        raise ValueError('expectClockNs must be a non-negative integer')
    shafts, sensors = arguments['shafts'], arguments['sensors']
    if not isinstance(shafts, list) or len(shafts) > len(PORTS):
        raise ValueError('shafts must be a list of at most six')
    if not isinstance(sensors, list) or len(sensors) > len(PORTS):
        raise ValueError('sensors must be a list of at most six')
    seen, out = set(), []
    for shaft in shafts:
        if not isinstance(shaft, dict) or set(shaft) != set(('port', 'positionMdeg', 'speedMdps')):
            raise ValueError('a shaft is {port, positionMdeg, speedMdps}')
        port = shaft['port']
        if port not in PORTS or port in seen:
            raise ValueError('shaft ports must be unique A-F')
        seen.add(port)
        position, speed = shaft['positionMdeg'], shaft['speedMdps']
        if not _integer(position) or abs(position) > MAX_POSITION_MDEG:
            raise ValueError('positionMdeg must be an integer within +-2^31')
        if not _integer(speed) or abs(speed) > MAX_SPEED_MDPS:
            raise ValueError('speedMdps must be an integer within +-2e6')
        out.append((port, int(position), int(speed)))
    for sensor in sensors:
        if isinstance(sensor, dict) and sensor.get('port') in seen:
            raise ValueError('a port is either a shaft or a sensor')
    inputs = {'sensors': sensors, 'loads': []}
    if 'hub' in arguments:
        inputs['hub'] = arguments['hub']
    return quantum, int(expect), out, inputs


class Lockstep(object):
    """Session rules over injected emulator access.

    ``emulator`` provides: ``clock_ns()``, ``is_started()``, ``pause()``,
    ``run_for_us(us)``, ``ports()`` -> {letter: electrical port model} and
    ``prepare_inputs(inputs)``, which validates and resolves an arena-inputs
    frame without changing a model and returns the callable that applies it.
    """

    def __init__(self, emulator):
        self.emulator = emulator
        self.active = False
        self.quantum = None
        self.steps = 0
        self.origin_ns = None

    @staticmethod
    def supported(ports):
        return bool(ports) and all(
            callable(getattr(port, name, None))
            for port in ports.values()
            for name in ('EnableExternalShaft', 'SetShaft', 'TakeDriveAverage'))

    def allowed(self, command):
        return not self.active or command in ALLOWED_DURING_LOCKSTEP

    def begin(self, arguments):
        quantum = validate_begin(arguments)
        if self.active:
            raise ValueError('lockstep is already active')
        ports = self.emulator.ports()
        if not self.supported(ports):
            raise ValueError('the port models have no external shaft')
        if self.emulator.is_started():
            self.emulator.pause()
        for letter in sorted(ports):
            ports[letter].EnableExternalShaft()
            ports[letter].TakeDriveAverage()
        self.active, self.quantum, self.steps = True, quantum, 0
        self.origin_ns = self.emulator.clock_ns()

    def step(self, arguments):
        if not self.active:
            raise ValueError('lockstep is not active')
        quantum, expect, shafts, inputs = validate_step(arguments)
        if quantum != self.quantum:
            raise ValueError('quantumUs differs from lockstep.begin')
        if self.emulator.is_started():
            # Someone resumed free-running time: the lab's clock is void.
            raise ValueError('the emulation was resumed outside lockstep')
        clock = self.emulator.clock_ns()
        if clock != expect:
            raise ValueError('expectClockNs %d does not match the emulator clock %d' % (expect, clock))
        ports = self.emulator.ports()
        motors = []
        for letter, position, speed in shafts:
            port = ports.get(letter)
            device = getattr(port, 'Device', None)
            if port is None or device is None or not callable(getattr(device, 'SetShaft', None)):
                raise ValueError('shaft port %s has no electrical motor' % letter)
            motors.append((port, position, speed))
        # Everything is resolved and validated before any model changes.
        apply_inputs = self.emulator.prepare_inputs(inputs)
        for port, position, speed in motors:
            port.SetShaft(position / 1000.0, speed / 1000.0)
        apply_inputs()
        for letter in sorted(ports):
            ports[letter].TakeDriveAverage()
        self.emulator.run_for_us(quantum)
        after = self.emulator.clock_ns()
        if after != expect + quantum * 1000:
            self.active = False
            raise ValueError('RunFor advanced the clock to %d, not %d; lockstep ended' % (after, expect + quantum * 1000))
        self.steps += 1
        return dict((letter, drive_report(ports[letter].TakeDriveAverage())) for letter in sorted(ports))

    def end(self, arguments):
        if not isinstance(arguments, dict) or arguments:
            raise ValueError('lockstep.end takes no arguments')
        if not self.active:
            raise ValueError('lockstep is not active')
        self.active = False


def drive_report(average):
    """Infra Lpf2DriveAverage -> the snapshot's motor drive (1/10000 duty)."""
    return {'mean': float(average.MeanDrive), 'last': int(average.LastDrive),
            'brakingTicks': int(average.BrakingTicks), 'ticks': int(average.Ticks)}
