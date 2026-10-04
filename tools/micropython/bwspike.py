# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Drive-motor API for Brickwright's qualified Prime simulation profile.

Power is an integer percentage, not a speed target. This module runs inside
MicroPython and uses the retained board's CPU-facing GPIO/PWM registers.
"""
from machine import mem32
from time import sleep_ms

# GPIO bank/pin pairs, timer, channels and AF from the modeled A-F board.
_PORTS = {
    "A": (0x40021000, 9, 0x40021000, 11, 0x40010000, 1, 2, 1),
    "B": (0x40021000, 13, 0x40021000, 14, 0x40010000, 3, 4, 1),
    "C": (0x40020400, 6, 0x40020400, 7, 0x40000800, 1, 2, 2),
    "D": (0x40020400, 8, 0x40020400, 9, 0x40000800, 3, 4, 2),
    "E": (0x40020800, 6, 0x40020800, 7, 0x40000400, 1, 2, 2),
    "F": (0x40020800, 8, 0x40020400, 1, 0x40000400, 3, 4, 2),
}
_initialized = set()
_motors = set("AB")


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + " must be an integer in " + str(low) + ".." + str(high))
    return value


def _field(address, shift, width, value):
    mask = ((1 << width) - 1) << shift
    mem32[address] = (mem32[address] & ~mask) | (value << shift)


def _mode(gpio, pin, value):
    _field(gpio, pin * 2, 2, value)


def _level(gpio, pin, high):
    _field(gpio + 20, pin, 1, int(high))


def _alternate(gpio, pin, af):
    _field(gpio + (32 if pin < 8 else 36), (pin % 8) * 4, 4, af)


def _initialize(timer):
    if timer in _initialized:
        return
    mem32[timer + 40] = 99
    mem32[timer + 44] = 999
    if timer == 0x40010000:
        mem32[timer + 68] = mem32[timer + 68] | 32768
    mem32[timer] = mem32[timer] | 1
    _initialized.add(timer)


def _ensure_motor(port):
    if port not in _motors:
        _read(port, 48, 2, 4)
        _motors.add(port)


def wait(milliseconds):
    """Wait using firmware ticks; Ctrl-C remains interruptible."""
    sleep_ms(_integer(milliseconds, 0, 2147483647, "milliseconds"))


def _read(port, device_type, mode, length):
    from _bwlpf2 import read
    return read(port, device_type, mode, length)


def _percent(value):
    if value > 100:
        raise OSError("sensor percentage outside range")
    return value


class Motor:
    """A modeled motor on A-F; auxiliary ports require motor discovery."""
    def __init__(self, port):
        if type(port) is not str or port not in _PORTS:
            raise ValueError("motor port must be A-F")
        self.port = port
        self._pins = _PORTS[port]

    def dc(self, power):
        """Apply signed power (-100..100%); zero coasts."""
        power = _integer(power, -100, 100, "power")
        if power == 0:
            self.coast()
            return
        _ensure_motor(self.port)
        g1, first, g2, second, timer, ch1, ch2, af = self._pins
        _initialize(timer)
        _mode(g1, first, 1)
        _mode(g2, second, 1)
        _level(g1, first, False)
        _level(g2, second, False)
        gpio, pin, other_gpio, other, channel = (g1, first, g2, second, ch1) if power > 0 else (g2, second, g1, first, ch2)
        _alternate(gpio, pin, af)
        _field(timer + (24 if channel <= 2 else 28), ((channel - 1) % 2) * 8, 8, 6 << 4)
        _field(timer + 32, (channel - 1) * 4, 4, 3)
        mem32[timer + 52 + (channel - 1) * 4] = abs(power) * 10
        _level(other_gpio, other, True)
        _mode(gpio, pin, 2)

    def brake(self):
        """Request electrical braking; deceleration comes from the hub model."""
        _ensure_motor(self.port)
        g1, first, g2, second, _, _, _, _ = self._pins
        _mode(g1, first, 1)
        _mode(g2, second, 1)
        _level(g1, first, True)
        _level(g2, second, True)

    def coast(self):
        """Remove drive; inertia and load remain governed by the hub model."""
        _ensure_motor(self.port)
        g1, first, g2, second, _, _, _, _ = self._pins
        _mode(g1, first, 1)
        _mode(g2, second, 1)
        _level(g1, first, False)
        _level(g2, second, False)

    def angle(self):
        """Read signed encoder degrees through the device UART."""
        data = _read(self.port, 48, 2, 4)
        _motors.add(self.port)
        value = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
        return value - 0x100000000 if value & 0x80000000 else value

    def speed_percent(self):
        """Read signed speed percentage, not a speed-control target."""
        value = _read(self.port, 48, 1, 1)[0]
        value = value - 256 if value & 128 else value
        if not -100 <= value <= 100:
            raise OSError("motor speed percentage outside range")
        _motors.add(self.port)
        return value

    def run_for(self, power, milliseconds):
        """Run for firmware milliseconds, braking on return or interruption."""
        _integer(power, -100, 100, "power")
        _integer(milliseconds, 0, 2147483647, "milliseconds")
        _ensure_motor(self.port)
        try:
            self.dc(power)
            wait(milliseconds)
        finally:
            self.brake()

    def run_speed(self, target_percent, milliseconds):
        """Track speed percentage for a duration, then brake and settle."""
        from _bwctrl import run_speed
        return run_speed(self, target_percent, milliseconds)

    def run_to(self, angle, speed_limit=30, timeout_ms=10000):
        """Reach absolute encoder degrees within two degrees, then brake."""
        from _bwctrl import run_to
        return run_to(self, angle, speed_limit, timeout_ms)


def stop_all():
    """Brake A/B and every auxiliary motor verified by this module."""
    for port in sorted(_motors):
        Motor(port).brake()


class ColorSensor:
    def __init__(self, port="C"):
        if type(port) is not str or port != "C":
            raise ValueError("default color sensor port must be C")
        self.port = port

    def color_id(self):
        """Return the model's color ID; 255 means unknown."""
        return _read(self.port, 61, 0, 1)[0]

    def reflection(self):
        return _percent(_read(self.port, 61, 1, 1)[0])

    def ambient(self):
        return _percent(_read(self.port, 61, 2, 1)[0])


class DistanceSensor:
    def __init__(self, port="D"):
        if type(port) is not str or port != "D":
            raise ValueError("default distance sensor port must be D")
        self.port = port

    def distance(self):
        """Return unsigned millimeters, or None when no distance is detected."""
        data = _read(self.port, 62, 0, 2)
        value = data[0] | (data[1] << 8)
        return None if value == 65535 else value


class ForceSensor:
    def __init__(self, port="E"):
        if type(port) is not str or port != "E":
            raise ValueError("default force sensor port must be E")
        self.port = port

    def force(self):
        return _percent(_read(self.port, 63, 0, 1)[0])

    def pressed(self):
        value = _read(self.port, 63, 1, 1)[0]
        if value not in (0, 1):
            raise OSError("force pressed value outside range")
        return bool(value)
