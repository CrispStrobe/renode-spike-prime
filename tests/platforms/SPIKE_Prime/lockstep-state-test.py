#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Robot Lab lockstep on the real Prime machine (renode-spike-prime#58).

Starts Renode with the Prime platform, the six electrical ports and a
source-built guest, programs the port A bridge to a fixed 25 % PWM through the
bus (the board's TIM1/GPIOE contract), and drives the actual state service:
lockstep.begin, N x lockstep.step, refusals, lockstep.end. Then, with
--profile, measures RunFor wall time for guest/port variants (R13-M).

Usage: lockstep-state-test.py --renode CMD [--models DIR] --busy ELF --idle ELF
       --result OUT.json [--steps N] [--profile]
``--renode`` is split on spaces (e.g. "dotnet output/bin/Release/Renode.dll").
``--models`` is a stage_prime_runtime.py output for a stock Renode.
"""
import argparse
import json
from pathlib import Path
import shlex
import socket
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
QUANTUM_US = 5000
LOCKSTEP = ('lockstep/v1', 'motor-bridge-drive/v1', 'external-shaft/v1')
# Port A: TIM1 CH1/CH2 on PE9/PE11, AF1 (PrimeElectricalPorts.cs definition A).
PWM_25 = ['sysbus WriteDoubleWord 0x40021000 0x00480000',  # GPIOE MODER: PE9 AF, PE11 output
          'sysbus WriteDoubleWord 0x40021014 0x00000800',  # GPIOE ODR: PE11 high
          'sysbus WriteDoubleWord 0x40021024 0x00000010',  # GPIOE AFRH: PE9 AF1
          'sysbus WriteDoubleWord 0x4001002c 999',         # TIM1 ARR
          'sysbus WriteDoubleWord 0x40010034 250',         # TIM1 CCR1
          'sysbus WriteDoubleWord 0x40010018 0x6060',      # PWM mode 1
          'sysbus WriteDoubleWord 0x40010020 0x33',        # CC1/CC2 enabled, inverted
          'sysbus WriteDoubleWord 0x40010044 0x8000',      # MOE
          'sysbus WriteDoubleWord 0x40010000 1']           # CEN


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def platform_lines(models, elf, ports=True):
    platform = (Path(models) if models else ROOT) / 'platforms/boards/spike-prime.repl'
    lines = (['include @' + str(Path(models) / 'models.cs')] if models else []) + [
        'mach create', 'machine LoadPlatformDescription @' + str(platform)]
    if ports:
        lines.append('emulation CreatePrimeElectricalPorts "machine-0"')
    return lines + ['sysbus LoadELF @' + str(elf), 'cpu VectorTableOffset 0x08000000', 'cpu SP 0x20050000']


def launch(renode, script, log):
    # The console reads stdin: keep a pipe open so the monitor stays alive.
    return subprocess.Popen(shlex.split(renode) + ['--disable-gui', '--plain', '--console', str(script)],
                            stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)


class Client(object):
    def __init__(self, port, deadline):
        while True:
            try:
                self.sock = socket.create_connection(('127.0.0.1', port), timeout=60)
                break
            except OSError:
                if time.time() > deadline:
                    raise SystemExit('state service never listened')
                time.sleep(0.2)
        self.file = self.sock.makefile('rwb')
        self.initial = self.read()
        self.seq, self.count = self.initial['seq'], 0

    def close(self):
        self.file.close()
        self.sock.close()

    def read(self):
        line = self.file.readline()
        if not line:
            raise SystemExit('state service closed the connection')
        return json.loads(line)

    def call(self, name, arguments):
        self.count += 1
        request = {'schemaVersion': 1, 'type': 'command', 'requestId': 'r%d' % self.count,
                   'command': name, 'arguments': arguments, 'expectedSeq': self.seq}
        started = time.perf_counter()
        self.file.write((json.dumps(request) + '\n').encode())
        self.file.flush()
        result = self.read()
        snapshot = self.read()
        wall = time.perf_counter() - started
        if result.get('type') != 'result' or snapshot.get('type') != 'snapshot':
            raise SystemExit('unexpected reply order')
        if snapshot['seq'] != self.seq + 1:
            raise SystemExit('snapshot seq %d after %d' % (snapshot['seq'], self.seq))
        self.seq = snapshot['seq']
        return result, snapshot, wall


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def lockstep(args, work):
    port = free_port()
    config = {'identity': {'board': 'spike-prime', 'firmware': 'brickwright-nuttx', 'transport': 'none',
                           'imageSha256': None},
              'paths': dict(('port' + p, 'external:port' + p) for p in 'ABCDEF'),
              'maxClients': 1, 'maxLineBytes': 262144, 'socketTimeoutSeconds': 60}
    (work / 'config.json').write_text(json.dumps(config))
    lines = platform_lines(args.models, args.busy) + PWM_25 + [
        'emulation RunFor "0.010"',
        'include @' + str(ROOT / 'scripts/spike-state-server.py'),
        'spike_state_start "127.0.0.1" %d "%s"' % (port, work / 'config.json')]
    script = work / 'lockstep.resc'
    script.write_text('\n'.join(lines) + '\n')
    log = open(work / 'lockstep.log', 'wb')
    proc = launch(args.renode, script, log)
    try:
        client = Client(port, time.time() + args.startup_seconds)
        result, begin, _ = client.call('lockstep.begin', {'quantumUs': QUANTUM_US})
        require(result['accepted'], 'begin: %s' % result.get('error'))
        require(result['data'] == begin, 'begin reply is the streamed snapshot')
        require(all(c in begin['target']['capabilities'] for c in LOCKSTEP), 'lockstep capabilities')
        t0, walls = begin['clockNs'], []
        position = 0
        for k in range(args.steps):
            shafts = [{'port': 'A', 'positionMdeg': position, 'speedMdps': 300000},
                      {'port': 'B', 'positionMdeg': -position, 'speedMdps': -300000}]
            result, frame, wall = client.call('lockstep.step', {
                'quantumUs': QUANTUM_US, 'expectClockNs': t0 + k * QUANTUM_US * 1000,
                'shafts': shafts, 'sensors': [{'port': 'D', 'kind': 'distance',
                                               'values': {'distanceMillimeters': 100 + k}}]})
            require(result['accepted'], 'step %d: %s' % (k, result.get('error')))
            require(result['data'] == frame, 'step reply is the streamed snapshot')
            require(frame['clockNs'] == t0 + (k + 1) * QUANTUM_US * 1000, 'clock after step %d: %d' % (k, frame['clockNs']))
            motors = dict((m['port'], m) for m in frame['motors'])
            a, b = motors['A'], motors['B']
            require(a['positionSource'] == 'external' and b['positionSource'] == 'external', 'external shafts')
            require(a['drive'] == {'mean': 2500.0, 'last': 2500, 'brakingTicks': 0, 'ticks': 5}, 'port A drive %r' % a['drive'])
            require(b['drive'] == {'mean': 0.0, 'last': 0, 'brakingTicks': 0, 'ticks': 5}, 'port B drive %r' % b['drive'])
            require(abs(a['position'] - (position / 1000.0 + 1.5)) < 1e-9, 'port A extrapolated %r' % a['position'])
            require(a['speedDps'] == 300.0 and not a['stalled'], 'port A speed')
            sensors = dict((s['port'], s) for s in frame['sensors'])
            require(sensors['D']['values']['distanceMillimeters'] == 100 + k, 'distance input applied')
            position += 1500
            walls.append(wall)
        clock = frame['clockNs']
        result, _, _ = client.call('lockstep.step', {'quantumUs': QUANTUM_US, 'expectClockNs': clock + 1,
                                                      'shafts': [], 'sensors': []})
        require(not result['accepted'] and 'expectClockNs' in result['error'], 'wrong clock refused')
        result, _, _ = client.call('arena.inputs', {'sensors': [], 'loads': [{'port': 'A', 'percent': 50}]})
        require(not result['accepted'], 'free-run input refused during lockstep')
        result, frame, _ = client.call('lockstep.end', {})
        require(result['accepted'] and frame['clockNs'] == clock, 'end keeps the clock')
        result, _, _ = client.call('lockstep.begin', {'quantumUs': QUANTUM_US})
        require(result['accepted'], 'begin again after end')
        client.call('lockstep.end', {})
        ordered = sorted(walls)
        return {'steps': args.steps, 'virtualMs': (clock - t0) / 1e6,
                'stepWallMedianMs': round(statistics.median(walls) * 1000, 3),
                'stepWallP90Ms': round(ordered[int(0.9 * len(ordered)) - 1] * 1000, 3),
                'virtualPerWall': round((clock - t0) / 1e9 / sum(walls), 4)}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def profile(args, work):
    results = work / 'profile.jsonl'
    # The board's motor PWM: TIM1 at PSC 7, ARR 1000 is the firmware's 11.99 kHz.
    pwm_12k = PWM_25[:3] + ['sysbus WriteDoubleWord 0x40010028 7', 'sysbus WriteDoubleWord 0x4001002c 1000'] + PWM_25[4:]
    variants = [('busy guest, no ports', args.busy, False, False, []),
                ('busy guest, six ports', args.busy, True, False, []),
                ('idle guest (WFI, 1 kHz SysTick), no ports', args.idle, False, False, []),
                ('idle guest (WFI, 1 kHz SysTick), six ports', args.idle, True, False, []),
                ('idle guest, six ports, advance immediately', args.idle, True, True, []),
                ('idle guest, six ports, TIM1 PWM 12 kHz', args.idle, True, False, pwm_12k),
                ('idle guest, six ports, TIM1 PWM 96 kHz', args.idle, True, False, PWM_25),
                ('idle guest, six ports, TIM1 PWM 12 kHz, advance immediately', args.idle, True, True, pwm_12k)]
    for label, elf, ports, immediate, extra in variants:
        lines = platform_lines(args.models, elf, ports) + extra
        lines += ['include @' + str(ROOT / 'tools/renode_lockstep_probe.py')]
        if immediate:
            lines.append('emulation SetGlobalAdvanceImmediately true')
        lines += ['emulation RunFor "0.010"',
                  'bw_runfor_probe %d %d "%s" "%s"' % (5000, args.profile_steps, results, label + ' / 5 ms'),
                  'bw_runfor_probe %d %d "%s" "%s"' % (100000, 5, results, label + ' / 100 ms'), 'quit']
        script = work / 'profile.resc'
        script.write_text('\n'.join(lines) + '\n')
        with open(work / 'profile.log', 'ab') as log:
            launch(args.renode, script, log).wait(timeout=args.startup_seconds + 600)
    return [json.loads(line) for line in results.read_text().splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renode', required=True)
    parser.add_argument('--models')
    parser.add_argument('--busy', required=True)
    parser.add_argument('--idle', required=True)
    parser.add_argument('--result', required=True)
    parser.add_argument('--steps', type=int, default=200)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--profile-steps', type=int, default=200)
    parser.add_argument('--startup-seconds', type=int, default=300)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='bw-lockstep-') as temporary:
        work = Path(temporary)
        report = {'lockstep': lockstep(args, work)}
        print(json.dumps(report['lockstep']), flush=True)
        if args.profile:
            report['runForProfile'] = profile(args, work)
        Path(args.result).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('PASS lockstep state service on the Prime machine')


if __name__ == '__main__':
    main()
