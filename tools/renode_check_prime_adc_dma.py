# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Check the real Prime ADC/DMA terminal handshake without loading firmware.

Requires a fresh paused fixture machine; uses synthetic samples and SRAM data.
"""

from Antmicro.Renode.Time import TimeInterval
from System import UInt64


def mc_check_prime_adc_dma():
    machine = monitor.Machine
    if not machine.IsPaused:
        raise ValueError('ADC DMA terminal fixture requires a paused machine')
    adc = machine['sysbus.adc1']
    dma = machine['sysbus.dma2']
    bus = machine.SystemBus
    address = 0x2003f100
    adc.Reset()
    dma.Reset()
    adc.SetChannelValue(0, 1234)
    adc.SetChannelValue(2, 2345)
    bus.WriteDoubleWord(address - 4, 0x12345678)
    bus.WriteDoubleWord(address + 4, 0x87654321)
    adc.WriteDoubleWord(4, 1 << 8)  # SCAN; EOCIE disabled.
    adc.WriteDoubleWord(0x2c, 1 << 20)
    adc.WriteDoubleWord(0x34, 0 | (2 << 5))
    adc.WriteDoubleWord(8, 1 | (1 << 8))  # ADON, DMA, DDS=0.
    stream_control = 1 | (1 << 10) | (1 << 11) | (1 << 13)

    def prepare_stream():
        dma.WriteDoubleWord(0x10, 0)
        dma.WriteDoubleWord(8, 1 << 5)
        dma.WriteDoubleWord(0x14, 2)
        dma.WriteDoubleWord(0x18, 0x4001204c)
        dma.WriteDoubleWord(0x1c, address)
        bus.WriteWord(address, 0xa55a)
        bus.WriteWord(address + 2, 0xa55a)
        dma.WriteDoubleWord(0x10, stream_control)  # TCIE disabled.

    def scan():
        adc.WriteDoubleWord(8, 1 | (1 << 8) | (1 << 30))
        for unused in range(2):
            machine.ClockSource.Advance(TimeInterval.FromNanoseconds(UInt64(100000)), True)

    def buffer_is(values):
        actual = [int(bus.ReadWord(address + 2 * index)) for index in range(2)]
        if actual != values:
            raise AssertionError('ADC DMA terminal fixture data mismatch: %r != %r' % (actual, values))
        if bus.ReadDoubleWord(address - 4) != 0x12345678 or bus.ReadDoubleWord(address + 4) != 0x87654321:
            raise AssertionError('ADC DMA exceeded the synthetic two-halfword buffer')

    def completed():
        if dma.ReadDoubleWord(0x14) != 0 or dma.ReadDoubleWord(0x10) & 1:
            raise AssertionError('Normal DMA transfer did not exhaust NDTR and clear EN')
        if not dma.ReadDoubleWord(0) & (1 << 5) or dma.Connections[0].IsSet:
            raise AssertionError('Terminal transfer must latch TCIF without a TCIE-disabled IRQ')
        if not adc.ReadDoubleWord(8) & (1 << 8):
            raise AssertionError('DDS=0 completion must leave the ADC DMA bit set')

    prepare_stream()
    scan()
    buffer_is([1234, 2345])
    completed()
    prepare_stream()
    scan()  # Re-enabling only the controller must not rearm the ADC.
    buffer_is([0xa55a, 0xa55a])
    if dma.ReadDoubleWord(0x14) != 2:
        raise AssertionError('DDS=0 kept requesting after its terminal transfer')
    adc.WriteDoubleWord(8, 1)  # Required ADC DMA=0 then DMA=1 transition.
    adc.WriteDoubleWord(8, 1 | (1 << 8))
    scan()
    buffer_is([1234, 2345])
    completed()
    adc.Reset()
    dma.Reset()
    print('PASS Prime ADC DMA terminal handshake: DDS=0 transfer, suppression, rearm, TCIE=0')


def mc_check_prime_dma_abort():
    """Restart a partially filled buffer through the actual ADC/DMA board pair."""
    machine = monitor.Machine
    if not machine.IsPaused:
        raise ValueError('DMA abort fixture requires a paused machine')
    adc = machine['sysbus.adc1']
    dma = machine['sysbus.dma2']
    bus = machine.SystemBus
    completions = []

    def observe_completion(value):
        if value:
            completions.append(True)

    dma.TransferComplete0.AddStateChangedHook(observe_completion)
    old_address = 0x2003f140
    new_address = 0x2003f180
    control = 1 | (1 << 10) | (1 << 11) | (1 << 13)
    adc.Reset()
    dma.Reset()
    for address in (old_address, new_address):
        bus.WriteWord(address - 2, 0xface)
        bus.WriteWord(address, 0xa55a)
        bus.WriteWord(address + 2, 0xa55a)
        bus.WriteWord(address + 4, 0xbeef)

    def prepare_adc():
        adc.Reset()
        adc.SetChannelValue(0, 1234)
        adc.SetChannelValue(2, 2345)
        adc.WriteDoubleWord(4, 1 << 8)
        adc.WriteDoubleWord(0x2c, 1 << 20)
        adc.WriteDoubleWord(0x34, 2 << 5)
        adc.WriteDoubleWord(8, 1 | (1 << 8) | (1 << 9))

    prepare_adc()
    dma.WriteDoubleWord(0x14, 2)
    dma.WriteDoubleWord(0x18, 0x4001204c)
    dma.WriteDoubleWord(0x1c, old_address)
    dma.WriteDoubleWord(0x10, control)
    adc.WriteDoubleWord(8, 1 | (1 << 8) | (1 << 9) | (1 << 30))
    machine.ClockSource.Advance(TimeInterval.FromNanoseconds(UInt64(100000)), True)
    if bus.ReadWord(old_address) != 1234 or dma.ReadDoubleWord(0x14) != 1:
        raise AssertionError('DMA abort fixture did not stop after its first sample')
    dma.WriteDoubleWord(0x10, 0)
    if completions or dma.TransferComplete0.IsSet:
        raise AssertionError('Partial disable must not publish terminal acknowledgement')
    prepare_adc()
    dma.WriteDoubleWord(0x14, 2)
    dma.WriteDoubleWord(0x18, 0x4001204c)
    dma.WriteDoubleWord(0x1c, new_address)
    dma.WriteDoubleWord(0x10, control)
    adc.WriteDoubleWord(8, 1 | (1 << 8) | (1 << 9) | (1 << 30))
    for unused in range(2):
        machine.ClockSource.Advance(TimeInterval.FromNanoseconds(UInt64(100000)), True)
    if [int(bus.ReadWord(new_address + 2 * i)) for i in range(2)] != [1234, 2345]:
        raise AssertionError('Reprogrammed DMA buffer did not restart at its base')
    if bus.ReadWord(old_address + 2) != 0xa55a:
        raise AssertionError('Aborted buffer received another sample')
    for address in (old_address, new_address):
        if bus.ReadWord(address - 2) != 0xface or bus.ReadWord(address + 4) != 0xbeef:
            raise AssertionError('DMA abort/rearm crossed a synthetic buffer guard')
    if dma.ReadDoubleWord(0x14) != 0 or dma.ReadDoubleWord(0x10) & 1:
        raise AssertionError('Reprogrammed DMA did not complete its two samples')
    if len(completions) != 1:
        raise AssertionError('Only the restarted complete buffer may acknowledge')
    adc.Reset()
    dma.Reset()
    print('PASS Prime DMA abort/rearm: new buffer base, preserved guards, no abort acknowledgement')
