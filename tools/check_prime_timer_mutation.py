#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check that the synthetic timer regression detects a missing zero compare.

Stages source models only; no firmware, network or published run artifact is
needed. The output must be a new private directory.
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
    prepare(args.infrastructure.resolve(), output)
    models = output / 'models.cs'
    source = models.read_text()
    target = """                    if(Direction == Direction.Ascending && ccTimers[i].Limit == 0 && ccInterruptEnable[i])
                    {
                        ccInterruptFlag[i] = true;
                    }"""
    if source.count(target) != 1:
        raise ValueError('zero-compare mutation target no longer matches')
    models.write_text(source.replace(target, ''))
    log_path = output / 'mutation.log'
    with log_path.open('wb') as log:
        result = subprocess.run(
            [str(args.renode.resolve()), '--disable-xwt', '--console', '--plain', str(output / 'test.resc')],
            stdout=log, stderr=subprocess.STDOUT, timeout=180)
    log_path.chmod(0o600)
    transcript = log_path.read_text(errors='replace')
    if result.returncode == 0 or 'source fixture equality failed: 2 / 0' not in transcript:
        raise SystemExit('missing zero compare was not detected as expected')
    print('Detected timer fault: missing rollover zero compare')


if __name__ == '__main__':
    main()
