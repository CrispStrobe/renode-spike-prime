#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove guest-controlled four-motor motion through actual GPIO encoder IRQs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--renode', required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--payload', required=True)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    platform, payload = (Path(value).resolve() for value in (args.platform, args.payload))
    for path in (platform, payload):
        if any(char in str(path) for char in '\n\r\t;" '):
            raise ValueError('unsafe monitor path')
    phases = ('Forward', 'Reverse', 'Brake', 'Coast')
    properties = ('State', 'Direction', 'DutyCycle', 'TachometerCount', 'EmittedEdges')
    with tempfile.TemporaryDirectory(prefix='ev3-motor-proof-') as directory:
        uart = Path(directory) / 'uart.log'
        commands = ['logLevel 3', 'mach create', 'machine LoadPlatformDescription @' + str(platform)]
        commands += ['sysbus LoadELF @' + str(payload), 'uart1 CreateFileBackend @%s true' % uart]
        for phase in range(4):
            commands += ['sysbus WriteDoubleWord 0xffff1810 %d' % phase,
                         'emulation RunFor "%s"' % ('0.1' if phase < 2 else '0.02')]
            for name, address in (('ack', 0xffff1818), ('seen', 0xffff1814)):
                commands += ['echo "MOTOR_PROOF_%d_%s"' % (phase, name),
                             'sysbus ReadDoubleWord 0x%x' % address]
            for port in 'ABCD':
                for prop in properties:
                    commands += ['echo "MOTOR_PROOF_%d_%s_%s"' % (phase, port, prop),
                                 'sysbus.gpio.motor%s %s' % (port, prop)]
        commands.append('q')
        result = subprocess.run([args.renode, '--disable-gui', '--plain', '--console'] +
                                [part for command in commands for part in ('-e', command)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=120)
        output = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', result.stdout)
        if result.returncode or not uart.exists() or uart.read_text() != 'EV3 MOTOR PWM4 TACHO IRQ47 IRQ48 OK\n':
            raise RuntimeError('Motor guest UART failed:\n' + output[-24000:])

        def value(label):
            match = re.search(r'^MOTOR_PROOF_%s\s*\n' % re.escape(label), output, re.MULTILINE)
            if not match:
                raise RuntimeError('Missing motor observation %s:\n%s' % (label, output[-24000:]))
            for line in output[match.end():].splitlines()[:12]:
                line = line.strip().strip('"')
                if line.startswith('MOTOR_PROOF_'):
                    break
                if re.fullmatch(r'(?:0x[0-9a-fA-F]+|-?\d+(?:\.\d+)?|Forward|Reverse|Brake|Coast)', line):
                    return line
            raise RuntimeError('Missing motor property %s:\n%s' % (label, output[-24000:]))

        def signed(label, bits):
            number = int(value(label), 0)
            return number - (1 << bits) if number >= (1 << (bits - 1)) else number

        observations = []
        for phase, state in enumerate(phases):
            ack = int(value('%d_ack' % phase), 0)
            seen = int(value('%d_seen' % phase), 0)
            assert ack == phase and seen == 15, (phase, ack, seen)
            motors = []
            for port in 'ABCD':
                prefix = '%d_%s_' % (phase, port)
                motor = {'port': port, 'state': value(prefix + 'State'),
                         'direction': signed(prefix + 'Direction', 32),
                         'dutyCycle': float(value(prefix + 'DutyCycle')),
                         'tachometerCount': signed(prefix + 'TachometerCount', 64),
                         'emittedEdges': int(value(prefix + 'EmittedEdges'), 0)}
                assert motor['state'] == state, (phase, motor)
                assert motor['direction'] == (1, -1, 0, 0)[phase], (phase, motor)
                assert abs(motor['dutyCycle'] - 0.5) < 1e-9
                if phase == 0:
                    assert 4 <= motor['tachometerCount'] <= 5
                    assert motor['emittedEdges'] == motor['tachometerCount']
                elif phase == 1:
                    before = observations[0]['motors']['ABCD'.index(port)]
                    reverse_edges = motor['emittedEdges'] - before['emittedEdges']
                    assert 4 <= reverse_edges <= 5
                    assert motor['tachometerCount'] == before['tachometerCount'] - reverse_edges
                else:
                    before = observations[phase - 1]['motors']['ABCD'.index(port)]
                    assert motor['tachometerCount'] == before['tachometerCount']
                    assert motor['emittedEdges'] == before['emittedEdges']
                motors.append(motor)
            observations.append({'phase': phase, 'state': state, 'encoderSeenMask': seen,
                                 'acknowledgedPhase': ack, 'motors': motors})
    Path(args.receipt).write_text(json.dumps({'schema': 'brickwright.ev3.motor-guest.v1',
        'payloadSha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
        'physicalInterrupts': [47, 48], 'phases': observations,
        'uart': 'EV3 MOTOR PWM4 TACHO IRQ47 IRQ48 OK', 'result': 'pass'}, sort_keys=True) + '\n')
    print('EV3 MOTOR GUEST OK: all four PWM sources, signed encoder IRQs, brake/coast')


if __name__ == '__main__':
    main()
