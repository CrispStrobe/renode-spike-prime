#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run actual ARM926 SPI0/ADC/IRQ guest at three injected analog levels."""
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
    paths = [Path(value).resolve() for value in (args.platform, args.payload)]
    for path in paths:
        if any(char in str(path) for char in '\n\r\t;" '):
            raise ValueError('unsafe monitor path')
    cases = []
    with tempfile.TemporaryDirectory(prefix='ev3-adc-proof-') as directory:
        for raw in (0, 341, 1023):
            uart = Path(directory) / ('uart-%d.log' % raw)
            commands = ['mach create', 'machine LoadPlatformDescription @' + str(paths[0]),
                'sysbus LoadELF @' + str(paths[1]),
                'sysbus.spi0.ev3Adc SetChannelValue 6 %d' % raw,
                'sysbus WriteDoubleWord 0xffff1800 %d' % raw,
                'uart1 CreateFileBackend @%s true' % uart,
                'emulation RunFor "0.02"', 'echo "ADC_OBSERVED"',
                'sysbus ReadDoubleWord 0xffff1804', 'q']
            result = subprocess.run([args.renode, '--disable-gui', '--plain', '--console'] +
                [part for command in commands for part in ('-e', command)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
            if result.returncode or not uart.exists() or uart.read_text() != 'EV3 ADC SPI IRQ OK\n':
                raise RuntimeError('ADC guest failed at raw=%d:\n%s' % (raw, result.stdout[-16000:]))
            # The guest checks the physical event20, N+2 pipeline, channel tag,
            # left-aligned sample and full returned word before storing it.
            expected = 0x6000 | (raw << 2)
            if not re.search(r'ADC_OBSERVED[^\n]*\n(?:\s|\x1b\[[0-9;]*m)*0x0*%x\b' % expected,
                             result.stdout, re.IGNORECASE):
                raise RuntimeError('Missing exact observed ADC word:\n' + result.stdout[-16000:])
            cases.append({'channel': 6, 'raw': raw, 'spiWord': expected,
                          'uart': uart.read_text().rstrip('\n')})
    Path(args.receipt).write_text(json.dumps({'schema': 'brickwright.ev3.adc-guest.v1',
        'payloadSha256': hashlib.sha256(paths[1].read_bytes()).hexdigest(),
        'cases': cases, 'result': 'pass'}, sort_keys=True) + '\n')
    print('EV3 ADC GUEST OK: 3/3 injected levels, physical SPI0 IRQ20')


if __name__ == '__main__':
    main()
