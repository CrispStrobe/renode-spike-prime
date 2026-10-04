# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic transport/contract tests; no firmware or physical calibration."""
import importlib.util
from pathlib import Path
import sys
from collections import defaultdict
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class Registers(defaultdict):
    def __init__(self):
        super().__init__(int)
        self.writes = []
        self.adc = {14: 4095, 1: 4095}
        self.stall = False
        self.interrupt_after = None
        self.spi = []
        self.pcm = []
        self.i2c_state = 'idle'
        self.i2c_status = 0
        self.i2c_pending = []
        self.i2c_selected = 0
        self.i2c_pointer = 0
        self.i2c_data = {0x0f: 0x6a}
        self.i2c_transactions = []
        self.i2c_fail = None
        self.i2c_byte_count = 0
        self.i2c_interrupt_after = None

    def __setitem__(self, key, value):
        self.writes.append((key, value))
        if key == 0x40005800:
            if value & 0x8000:
                self.i2c_pending = []
                self.i2c_status = 0
                self.i2c_state = 'idle'
            elif value & 0x300:
                if self.i2c_pending:
                    self.i2c_pointer = self.i2c_pending[0]
                    if len(self.i2c_pending) == 2:
                        self.i2c_data[self.i2c_pointer] = self.i2c_pending[1]
                    self.i2c_transactions.append(tuple(self.i2c_pending))
                    self.i2c_pending = []
                if value & 0x100:
                    self.i2c_state = 'address'
                    self.i2c_status = 1
                else:
                    self.i2c_state = 'idle'
                    self.i2c_status &= 0x40
        if key == 0x40005810:
            self.i2c_byte_count += 1
            if self.i2c_interrupt_after == self.i2c_byte_count:
                raise KeyboardInterrupt
            if self.i2c_state == 'address':
                if value not in (0xd4, 0xd5):
                    raise AssertionError('wrong sensor address')
                self.i2c_state = 'receive' if value & 1 else 'transmit'
                self.i2c_status = 2 | (0 if value & 1 else 0x80)
            elif self.i2c_state == 'transmit':
                self.i2c_pending.append(value)
                self.i2c_status = 0x84
            else:
                raise AssertionError('data outside transmit phase')
        if key == 0x40012008 and value & (1 << 30) and not self.stall:
            super().__setitem__(0x40012000, 2)
        if key == 0x4001300c:
            self.spi.append(value)
            if self.interrupt_after == len(self.spi):
                raise KeyboardInterrupt
        if key == 0x40007408:
            self.pcm.append(value)
            if self.interrupt_after == len(self.pcm):
                raise KeyboardInterrupt
        super().__setitem__(key, value)

    def __getitem__(self, key):
        if key == 0x40005814:
            if self.i2c_fail == 'nack':
                return 0x400
            if self.i2c_fail == 'stall':
                return 0
            return self.i2c_status
        if key == 0x40005818:
            if not self.i2c_status & 2:
                raise AssertionError('ADDR cleared before SR1 address check')
            self.i2c_status &= ~2
            if self.i2c_state == 'receive':
                self.i2c_status |= 0x40
            return 1
        if key == 0x40005810:
            if not self.i2c_status & 0x40:
                raise AssertionError('read before receive ready')
            self.i2c_status &= ~0x40
            return self.i2c_data.get(self.i2c_pointer, 0)
        if key == 0x4001204c:
            super().__setitem__(0x40012000, 0)
            return self.adc[super().__getitem__(0x40012034)]
        if key == 0x40013008:
            return 0 if self.stall else 3
        return super().__getitem__(key)


