# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Controller tests against a separate synthetic first-order plant."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class Plant:
    def __init__(self, port, load=0, position=0):
        self.port, self.load, self.position = port, load, position
        self.speed, self.power, self.braking = 0.0, 0, False
        self.commands, self.history = [], []

    def dc(self, power):
        if type(power) is not int or not -100 <= power <= 100:
            raise AssertionError("controller emitted invalid power")
        self.power, self.braking = power, False
        self.commands.append(power)

    def brake(self):
        self.power, self.braking = 0, True

    def angle(self):
        return round(self.position)

    def speed_percent(self):
        return round(self.speed)

    def advance(self, milliseconds, time):
        target = self.power * (1 - self.load / 100)
        old = self.speed
        self.speed += (target - self.speed) * milliseconds / ((20 if self.braking else 60) + milliseconds)
        self.position += (old + self.speed) * 5 * milliseconds / 1000
        self.history.append((time, self.speed, self.position, self.power))


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.plants, self.interrupt = 0, [], False
        def sleep(milliseconds):
            if self.interrupt:
                raise KeyboardInterrupt()
            self.clock += milliseconds
            for motor in self.plants:
                motor.advance(milliseconds, self.clock)
        def difference(a, b):
            return ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)
        time = SimpleNamespace(sleep_ms=sleep, ticks_ms=lambda: self.clock % (1 << 30), ticks_diff=difference)
        source = Path(__file__).resolve().parents[2] / "tools/micropython/_bwctrl.py"
        spec = importlib.util.spec_from_file_location("control_fixture", source)
        self.control = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"time": time}):
            spec.loader.exec_module(self.control)

    def plant(self, *args, **kwargs):
        motor = Plant(*args, **kwargs)
        self.plants.append(motor)
        return motor

    def test_speed_feedback_compensates_load_both_directions(self):
        for target in (50, -50):
            motor = self.plant("A", load=25)
            start = self.clock
            self.control.run_speed(motor, target, 1500)
            steady = [speed for time, speed, _, _ in motor.history if start + 1100 <= time < start + 1500]
            self.assertTrue(steady)
            self.assertTrue(all(abs(speed - target) <= 3 for speed in steady))
            self.assertTrue(motor.braking)
            self.assertEqual(motor.speed_percent(), 0)
            self.assertEqual(self.control._active, set())

    def test_absolute_position_both_directions_and_zero_distance(self):
        motor = self.plant("A", position=-80)
        for target in (180, -90, -90):
            result = self.control.run_to(motor, target, 30, 10000)
            self.assertLessEqual(abs(result - target), 2)
            self.assertLessEqual(abs(motor.angle() - target), 2)
            self.assertEqual(motor.speed_percent(), 0)
            self.assertTrue(motor.braking)

    def test_stall_position_timeout_and_reader_failure_brake(self):
        motor = self.plant("A", load=100)
        with self.assertRaisesRegex(OSError, "stalled"):
            self.control.run_speed(motor, 50, 2000)
        self.assertTrue(motor.braking)
        with self.assertRaisesRegex(OSError, "position timed out"):
            self.control.run_to(motor, 90, 30, 100)
        self.assertTrue(motor.braking)
        with patch.object(motor, "angle", side_effect=OSError("bad UART")):
            with self.assertRaisesRegex(OSError, "bad UART"):
                self.control.run_to(motor, 90)
        self.assertTrue(motor.braking)
        self.assertFalse(self.control._active)

    def test_interrupt_releases_owner_and_brakes_only_selected_port(self):
        a, b = self.plant("A"), self.plant("B")
        b.dc(30)
        self.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.control.run_speed(a, 40, 1000)
        self.assertTrue(a.braking)
        self.assertEqual(b.power, 30)
        self.assertFalse(b.braking)
        self.assertFalse(self.control._active)

    def test_concurrent_uncontrolled_motor_preserved(self):
        a, b = self.plant("A"), self.plant("B")
        b.dc(-20)
        self.control.run_to(a, 90)
        self.assertEqual(b.power, -20)
        self.assertLess(b.angle(), 0)
        self.assertFalse(b.braking)

    def test_validation_and_busy_do_not_actuate(self):
        motor = self.plant("A")
        for target, duration in ((101, 10), (-101, 10), (True, 10), (1.5, 10), (10, -1), (10, True)):
            with self.assertRaises(ValueError):
                self.control.run_speed(motor, target, duration)
        for angle, speed, timeout in ((2147483648, 30, 100), (0, 0, 100), (0, 101, 100), (0, 30, 0)):
            with self.assertRaises(ValueError):
                self.control.run_to(motor, angle, speed, timeout)
        self.control._active.add("A")
        with self.assertRaisesRegex(OSError, "busy"):
            self.control.run_speed(motor, 20, 100)
        self.assertEqual(motor.commands, [])
        self.assertFalse(motor.braking)

    def test_zero_speed_duration_and_tick_wrap(self):
        motor = self.plant("A")
        motor.dc(50)
        self.control.run_speed(motor, 0, 20)
        self.assertTrue(motor.braking)
        self.control.run_speed(motor, 50, 0)
        self.assertTrue(motor.braking)
        self.clock = (1 << 30) - 50
        self.control.run_speed(motor, -30, 500)
        self.assertTrue(motor.braking)
        self.assertEqual(motor.speed_percent(), 0)


if __name__ == "__main__":
    unittest.main()
