#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Qualify our source-built protected NuttX robot runner offline in Renode.

Generated configs/results/logs go only into a NEW private output directory.
No images are fetched and no physical hub connection is used.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
from stage_prime_runtime import stage
from spike_nuttx_mailbox import validate_base


def vector(elf):
    raw = elf.read_bytes()
    if raw[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', raw, 18)[0] != 40:
        raise ValueError('expected our source-built ARM ELF32')
    phoff = struct.unpack_from('<I', raw, 28)[0]
    phsize, count = struct.unpack_from('<HH', raw, 42)
    for i in range(count):
        p = phoff + phsize * i
        if phsize < 32 or p + 32 > len(raw): raise ValueError('invalid ELF program headers')
        kind, offset, address, physical, size = struct.unpack_from('<5I', raw, p)
        if kind == 1 and address <= 0x08008000 and address + size >= 0x08008008:
            sp, pc = struct.unpack_from('<II', raw, offset + 0x08008000 - address)
            if sp % 8 or not 0x20000000 < sp <= 0x20020000 or not pc & 1 or not 0x08008000 <= pc < 0x08060000:
                raise ValueError('reset vector exceeds protected kernel')
            return sp, pc
    raise ValueError('kernel reset vector was not found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware-root', type=Path, required=True)
    parser.add_argument('--infrastructure', type=Path, required=True)
    parser.add_argument('--renode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=600)
    args = parser.parse_args()
    if not 60 <= args.timeout_seconds <= 1800: raise ValueError('qualification timeout must be 60-1800 seconds')
    root = Path(__file__).resolve().parents[1]
    output, firmware = args.output.resolve(), args.firmware_root.resolve()
    kernel, user = firmware / 'nuttx/nuttx', firmware / 'nuttx/nuttx_user.elf'
    for p in (output, kernel, user, root):
        if re.search(r'[\s"\'@;\\]', str(p)): raise ValueError('paths contain monitor metacharacters')
    if output.exists(): raise ValueError('output already exists; prior evidence is preserved')
    sp, pc = vector(kernel)
    symbols = subprocess.check_output(['arm-none-eabi-nm', str(user)], text=True)
    match = re.search(r'^([a-fA-F0-9]+)\s+\w\s+g_bw_program_debug$', symbols, re.M)
    if not match: raise ValueError('our firmware program mailbox was not found')
    base = validate_base(int(match.group(1), 16))
    kernel_symbols = subprocess.check_output(['arm-none-eabi-nm', '-S', str(kernel)], text=True)
    ramlog = re.search(r'^([a-fA-F0-9]+)\s+([a-fA-F0-9]+)\s+\w\s+g_sysbuffer$', kernel_symbols, re.M)
    if not ramlog: raise ValueError('qualification requires our kernel RAM log')
    ramlog_base, ramlog_size = (int(value, 16) for value in ramlog.groups())
    if ramlog_size > 32768 or not 0x20000000 <= ramlog_base < ramlog_base + ramlog_size <= 0x20020000:
        raise ValueError('kernel RAM log exceeds the protected kernel memory')
    output.mkdir(mode=0o700, parents=True)
    runtime = output / 'runtime'
    stage(args.infrastructure.resolve(), runtime, True)
    config = output / 'config.json'
    config.write_text(json.dumps({'tools': str(root / 'tools'), 'programMailbox': base, 'ramlogBase': ramlog_base, 'ramlogSize': ramlog_size, 'result': str(output / 'result.json')}))
    config.chmod(0o600)
    scenario = output / 'check.resc'
    scenario.write_text('\n'.join((
        'include @' + str(runtime / 'models.cs'), 'mach create',
        'machine LoadPlatformDescription @' + str(runtime / 'platforms/boards/spike-prime.repl'),
        'emulation CreatePrimeElectricalPorts "machine-0"', 'sysbus LoadELF @' + str(kernel),
        'sysbus LoadELF @' + str(user), 'cpu VectorTableOffset 0x08008000',
        'cpu SP ' + str(sp), 'cpu PC ' + str(pc), 'emulation RunFor "1.0"',
        'python "import json; _bw_nuttx_config=json.load(open(\'' + str(config) + '\'))"',
        'python "execfile(\'' + str(root / 'tests/firmware/nuttx-robot-fixture.py') + '\')"', 'quit', '')))
    with (output / 'run.log').open('wb') as log:
        result = subprocess.run([str(args.renode.resolve()), '--disable-xwt', '--console', '--plain', str(scenario)],
                                stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout_seconds)
    report = output / 'result.json'
    if result.returncode or not report.exists() or json.loads(report.read_text()).get('passed') is not True:
        raise SystemExit('Full NuttX robot scenarios failed; inspect private output')
    report.chmod(0o600)
    print('Full protected NuttX robot program scenarios passed.')


if __name__ == '__main__':
    main()
