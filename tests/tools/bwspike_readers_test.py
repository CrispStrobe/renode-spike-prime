# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic external UART traces and the public reader value contract."""
from collections import defaultdict, deque
import importlib.util
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / "tools/micropython"


def packet(header, payload):
    checksum = 255 ^ header
    for value in payload:
        checksum ^= value
    return bytes((header,)) + bytes(payload) + bytes((checksum,))


class UartFixture:
    address = 0x40007800

    def __init__(self):
        self.registers = defaultdict(int)
        self.rx = deque()
        self.command = []
        self.writes = []
        self.values = {0: b"\x14", 1: b"\xce", 2: struct.pack("<i", -1234)}
        self.discovery = (b"\x00" + packet(0x40, b"\x30") +
                          packet(0x98, b"\x00SYNTH   ") + b"\x04")
        self.reply = lambda mode: self.data(mode)
        self.error = 0

    def data(self, mode):
        payload = self.values[mode]
        size = {1: 0, 2: 1, 4: 2, 8: 3}[len(payload)]
        return packet(0xc0 | (size << 3) | mode, payload)

    def __getitem__(self, address):
        if address == self.address:
            return 128 | (32 if self.rx else 0) | self.error
        if address == self.address + 4:
            self.error = 0
            return self.rx.popleft() if self.rx else 0
        return self.registers[address]

    def __setitem__(self, address, value):
        self.registers[address] = value
        self.writes.append((address, value))
        if address == self.address + 12 and value == 0x200c:
            self.rx.extend(self.discovery)
        if address != self.address + 4:
            return
        if self.command or value == 0x43:
            self.command.append(value)
            if len(self.command) == 3:
                header, mode, checksum = self.command
                if header ^ mode ^ checksum != 255:
                    raise AssertionError("invalid externally observed select frame")
                self.command = []
                self.rx.extend(self.reply(mode))
        elif value == 4:
            self.rx.extend(self.data(0))


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.uart = UartFixture()
        self.clock = 0
        self.interrupt = False
        def sleep(milliseconds):
            if self.interrupt:
                raise KeyboardInterrupt()
            self.clock = (self.clock + milliseconds) % (1 << 30)
        def diff(a, b):
            return ((a - b + (1 << 29)) % (1 << 30)) - (1 << 29)
        time = SimpleNamespace(sleep_ms=sleep, ticks_ms=lambda: self.clock, ticks_diff=diff)
        spec = importlib.util.spec_from_file_location("lpf2_fixture", ROOT / "_bwlpf2.py")
        self.protocol = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"machine": SimpleNamespace(mem32=self.uart), "time": time}):
            spec.loader.exec_module(self.protocol)
            spec = importlib.util.spec_from_file_location("api_fixture", ROOT / "bwspike.py")
            self.api = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.api)

    def read(self, mode=2, length=4):
        return self.protocol.read("A", 48, mode, length)

    def test_discovery_checksum_metadata_and_signed_encoder(self):
        with patch.dict(sys.modules, {"_bwlpf2": self.protocol}):
            self.assertEqual(self.api.Motor("A").angle(), -1234)
            self.assertEqual(self.api.Motor("A").speed_percent(), -50)
        self.assertEqual(sum(value == 0x200c and address == self.uart.address + 12
                             for address, value in self.uart.writes), 1)

    def test_queued_old_reports_discarded_and_modes_not_cached(self):
        self.assertEqual(self.read(), struct.pack("<i", -1234))
        self.uart.rx.extend(self.uart.data(2))
        self.uart.values[2] = struct.pack("<i", 2345)
        self.assertEqual(self.read(), struct.pack("<i", 2345))
        self.assertEqual(self.read(1, 1), b"\xce")

    def test_unrequested_mode_frame_ignored(self):
        self.uart.reply = lambda mode: self.uart.data(0) + self.uart.data(mode)
        self.assertEqual(self.read(), struct.pack("<i", -1234))

    def test_wrong_type_refused_before_acknowledgment(self):
        self.uart.discovery = packet(0x40, b"\x3d") + b"\x04"
        with self.assertRaisesRegex(OSError, "type mismatch"):
            self.read()
        self.assertNotIn((self.uart.address + 4, 4), self.uart.writes)

    def test_missing_type_refused(self):
        self.uart.discovery = b"\x04"
        with self.assertRaisesRegex(OSError, "missing device type"):
            self.read()

    def test_corrupt_discovery_and_corrupt_data_refused(self):
        self.uart.discovery = bytes((0x40, 48, 0))
        with self.assertRaisesRegex(OSError, "checksum"):
            self.read()
        self.uart.discovery = packet(0x40, b"\x30") + b"\x04"
        self.uart.reply = lambda mode: bytes((0xd2, 1, 2, 3, 4, 0))
        with self.assertRaisesRegex(OSError, "checksum"):
            self.read()

    def test_wrong_data_length_refused(self):
        self.uart.values[2] = b"\x01\x02"
        with self.assertRaisesRegex(OSError, "length mismatch"):
            self.read()

    def test_oversized_frame_refused_before_payload(self):
        self.uart.discovery = b"\xf8"
        with self.assertRaisesRegex(OSError, "frame exceeds bound"):
            self.read()

    def test_discovery_and_backlog_bounds(self):
        self.uart.discovery = bytes(128)
        with self.assertRaisesRegex(OSError, "discovery exceeds"):
            self.read()
        self.uart.discovery = packet(0x40, b"\x30") + b"\x04"
        self.read()
        self.uart.rx.extend(bytes(1024))
        with self.assertRaisesRegex(OSError, "backlog exceeds"):
            self.read()

    def test_timeout_tick_wrap_and_interruption_release_busy(self):
        self.uart.discovery = b""
        self.clock = (1 << 30) - 20
        with self.assertRaisesRegex(OSError, "timed out"):
            self.read()
        self.assertFalse(self.protocol._links["A"].busy)
        self.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.read()
        self.assertFalse(self.protocol._links["A"].busy)

    def test_uart_error_refused(self):
        self.uart.error = 8
        with self.assertRaisesRegex(OSError, "UART receive error"):
            self.read()

    def test_sensor_units_sentinels_and_ranges(self):
        color, distance, force = self.api.ColorSensor(), self.api.DistanceSensor(), self.api.ForceSensor()
        with patch.object(self.api, "_read", return_value=b"\xff"):
            self.assertEqual(color.color_id(), 255)
            with self.assertRaises(OSError):
                color.reflection()
            with self.assertRaises(OSError):
                force.force()
            with self.assertRaises(OSError):
                force.pressed()
        with patch.object(self.api, "_read", return_value=b"\xff\xff"):
            self.assertIsNone(distance.distance())
        with patch.object(self.api, "_read", return_value=b"\xfe\xff"):
            self.assertEqual(distance.distance(), 65534)
        with patch.object(self.api, "_read", return_value=b"\x01"):
            self.assertTrue(force.pressed())
        with patch.object(self.api, "_read", return_value=b"\x00"):
            self.assertFalse(force.pressed())
            self.assertEqual(color.ambient(), 0)
        with patch.object(self.api, "_read", return_value=b"\x64"):
            self.assertEqual(color.reflection(), 100)

    def test_encoder_integer_boundaries_and_speed_range(self):
        motor = self.api.Motor("A")
        for value in (-2147483648, -1, 0, 2147483647):
            with patch.object(self.api, "_read", return_value=struct.pack("<i", value)):
                self.assertEqual(motor.angle(), value)
        for raw, value in ((156, -100), (0, 0), (100, 100)):
            with patch.object(self.api, "_read", return_value=bytes((raw,))):
                self.assertEqual(motor.speed_percent(), value)
        with patch.object(self.api, "_read", return_value=b"\x7f"):
            with self.assertRaises(OSError):
                motor.speed_percent()

    def test_wrong_sensor_ports_and_busy_refused(self):
        for constructor in (self.api.ColorSensor, self.api.DistanceSensor, self.api.ForceSensor):
            for port in ("A", "F", 0, True, None):
                with self.assertRaises(ValueError):
                    constructor(port)
        self.assertEqual(self.uart.writes, [])
        link = self.protocol._Link("A", 48)
        link.busy = True
        with self.assertRaisesRegex(OSError, "busy"):
            link.read(2, 4)


if __name__ == "__main__":
    unittest.main()
