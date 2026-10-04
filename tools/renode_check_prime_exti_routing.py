# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Exercise actual Prime GPIO/SYSCFG/EXTI topology without guest firmware.

Derived from our public firmware routing fixture. Runs against both native
models and staged source aliases; requires a fresh, paused Prime machine.
"""


def mc_check_prime_exti_routing():
    machine = monitor.Machine
    if not machine.IsPaused:
        raise ValueError('Prime routing fixture requires a paused machine')
    port_a = machine['sysbus.gpioPortA']
    port_b = machine['sysbus.gpioPortB']
    port_c = machine['sysbus.gpioPortC']
    syscfg = machine['sysbus.syscfg']
    exti = machine['sysbus.exti']
    bit = 1 << 9
    exti.WriteDoubleWord(0x00, bit)
    exti.WriteDoubleWord(0x08, bit)
    exti.WriteDoubleWord(0x0c, bit)
    exti.WriteDoubleWord(0x14, bit)

    def pending(pin, expected):
        flag = bool(exti.ReadDoubleWord(0x14) & (1 << pin))
        if flag != expected or exti.Connections[pin].IsSet != expected:
            raise AssertionError('EXTI pending/output mismatch on line ' + str(pin))

    def edge(port, value):
        port.OnGPIO(9, value)
        pending(9, True)
        exti.WriteDoubleWord(0x14, bit)
        pending(9, False)

    def reject(port):
        for unused in range(8):
            port.OnGPIO(9, True)
            port.OnGPIO(9, False)
            pending(9, False)

    pending(9, False)
    reject(port_c)
    edge(port_a, True)
    edge(port_a, False)
    syscfg.WriteDoubleWord(0x10, 2 << 4)
    pending(9, False)
    reject(port_a)
    edge(port_c, True)
    edge(port_c, False)
    syscfg.Reset()
    if syscfg.ReadDoubleWord(0x10) != 0:
        raise AssertionError('SYSCFG reset did not restore port A routing')
    reject(port_c)
    edge(port_a, True)
    edge(port_a, False)

    # These physical pins must still reach both SYSCFG and their original
    # device endpoints after replacing the inherited direct EXTI wiring.
    endpoints = ((port_a, 13, 'power'), (port_a, 15, 'display'),
                 (port_b, 12, 'primeStorageMux'), (port_c, 10, 'speaker'))
    receiver_types = {'power': 'BrickPowerController', 'display': 'TLC5955',
                      'primeStorageMux': 'SPIMultiplexer', 'speaker': 'PCMAudioSink'}
    targets = {}
    for port, pin, name in endpoints:
        receivers = [endpoint.Receiver for endpoint in port.Connections[pin].Endpoints
                     if endpoint.Number == 0 and endpoint.Receiver.GetType().Name == receiver_types[name]]
        if len(receivers) != 1:
            raise AssertionError('Missing or duplicated preserved GPIO endpoint: ' + name)
        targets[name] = receivers[0]

    mask = (1 << 13) | (1 << 15) | (1 << 12) | (1 << 10)
    exti.WriteDoubleWord(0x00, mask)
    exti.WriteDoubleWord(0x08, mask)
    exti.WriteDoubleWord(0x0c, mask)
    # EXTICR3 line10=C; EXTICR4 line12=B, line13=A, line15=A.
    syscfg.WriteDoubleWord(0x10, 2 << 8)
    syscfg.WriteDoubleWord(0x14, 1)
    for port, pin, unused in endpoints:
        mode = port.ReadDoubleWord(0)
        port.WriteDoubleWord(0, (mode & ~(3 << (pin * 2))) | (1 << (pin * 2)))
        port.WriteDoubleWord(0x18, 1 << (pin + 16))
    exti.WriteDoubleWord(0x14, mask)
    for port, pin, name in endpoints:
        port.WriteDoubleWord(0x18, 1 << pin)
        pending(pin, True)
        exti.WriteDoubleWord(0x14, 1 << pin)
        pending(pin, False)
        if name == 'power' and not targets['power'].PowerHold:
            raise AssertionError('PA13 did not drive power hold')
        if name == 'speaker' and not targets['speaker'].Enabled:
            raise AssertionError('PC10 did not enable speaker')
        before = targets['display'].LatchedFrames
        port.WriteDoubleWord(0x18, 1 << (pin + 16))
        pending(pin, True)
        exti.WriteDoubleWord(0x14, 1 << pin)
        pending(pin, False)
        if name == 'display' and targets['display'].LatchedFrames != before + 1:
            raise AssertionError('PA15 falling edge did not latch display')
        if name == 'power' and targets['power'].PowerHold:
            raise AssertionError('PA13 did not release power hold')
        if name == 'speaker' and targets['speaker'].Enabled:
            raise AssertionError('PC10 did not disable speaker')
    print('PASS Prime GPIO/SYSCFG/EXTI routing and 4 preserved device endpoints')
