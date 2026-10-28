#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""R04 connection recovery and bounded-growth qualification on real Renode.

Uses a public source-built CPU guest and the actual state service and port
models. This does not qualify a NuttX program/storage workload or physical I/O.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import shlex
import subprocess
import tempfile
import time

SPEC = importlib.util.spec_from_file_location('lockstep_gate', Path(__file__).with_name('lockstep-state-test.py'))
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def resources(pid):
    proc = Path('/proc') / str(pid)
    if proc.exists():
        fields = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
        return {'rssKiB': int(fields['VmRSS'].split()[0]), 'threads': int(fields['Threads']),
                'fds': len(list((proc / 'fd').iterdir()))}
    def ps(*args):
        return subprocess.check_output(['ps', *args], text=True, timeout=5)
    rss = int(ps('-p', str(pid), '-o', 'rss=').strip())
    threads = len(ps('-M', '-p', str(pid), '-o', 'pid=').splitlines())
    listing = subprocess.check_output(['/usr/sbin/lsof', '-n', '-a', '-p', str(pid),
                                       '-d', '0-65535', '-F', 'f'], text=True, timeout=10)
    return {'rssKiB': rss, 'threads': threads, 'fds': sum(line.startswith('f') for line in listing.splitlines())}


def run(args, work):
    port = GATE.free_port()
    config = {'identity': {'board': 'spike-prime', 'firmware': 'brickwright-nuttx',
                           'transport': 'none', 'imageSha256': None},
              'paths': dict(('port' + p, 'external:port' + p) for p in 'ABCDEF'),
              'socketTimeoutSeconds': 0.2}
    config_path = work / 'config.json'
    config_path.write_text(json.dumps(config))
    status_path = work / 'service.json'
    probe = work / 'probe.py'
    probe.write_text('def mc_r04_record(path):\n'
                     '    import json\n'
                     '    with open(str(path), "w") as output:\n'
                     '        json.dump({"lastError": _state_server.last_error, "seq": _state_server.seq}, output)\n')
    start = 'spike_state_start "127.0.0.1" %d "%s"' % (port, config_path)
    script = work / 'recovery.resc'
    script.write_text('\n'.join(GATE.platform_lines(args.models, args.guest) + [
        'emulation RunFor "0.010"', 'include @' + str(GATE.ROOT / 'scripts/spike-state-server.py'),
        'include @' + str(probe), start]) + '\n')
    samples, restarts, clock = [], 0, None
    with (work / 'renode.log').open('wb') as log:
        process = GATE.launch(args.renode, script, log)
        try:
            def monitor(command):
                process.stdin.write((command + '\n').encode())
                process.stdin.flush()

            for cycle in range(args.cycles):
                client = GATE.Client(port, time.time() + 60)
                try:
                    if clock is not None:
                        GATE.require(client.initial['clockNs'] == clock, 'reconnect preserved paused clock')
                    GATE.require(client.initial['seq'] == 0, 'new connection resets sequence')
                    result, frame, _ = client.call('lockstep.begin', {'quantumUs': 5000})
                    GATE.require(result['accepted'], 'replacement lockstep.begin accepted')
                    result, frame, _ = client.call('lockstep.step', {
                        'quantumUs': 5000, 'expectClockNs': frame['clockNs'],
                        'shafts': [{'port': 'A', 'positionMdeg': cycle * 1000, 'speedMdps': 0}],
                        'sensors': [{'port': 'D', 'kind': 'distance',
                                     'values': {'distanceMillimeters': 100 + cycle}}]})
                    GATE.require(result['accepted'], 'motor/sensor step accepted')
                    GATE.require(frame['motors'][0]['positionSource'] == 'external', 'external shaft survives')
                    clock = frame['clockNs']
                    if (cycle + 1) % 10 == 0:
                        # Stop while a client owns lockstep; restart on this same machine.
                        monitor('spike_state_stop\n' + start)
                        client.sock.settimeout(5)
                        GATE.require(client.file.readline() == b'', 'monitor stop closes connected client')
                        restarts += 1
                    elif cycle % 2 == 0:
                        result, _, _ = client.call('lockstep.end', {})
                        GATE.require(result['accepted'], 'explicit lockstep.end accepted')
                    # Odd cycles disconnect without end, exercising abandonment.
                finally:
                    client.close()
                if (cycle + 1) % 10 == 0:
                    # Sample with a connected stream so descriptor counts are comparable.
                    settled = GATE.Client(port, time.time() + 10)
                    try:
                        GATE.require(settled.initial['clockNs'] == clock, 'restart preserved clock')
                        samples.append(dict(cycle=cycle + 1, **resources(process.pid)))
                    finally:
                        settled.close()

            # A bounded burst to a reader with a tiny receive window fills the
            # real .NET write buffer. Keep the socket open after send timeout.
            # Start a fresh listener so last_error cannot come from an earlier
            # client timing out during a resource sample.
            status_path.unlink(missing_ok=True)
            monitor('spike_state_stop\n' + start + '\nr04_record "%s"' % status_path)
            ready_deadline = time.monotonic() + 10
            while not status_path.exists():
                GATE.require(time.monotonic() < ready_deadline, 'fresh listener started')
                time.sleep(0.01)
            vanished = socket.socket()
            vanished.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            vanished.settimeout(2)
            vanished.connect(('127.0.0.1', port))
            try:
                burst = b''.join((json.dumps({'schemaVersion': 1, 'type': 'command',
                    'requestId': 'slow%d' % i, 'command': 'state.sample', 'arguments': {}}) + '\n').encode()
                    for i in range(4096))
                try:
                    vanished.sendall(burst)
                except socket.timeout:
                    pass
                deadline, failure, sequence = time.monotonic() + 15, '', None
                while time.monotonic() < deadline:
                    status_path.unlink(missing_ok=True)
                    monitor('r04_record "%s"' % status_path)
                    for _ in range(30):
                        if status_path.exists():
                            try:
                                status = json.loads(status_path.read_text())
                                failure, sequence = status['lastError'], status['seq']
                                break
                            except json.JSONDecodeError:
                                pass
                        time.sleep(0.01)
                    if failure:
                        break
                    time.sleep(0.1)
                GATE.require(bool(failure), 'non-reading live socket triggered a service error')
                GATE.require(sequence is not None and 0 < sequence < 4096,
                             'write failed before the queued sample burst was consumed')
                recovered = GATE.Client(port, time.time() + 10)
                try:
                    result, _, _ = recovered.call('lockstep.begin', {'quantumUs': 5000})
                    GATE.require(result['accepted'], 'service recovered while slow reader remains open')
                finally:
                    recovered.close()
            finally:
                vanished.close()
            GATE.require(len(samples) >= 3, 'at least three resource samples after warmup')
            # First sample follows ten cycles and one restart, warming dynamic code.
            growth = {key: max(s[key] for s in samples) - samples[0][key]
                      for key in ('rssKiB', 'threads', 'fds')}
            GATE.require(growth['rssKiB'] <= 64 * 1024, 'RSS growth <= 64 MiB after warmup')
            GATE.require(growth['threads'] <= 4, 'thread growth <= 4 after warmup')
            GATE.require(growth['fds'] <= 2, 'descriptor growth <= 2 after warmup')
            runtime = Path(shlex.split(args.renode)[-1])
            closure = (Path(args.models) / 'models.cs') if args.models else GATE.ROOT / 'src/Infrastructure'
            model_identity = ({'modelsSha256': hashlib.sha256(closure.read_bytes()).hexdigest()}
                              if args.models else {'infrastructureSource': subprocess.check_output(
                                  ['git', '-C', str(closure), 'rev-parse', 'HEAD'], text=True).strip()})
            return dict({'cycles': args.cycles, 'restarts': restarts, 'virtualNs': clock,
                    'slowReaderRecovered': True, 'slowReaderSnapshots': sequence,
                    'resourceSamples': samples, 'growth': growth,
                    'guestSha256': hashlib.sha256(Path(args.guest).read_bytes()).hexdigest(),
                    'runtimeSha256': hashlib.sha256(runtime.read_bytes()).hexdigest(),
                    'scope': 'source-built CPU guest, motor/sensor state service; no NuttX program/storage qualification'},
                    **model_identity)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renode', required=True)
    parser.add_argument('--models', help='stage_prime_runtime source package; omit for the compiled fork')
    parser.add_argument('--guest', required=True)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=50)
    args = parser.parse_args()
    if not 30 <= args.cycles <= 1000:
        parser.error('--cycles must be 30..1000')
    with tempfile.TemporaryDirectory(prefix='spike-r04-') as directory:
        result = run(args, Path(directory))
    args.result.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    print('PASS R04 Renode connection recovery and bounded growth')


if __name__ == '__main__':
    main()
