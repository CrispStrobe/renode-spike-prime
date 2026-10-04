# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from collections import defaultdict


class MotorApiTests(unittest.TestCase):
    def setUp(self):
        self.registers = defaultdict(int)
        self.sleep = Mock()
        spec = importlib.util.spec_from_file_location(
            "bwspike_fixture", Path(__file__).resolve().parents[2] / "tools/micropython/bwspike.py")
        self.api = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"machine": SimpleNamespace(mem32=self.registers),
                                     "time": SimpleNamespace(sleep_ms=self.sleep)}):
            spec.loader.exec_module(self.api)
        self.gpio = 0x40021000
        self.timer = 0x40010000

    def mode(self, pin):
        return (self.registers[self.gpio] >> (pin * 2)) & 3

    def high(self, pin):
        return bool(self.registers[self.gpio + 20] & (1 << pin))

    def test_constructor_and_bad_arguments_do_not_actuate(self):
        motor = self.api.Motor("A")
        self.assertEqual(dict(self.registers), {})
        for value in (-101, 101, True, 1.5, "50", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                motor.dc(value)
        for port in ("C", "a", 0, None, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                self.api.Motor(port)
        with self.assertRaises(ValueError):
            motor.run_for(50, -1)
        self.assertEqual(dict(self.registers), {})

    def test_concurrent_ports_preserve_other_motor_and_unrelated_gpio(self):
        self.registers[self.gpio] = 3  # Unrelated E0 configuration.
        a, b = self.api.Motor("A"), self.api.Motor("B")
        a.dc(-50)
        before = self.registers[self.timer + 56]
        b.dc(25)
        self.assertEqual(self.registers[self.timer + 56], before)
        self.assertEqual(before, 500)
        self.assertEqual(self.registers[self.timer + 60], 250)
        self.assertEqual((self.mode(9), self.mode(11)), (1, 2))
        self.assertEqual((self.mode(13), self.mode(14)), (2, 1))
        self.assertTrue(self.high(9))
        self.assertTrue(self.high(14))
        self.assertEqual(self.registers[self.gpio] & 3, 3)
        a.dc(100)
        self.assertEqual(self.registers[self.timer + 52], 1000)
        self.assertEqual((self.mode(13), self.mode(14)), (2, 1))
        self.assertEqual(self.registers[self.timer + 60], 250)

    def test_coast_and_brake_differ_and_do_not_stop_other_port(self):
        a, b = self.api.Motor("A"), self.api.Motor("B")
        b.dc(50)
        a.brake()
        self.assertTrue(self.high(9) and self.high(11))
        a.dc(0)
        self.assertFalse(self.high(9) or self.high(11))
        self.assertEqual((self.mode(9), self.mode(11)), (1, 1))
        self.assertEqual((self.mode(13), self.mode(14)), (2, 1))
        self.api.stop_all()
        self.assertTrue(all(self.high(pin) for pin in (9, 11, 13, 14)))
        self.assertTrue(all(self.mode(pin) == 1 for pin in (9, 11, 13, 14)))

    def test_timed_run_brakes_on_completion_and_interrupt(self):
        a = self.api.Motor("A")
        a.run_for(20, 700)
        self.sleep.assert_called_once_with(700)
        self.assertTrue(self.high(9) and self.high(11))
        self.sleep.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            a.run_for(-30, 700)
        self.assertEqual((self.mode(9), self.mode(11)), (1, 1))
        self.assertTrue(self.high(9) and self.high(11))

    def test_wait_boundaries_and_validation(self):
        for value in (0, 2147483647):
            self.api.wait(value)
            self.sleep.assert_called_with(value)
        for value in (-1, 2147483648, True, 1.5):
            with self.assertRaises(ValueError):
                self.api.wait(value)


if __name__ == "__main__":
    unittest.main()
