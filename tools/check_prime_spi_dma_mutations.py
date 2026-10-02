#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Show that the synthetic SPI/DMA regression detects two receive faults.

No firmware, network access or published run artifacts are needed. Each
mutant runs in a new private output directory against staged source models.
"""
import argparse
from pathlib import Path
import subprocess
from check_prime_source_models import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infrastructure', type=Path, required=True)
    parser.add_argument('--renode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('output already exists; prior evidence is preserved')
    output.mkdir(mode=0o700, parents=True)
    faults = (
        ('stale-request', '''                    if(direction.Value == Direction.PeripheralToMemory)
                    {
                        pendingPeripheralRequest = false;
                    }''', '', 'consumed CPU byte must not trigger DMA: 32 / 31'),
        ('fifo-overread', '''case Direction.PeripheralToMemory:
                    // FIFO threshold governs memory-side buffering; it does
                    // not authorize extra reads of a peripheral data register.
                    // Each request supplies exactly one peripheral data unit.
                    requestedSize = PeripheralDataSizeInBytes;''',
         '''case Direction.PeripheralToMemory:
                    requestedSize = directMode.Value ? FIFOThresholdInBytes : PeripheralDataSizeInBytes;''',
         'ordered DMA response:'),
    )
    for name, before, after, expected in faults:
        run = output / name
        prepare(args.infrastructure.resolve(), run)
        models = run / 'models.cs'
        source = models.read_text()
        if source.count(before) != 1:
            raise ValueError('mutation target no longer matches: ' + name)
        models.write_text(source.replace(before, after))
        with (run / 'mutation.log').open('wb') as log:
            result = subprocess.run(
                [str(args.renode.resolve()), '--disable-xwt', '--console', '--plain', str(run / 'test.resc')],
                stdout=log, stderr=subprocess.STDOUT, timeout=180)
        transcript = (run / 'mutation.log').read_text(errors='replace')
        if result.returncode == 0 or expected not in transcript:
            raise SystemExit('mutation was not detected as expected: ' + name)
        print('Detected SPI receive fault: ' + name)


if __name__ == '__main__':
    main()
