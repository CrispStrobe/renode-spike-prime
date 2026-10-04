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
        for port in ("G", "a", 0, None, True):
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

    def test_auxiliary_ports_discover_before_actuation_and_refuse_wrong_device(self):
        self.api._read=Mock(side_effect=OSError('wrong device'))
        for port in 'CDEF':
            motor=self.api.Motor(port)
            with self.assertRaises(OSError):motor.dc(20)
        self.assertEqual(dict(self.registers),{})
        self.assertEqual(self.api._motors,set('AB'))
        self.api._read.reset_mock(side_effect=True)
        self.api._read.return_value=b'\0'*4
        self.api.Motor('F').dc(-30)
        self.api._read.assert_called_once_with('F',48,2,4)
        self.api.Motor('F').brake()
        self.api._read.assert_called_once()

    def test_six_motor_timer_isolation_cross_bank_f_and_stop_all(self):
        self.api._read=Mock(return_value=b'\0'*4)
        # Synthetic pin contract independent of register-write helper implementation.
        layout={'C':(0x40020400,6,7,0x40000800,1),
                'D':(0x40020400,8,9,0x40000800,3),
                'E':(0x40020800,6,7,0x40000400,1)}
        for port,(gpio,first,second,timer,channel) in layout.items():
            self.api.Motor(port).dc(40)
            self.assertEqual(self.registers[timer+52+(channel-1)*4],400)
            self.assertEqual((self.registers[gpio]>>(first*2))&3,2)
            self.assertTrue(self.registers[gpio+20]&(1<<second))
        e=self.registers[0x40000400+52]
        self.api.Motor('F').dc(-25)
        self.assertEqual(self.registers[0x40000400+64],250)
        self.assertEqual(self.registers[0x40000400+52],e)
        self.assertEqual((self.registers[0x40020400]>>2)&3,2)
        self.assertEqual((self.registers[0x40020400+32]>>4)&15,2)
        self.assertTrue(self.registers[0x40020800+20]&(1<<8))
        self.assertEqual(self.api._initialized,{0x40000400,0x40000800})
        self.assertNotIn(0x40000400+68,self.registers)
        self.assertNotIn(0x40000800+68,self.registers)
        self.api.stop_all()
        for gpio,pins in [(0x40021000,(9,11,13,14)),(0x40020400,(1,6,7,8,9)),(0x40020800,(6,7,8))]:
            for pin in pins:
                self.assertEqual((self.registers[gpio]>>(2*pin))&3,1)
                self.assertTrue(self.registers[gpio+20]&(1<<pin))

    def test_wait_boundaries_and_validation(self):
        for value in (0, 2147483647):
            self.api.wait(value)
            self.sleep.assert_called_with(value)
        for value in (-1, 2147483648, True, 1.5):
            with self.assertRaises(ValueError):
                self.api.wait(value)


if __name__ == "__main__":
    unittest.main()
