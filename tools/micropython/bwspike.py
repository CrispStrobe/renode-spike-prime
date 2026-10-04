# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Drive-motor API for Brickwright's qualified Prime simulation profile.

Power is an integer percentage, not a speed target. This module runs inside
MicroPython and uses the retained board's CPU-facing GPIO/PWM registers.
"""
from machine import mem32
from time import sleep_ms

_GPIO = 0x40021000  # GPIO E
_TIMER = 0x40010000  # TIM1, 100 MHz input in this application profile
_PORTS = {"A": (9, 11, 1, 2), "B": (13, 14, 3, 4)}
_initialized = False


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + " must be an integer in " + str(low) + ".." + str(high))
    return value


def _field(address, shift, width, value):
    mask = ((1 << width) - 1) << shift
    mem32[address] = (mem32[address] & ~mask) | (value << shift)


def _mode(pin, value):
    _field(_GPIO, pin * 2, 2, value)


def _level(pin, high):
    _field(_GPIO + 20, pin, 1, int(high))


def _alternate(pin):
    _field(_GPIO + (32 if pin < 8 else 36), (pin % 8) * 4, 4, 1)


def _initialize():
    global _initialized
    if _initialized:
        return
    # A and B share TIM1. Initialize once, so starting the second motor
    # never resets the first motor's compare value or GPIO state.
    mem32[_TIMER + 40] = 99
    mem32[_TIMER + 44] = 999
    mem32[_TIMER + 68] = mem32[_TIMER + 68] | 32768
    mem32[_TIMER] = mem32[_TIMER] | 1
    _initialized = True


def wait(milliseconds):
    """Wait using firmware ticks; Ctrl-C remains interruptible."""
    sleep_ms(_integer(milliseconds, 0, 2147483647, "milliseconds"))


class Motor:
    """One of the two drive motors in the default simulation topology."""
    def __init__(self, port):
        if type(port) is not str or port not in _PORTS:
            raise ValueError("drive motor port must be A or B")
        self.port = port
        self._pins = _PORTS[port]

    def dc(self, power):
        """Apply signed power (-100..100%); zero coasts."""
        power = _integer(power, -100, 100, "power")
        if power == 0:
            self.coast()
            return
        _initialize()
        first, second, channel1, channel2 = self._pins
        # Disconnect PWM before changing direction, preserving the other port.
        _mode(first, 1)
        _mode(second, 1)
        _level(first, False)
        _level(second, False)
        pin, other, channel = (first, second, channel1) if power > 0 else (second, first, channel2)
        _alternate(pin)
        _field(_TIMER + (24 if channel <= 2 else 28), ((channel - 1) % 2) * 8, 8, 6 << 4)
        _field(_TIMER + 32, (channel - 1) * 4, 4, 3)
        mem32[_TIMER + 52 + (channel - 1) * 4] = abs(power) * 10
        _level(other, True)
        _mode(pin, 2)

    def brake(self):
        """Request electrical braking; deceleration comes from the hub model."""
        first, second, _, _ = self._pins
        _mode(first, 1)
        _mode(second, 1)
        _level(first, True)
        _level(second, True)

    def coast(self):
        """Remove drive; inertia and load remain governed by the hub model."""
        first, second, _, _ = self._pins
        _mode(first, 1)
        _mode(second, 1)
        _level(first, False)
        _level(second, False)

    def run_for(self, power, milliseconds):
        """Run for firmware milliseconds, braking on return or interruption."""
        _integer(power, -100, 100, "power")
        _integer(milliseconds, 0, 2147483647, "milliseconds")
        try:
            self.dc(power)
            wait(milliseconds)
        finally:
            self.brake()


def stop_all():
    """Brake both configured drive motors."""
    Motor("A").brake()
    Motor("B").brake()
