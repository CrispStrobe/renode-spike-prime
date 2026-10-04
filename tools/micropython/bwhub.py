# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
# Matrix mapping contract: retained MIT TLC5955 model interface.
# Retained mapping attribution: Copyright (c) 2019-2023 The Pybricks Authors.
# The SDK does not reproduce their driver implementation.
"""Hub interfaces for the retained Prime simulation profile, not hardware firmware.

Register/channel facts come from the retained MIT LSM6DS3TRC, TLC5955,
PrimeButtonLadder and PCMAudioSink interfaces and public board overlay.
"""
from machine import mem8, mem32
from time import sleep_ms, ticks_ms, ticks_diff
from bwspike import _integer, _mode, _level, _alternate

_busy = set()
_MATRIX = (38, 36, 41, 46, 33, 37, 28, 39, 47, 21, 24, 29, 31,
           45, 23, 26, 27, 32, 34, 22, 25, 40, 30, 35, 9)


def _claim(name):
    if name in _busy:
        raise OSError(name + " is busy")
    _busy.add(name)


def _poll(address, mask, started):
    while not mem32[address] & mask:
        if ticks_diff(ticks_ms(), started) >= 1000:
            raise OSError("hub peripheral timed out")
        sleep_ms(1)


class Display:
    """Latched 5x5 matrix; row-major retained-model orientation."""
    def show(self, pixels):
        if type(pixels) not in (list, tuple) or len(pixels) != 25:
            raise ValueError("display requires 25 integer grayscale values")
        frame = bytearray(97)
        for channel, value in zip(_MATRIX, pixels):
            _integer(value, 0, 65535, "grayscale")
            frame[channel * 2 + 1] = value >> 8
            frame[channel * 2 + 2] = value & 255
        _claim("display")
        try:
            started = ticks_ms()
            # SPI1, software NSS, 8-bit master; PA15 is LAT, not NSS.
            for pin in (5, 7):
                _alternate(0x40020000, pin, 5)
                _mode(0x40020000, pin, 2)
            _mode(0x40020000, 15, 1)
            _level(0x40020000, 15, False)
            mem32[0x40013000] = 0x37c
            for value in frame:
                _poll(0x40013008, 2, started)
                mem8[0x4001300c] = value
                _poll(0x40013008, 1, started)
                mem8[0x4001300c]
            _level(0x40020000, 15, True)
            _level(0x40020000, 15, False)
        finally:
            _level(0x40020000, 15, False)
            _busy.remove("display")

    def clear(self):
        self.show([0] * 25)


class Buttons:
    """Read deterministic ADC ladder combinations on the retained board."""
    def raw(self):
        _claim("buttons")
        try:
            started = ticks_ms()
            result = []
            for gpio, pin, channel in ((0x40020800, 4, 14), (0x40020000, 1, 1)):
                _mode(gpio, pin, 3)
                mem32[0x40012008] = 0
                mem32[0x40012004] = 0
                mem32[0x4001202c] = 0
                mem32[0x40012034] = channel
                mem32[0x40012008] = 1
                mem32[0x40012008] = 1 | (1 << 30)
                _poll(0x40012000, 2, started)
                value = mem32[0x4001204c]
                if not 0 <= value <= 4095:
                    raise OSError("button ADC sample outside range")
                result.append(value)
            return tuple(result)
        finally:
            mem32[0x40012008] = 0
            _busy.remove("buttons")

    def pressed(self):
        center, shared = self.raw()
        # Exact deterministic samples from PrimeButtonLadder, not physical thresholds.
        combinations = {4095: 0, 2646: 1, 3201: 2, 2234: 3,
                        3633: 4, 2432: 5, 2882: 6, 2055: 7}
        if center not in (4095, 3010) or shared not in combinations:
            raise OSError("unsupported button ladder sample")
        flags = combinations[shared]
        return tuple(name for name, down in (("center", center == 3010),
                     ("left", flags & 1), ("right", flags & 2),
                     ("bluetooth", flags & 4)) if down)


_I2C = 0x40005800


def _i2c_poll(mask, started):
    while True:
        status = mem32[_I2C + 0x14]
        if status & 0x0f00:
            raise OSError("IMU I2C transaction error")
        if ticks_diff(ticks_ms(), started) >= 1000:
            raise OSError("IMU I2C timed out")
        if status & mask:
            return
        sleep_ms(1)


def _i2c_address(read, started):
    # ACK/POS stay clear: each receive transaction reads exactly one byte.
    mem32[_I2C] = 0x101
    _i2c_poll(1, started)
    mem8[_I2C + 0x10] = 0xd5 if read else 0xd4
    _i2c_poll(2, started)
    mem32[_I2C + 0x18]


def _i2c_register(register, started, value=None):
    _i2c_address(False, started)
    _i2c_poll(0x80, started)
    mem8[_I2C + 0x10] = register
    _i2c_poll(4, started)
    if value is not None:
        _i2c_poll(0x80, started)
        mem8[_I2C + 0x10] = value
        _i2c_poll(4, started)
        mem32[_I2C] = 0x201
        return
    _i2c_address(True, started)
    mem32[_I2C] = 0x201
    _i2c_poll(0x40, started)
    return mem8[_I2C + 0x10]


class IMU:
    """Signed raw register samples through the retained CPU I2C2 interface."""
    def _read(self, register, count):
        _claim("imu")
        try:
            started = ticks_ms()
            # Reset only the controller, not the sensor. No firmware I2C module.
            mem32[_I2C] = 0x8000
            mem32[_I2C] = 0
            mem32[_I2C + 4] = 50
            mem32[_I2C + 0x1c] = 250
            mem32[_I2C + 0x20] = 51
            mem32[_I2C] = 1
            if _i2c_register(0x0f, started) != 0x6a:
                raise OSError("unsupported IMU identity")
            _i2c_register(0x12, started, 4)
            data = bytearray(count)
            for i in range(count):
                data[i] = _i2c_register(register + i, started)
            values = []
            for i in range(0, count, 2):
                value = data[i] | data[i + 1] << 8
                values.append(value - 65536 if value & 32768 else value)
            return tuple(values)
        finally:
            # STOP, reset and disable discard pending traffic on every exit.
            mem32[_I2C] = 0x201
            mem32[_I2C] = 0x8000
            mem32[_I2C] = 0
            _busy.remove("imu")

    def acceleration_raw(self):
        return self._read(0x28, 6)

    def angular_rate_raw(self):
        return self._read(0x22, 6)

    def temperature_raw(self):
        return self._read(0x20, 2)[0]


class Sound:
    """Bounded bytes to the modeled PCM observation sink; no host playback."""
    def write_pcm8(self, samples):
        if type(samples) is not bytes or not 1 <= len(samples) <= 4096:
            raise ValueError("PCM requires 1..4096 immutable bytes")
        _claim("sound")
        try:
            _mode(0x40020800, 10, 1)
            _level(0x40020800, 10, True)
            for value in samples:
                mem8[0x40007408] = value
        finally:
            _level(0x40020800, 10, False)
            _busy.remove("sound")
