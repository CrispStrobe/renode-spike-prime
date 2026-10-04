# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded UART readers for Brickwright's qualified simulation attachments.

This is a simulation-profile interface, not a general LPF2 hardware driver.
Calls are serialized by the MicroPython program; topology changes require a
new session. No host telemetry, listeners or frontend state are accessed.
"""
from machine import mem32
from time import sleep_ms, ticks_ms, ticks_diff

# UART address, TX GPIO/pin, RX GPIO/pin, alternate function, UART input Hz.
_PORTS = {
    "A": (0x40007800, 0x40021000, 8, 0x40021000, 7, 8, 50000000),
    "B": (0x40004c00, 0x40020c00, 1, 0x40020c00, 0, 8, 50000000),
    "C": (0x40007c00, 0x40021000, 1, 0x40021000, 0, 8, 50000000),
    "D": (0x40005000, 0x40020800, 12, 0x40020c00, 2, 8, 50000000),
    "E": (0x40011c00, 0x40021000, 3, 0x40021000, 2, 11, 100000000),
}
_links = {}


def _field(address, shift, width, value):
    mask = ((1 << width) - 1) << shift
    mem32[address] = (mem32[address] & ~mask) | (value << shift)


class _Link:
    def __init__(self, port, device_type):
        self.uart, self.tx_gpio, self.tx_pin, self.rx_gpio, self.rx_pin, self.af, self.hz = _PORTS[port]
        self.device_type = device_type
        self.ready = False
        self.busy = False

    def _check_time(self):
        if ticks_diff(ticks_ms(), self.started) >= 1000:
            raise OSError("LPF2 read timed out")

    def _byte(self):
        while True:
            self._check_time()
            status = mem32[self.uart]
            if status & 15:
                mem32[self.uart + 4]  # Consume DR to clear the error condition.
                raise OSError("LPF2 UART receive error")
            if status & 32:
                return mem32[self.uart + 4] & 255
            sleep_ms(1)

    def _write(self, data):
        for value in data:
            while not mem32[self.uart] & 128:
                self._check_time()
                sleep_ms(1)
            self._check_time()
            mem32[self.uart + 4] = value

    def _frame(self):
        header = self._byte()
        if header < 64:
            return header, b""
        length = (1 << ((header >> 3) & 7)) + (1 if header & 192 == 128 else 0)
        if length > 33:
            raise OSError("LPF2 frame exceeds bound")
        data = bytearray(length)
        checksum = header
        for index in range(length):
            data[index] = self._byte()
            checksum ^= data[index]
        checksum ^= self._byte()
        if checksum != 255:
            raise OSError("LPF2 checksum mismatch")
        return header, data

    def _open(self):
        if self.ready:
            return
        mem32[self.uart + 12] = 0  # No IRQ/DMA: this API polls the CPU UART.
        mem32[self.uart + 16] = 0
        mem32[self.uart + 20] = 0
        mem32[self.uart + 8] = (self.hz + 57600) // 115200
        mem32[self.uart + 12] = 0x200c
        # Set AF before enabling TX; the port announces only after TX is AF.
        for gpio, pin in ((self.rx_gpio, self.rx_pin), (self.tx_gpio, self.tx_pin)):
            _field(gpio + (32 if pin < 8 else 36), (pin % 8) * 4, 4, self.af)
            _field(gpio, pin * 2, 2, 2)
        found_type = False
        for _ in range(128):
            header, data = self._frame()
            if header == 64:
                if len(data) != 1 or data[0] != self.device_type:
                    raise OSError("LPF2 attachment type mismatch")
                found_type = True
            if header == 4:
                if not found_type:
                    raise OSError("LPF2 discovery missing device type")
                self._write(b"\x04")
                self.ready = True
                return
        raise OSError("LPF2 discovery exceeds frame bound")

    def read(self, mode, length):
        if self.busy:
            raise OSError("LPF2 port is busy")
        self.busy = True
        self.started = ticks_ms()
        try:
            self._open()
            # Discard already queued reports, then request a fresh mode report.
            for _ in range(1024):
                self._check_time()
                if not mem32[self.uart] & 32:
                    break
                mem32[self.uart + 4]
            else:
                raise OSError("LPF2 receive backlog exceeds bound")
            self._write(bytes((0x43, mode, 0xff ^ 0x43 ^ mode)))
            for _ in range(128):
                header, data = self._frame()
                if header & 192 == 192 and header & 7 == mode:
                    if len(data) != length:
                        raise OSError("LPF2 data length mismatch")
                    return data
            raise OSError("LPF2 mode reply exceeds frame bound")
        finally:
            self.busy = False


def read(port, device_type, mode, length):
    link = _links.get(port)
    if link is None:
        link = _Link(port, device_type)
        _links[port] = link
    elif link.device_type != device_type:
        raise OSError("LPF2 port already belongs to another attachment type")
    return link.read(mode, length)
