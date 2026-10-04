# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synchronous feedback controls for the qualified two-motor profile."""
from time import sleep_ms, ticks_ms, ticks_diff

_active = set()


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + " outside integer range")


def _clip(value, low, high):
    return max(low, min(high, value))


class _Feedback:
    def __init__(self, motor):
        self.motor = motor
        self.integral = 0.0
        self.demand = 0.0
        self.previous = ticks_ms()
        self.progress_at = self.previous
        self.position = motor.angle()

    def step(self, target):
        now = ticks_ms()
        elapsed = max(1, ticks_diff(now, self.previous))
        self.previous = now
        # Limit the requested speed ramp to 200 percentage points/second.
        change = elapsed * 0.2
        self.demand += _clip(target - self.demand, -change, change)
        speed = self.motor.speed_percent()
        error = self.demand - speed
        candidate = _clip(self.integral + error * elapsed / 1000, -50, 50)
        power = self.demand + 0.8 * error + 2 * candidate
        if -100 <= power <= 100 or power * error < 0:
            self.integral = candidate
        self.motor.dc(int(round(_clip(power, -100, 100))))
        position = self.motor.angle()
        if abs(position - self.position) >= 2:
            self.position = position
            self.progress_at = now
        elif abs(target) >= 1 and ticks_diff(now, self.progress_at) >= 500:
            raise OSError("motor stalled: no encoder progress")
        sleep_ms(20)


def _settle(motor):
    started = ticks_ms()
    while motor.speed_percent() != 0:
        if ticks_diff(ticks_ms(), started) >= 1000:
            raise OSError("motor braking timed out")
        sleep_ms(20)


def _claim(motor):
    if motor.port in _active:
        raise OSError("motor control is busy")
    _active.add(motor.port)


def run_speed(motor, target, milliseconds):
    _integer(target, -100, 100, "speed percentage")
    _integer(milliseconds, 0, 2147483647, "milliseconds")
    _claim(motor)
    try:
        try:
            if target == 0:
                motor.brake()
                sleep_ms(milliseconds)
            elif milliseconds:
                feedback = _Feedback(motor)
                started = ticks_ms()
                while ticks_diff(ticks_ms(), started) < milliseconds:
                    feedback.step(target)
        finally:
            motor.brake()
        _settle(motor)
    finally:
        _active.discard(motor.port)


def run_to(motor, target, speed_limit=30, timeout_ms=10000):
    _integer(target, -2147483648, 2147483647, "target angle")
    _integer(speed_limit, 1, 100, "speed limit")
    _integer(timeout_ms, 1, 2147483647, "timeout")
    _claim(motor)
    try:
        try:
            feedback = _Feedback(motor)
            started = ticks_ms()
            while True:
                if ticks_diff(ticks_ms(), started) >= timeout_ms:
                    raise OSError("motor position timed out")
                error = target - motor.angle()
                if abs(error) <= 2:
                    motor.brake()
                    _settle(motor)
                    position = motor.angle()
                    if ticks_diff(ticks_ms(), started) >= timeout_ms:
                        raise OSError("motor position timed out")
                    if abs(target - position) <= 2:
                        return position
                    feedback = _Feedback(motor)
                    error = target - position
                demand = min(speed_limit, max(1, abs(error) * 0.6))
                feedback.step(demand if error > 0 else -demand)
        finally:
            motor.brake()
    finally:
        _active.discard(motor.port)