class HubTests(unittest.TestCase):
    def setUp(self):
        self.mem = Registers()
        self.clock = (1 << 30) - 500
        def tick():
            return self.clock % (1 << 30)
        def sleep(ms):
            self.clock += ms
        def diff(a, b):
            return ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)
        self.env = patch.dict(sys.modules, {
            'machine': SimpleNamespace(mem32=self.mem, mem8=self.mem),
            'time': SimpleNamespace(sleep_ms=sleep, ticks_ms=tick, ticks_diff=diff)})
        self.env.start()
        self.addCleanup(self.env.stop)
        for name in ('bwspike', 'bwhub'):
            spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/micropython' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            modules = patch.dict(sys.modules, {name: module})
            modules.start()
            self.addCleanup(modules.stop)
            spec.loader.exec_module(module)
            if name == 'bwhub':
                self.api = module

    def test_import_and_construction_do_not_write(self):
        for name in ('Display', 'Buttons', 'IMU', 'Sound'):
            getattr(self.api, name)()
        self.assertEqual(self.mem.writes, [])
        self.assertEqual(self.mem.i2c_transactions, [])

    def test_display_full_frame_mapping_latch_and_preservation(self):
        self.mem[0x40020014] = 1 << 2
        self.api.Display().show(list(range(25)))
        self.assertEqual(len(self.mem.spi), 97)
        self.assertEqual(self.mem.spi[0], 0)
        # Explicit retained-model matrix contract, not SDK helper reuse.
        expected = (38, 36, 41, 46, 33, 37, 28, 39, 47, 21, 24, 29, 31,
                    45, 23, 26, 27, 32, 34, 22, 25, 40, 30, 35, 9)
        channels = [(self.mem.spi[i] << 8) | self.mem.spi[i + 1] for i in range(1, 97, 2)]
        self.assertEqual([channels[i] for i in expected], list(range(25)))
        self.assertTrue(any(a == 0x40020014 and v & (1 << 15) for a, v in self.mem.writes))
        self.assertEqual(self.mem[0x40020014], 1 << 2)
        self.api.Display().clear()
        self.assertEqual(self.mem.spi[-97:], [0] * 97)

    def test_validation_precedes_output(self):
        for bad in ([0] * 24, [True] * 25, [0] * 24 + [65536], '0' * 25):
            with self.assertRaises(ValueError):
                self.api.Display().show(bad)
        for bad in (b'', b'x' * 4097, bytearray(b'a'), 7):
            with self.assertRaises(ValueError):
                self.api.Sound().write_pcm8(bad)
        self.assertEqual(self.mem.writes, [])

    def test_all_button_combinations_and_unknown_samples(self):
        for flags, sample in enumerate((4095, 2646, 3201, 2234, 3633, 2432, 2882, 2055)):
            for center in (False, True):
                self.mem.adc = {14: 3010 if center else 4095, 1: sample}
                wanted = tuple(n for n, yes in (('center', center), ('left', flags & 1),
                               ('right', flags & 2), ('bluetooth', flags & 4)) if yes)
                self.assertEqual(self.api.Buttons().pressed(), wanted)
                self.assertEqual(self.mem[0x40012008], 0)
        self.mem.adc[1] = 2000
        with self.assertRaisesRegex(OSError, 'unsupported'):
            self.api.Buttons().pressed()
        self.mem.adc[1] = 4096
        with self.assertRaisesRegex(OSError, 'range'):
            self.api.Buttons().raw()

    def test_bounded_polls_across_tick_wrap_and_release(self):
        self.mem.stall = True
        for device, method in ((self.api.Buttons(), 'raw'), (self.api.Display(), 'clear')):
            before = self.clock
            with self.assertRaisesRegex(OSError, 'timed out'):
                getattr(device, method)()
            self.assertEqual(self.clock - before, 1000)
            self.assertEqual(self.api._busy, set())
        self.mem.stall = False
        self.api.Buttons().raw()

    def test_display_interruption_never_latches_partial_frame(self):
        self.mem.interrupt_after = 12
        with self.assertRaises(KeyboardInterrupt):
            self.api.Display().clear()
        self.assertFalse(any(a == 0x40020014 and v & (1 << 15) for a, v in self.mem.writes))
        self.assertEqual(self.api._busy, set())

    def test_imu_signed_registers_identity_and_single_byte_transactions(self):
        for base in (0x20, 0x22, 0x28):
            for i, value in enumerate(b'\x00\x80\xff\x7f\xff\xff'):
                self.mem.i2c_data[base + i] = value
        # Temperature overlaps gyro, so explicitly establish its boundary.
        self.mem.i2c_data[0x20] = 0
        self.mem.i2c_data[0x21] = 128
        imu = self.api.IMU()
        self.assertEqual(imu.acceleration_raw(), (-32768, 32767, -1))
        self.assertEqual(imu.angular_rate_raw(), (-32768, 32767, -1))
        self.assertEqual(imu.temperature_raw(), -32768)
        self.assertIn((0x12, 4), self.mem.i2c_transactions)
        self.assertTrue(all(len(t) == 1 or t == (0x12, 4) for t in self.mem.i2c_transactions))
        self.assertEqual(self.mem[0x40005800], 0)
        self.mem.i2c_data[0x0f] = 0
        with self.assertRaisesRegex(OSError, 'identity'):
            imu.acceleration_raw()
        self.assertEqual(self.api._busy, set())
        self.assertEqual(self.mem[0x40005800], 0)

    def test_imu_nack_timeout_wrap_interruption_and_recovery(self):
        imu = self.api.IMU()
        for failure, message in (('nack', 'transaction error'), ('stall', 'timed out')):
            self.mem.i2c_fail = failure
            before = self.clock
            with self.assertRaisesRegex(OSError, message):
                imu.acceleration_raw()
            self.assertEqual(self.clock - before, 1000 if failure == 'stall' else 0)
            self.assertEqual(self.mem[0x40005800], 0)
            self.assertEqual(self.api._busy, set())
        self.mem.i2c_fail = None
        # Interrupt at address, pointer, repeated address, control write,
        # and data register transactions; each leaves a reusable controller.
        for after in range(1, 25):
            self.mem.i2c_interrupt_after = self.mem.i2c_byte_count + after
            with self.assertRaises(KeyboardInterrupt):
                imu.acceleration_raw()
            self.assertEqual(self.mem[0x40005800], 0)
            self.assertEqual(self.mem.i2c_pending, [])
            self.assertEqual(self.api._busy, set())
            self.mem.i2c_interrupt_after = None
            self.assertEqual(imu.acceleration_raw(), (0, 0, 0))

    def test_pcm_bytes_gate_cleanup_and_shared_ownership(self):
        self.mem[0x40020814] = 1 << 6
        sound = self.api.Sound()
        sound.write_pcm8(b'\x00\xff\x80')
        self.assertEqual(self.mem.pcm, [0, 255, 128])
        self.assertEqual(self.mem[0x40020814], 1 << 6)
        self.mem.interrupt_after = 4
        with self.assertRaises(KeyboardInterrupt):
            sound.write_pcm8(b'ab')
        self.assertEqual(self.mem[0x40020814], 1 << 6)
        self.assertEqual(self.api._busy, set())
        for resource, device, method in (('sound', sound, lambda: sound.write_pcm8(b'a')),
                                       ('display', self.api.Display(), lambda: self.api.Display().clear()),
                                       ('buttons', self.api.Buttons(), lambda: self.api.Buttons().raw()),
                                       ('imu', self.api.IMU(), lambda: self.api.IMU().temperature_raw())):
            self.api._busy.add(resource)
            before = len(self.mem.writes)
            with self.assertRaisesRegex(OSError, 'busy'):
                method()
            self.assertEqual(len(self.mem.writes), before)
            self.api._busy.remove(resource)


if __name__ == '__main__':
    unittest.main()
