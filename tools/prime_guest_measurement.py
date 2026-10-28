# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bound and retain actual emulator process RSS and wall-time observations."""
import json
from pathlib import Path
import subprocess
import time


def process_rss_kib(pid):
    status = Path('/proc') / str(pid) / 'status'
    if status.exists():
        try:
            lines = status.read_text().splitlines()
        except FileNotFoundError:
            return None # the child can exit between poll and the read
        for line in lines:
            if line.startswith('VmRSS:'):
                return int(line.split()[1])
        return None
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'rss='], capture_output=True,
                            text=True, timeout=5)
    return int(result.stdout.strip()) if result.stdout.strip() else None


def workload_growth(samples):
    measured = [s['rssKiB'] for s in samples if s['wallSeconds'] >= 15
                and s.get('progress', {}).get('cycle', 0) >= 10]
    if len(measured) < 2:
        raise RuntimeError('insufficient post-warmup workload RSS observations')
    # Match the existing R04 growth definition. A working-set decrease from
    # GC or host reclamation is not growth and must not lower the baseline.
    growth = max(measured)-measured[0]
    if growth > 64*1024:
        raise RuntimeError('workload RSS growth exceeded 64 MiB after warmup')
    return growth


def run_measured(command, log, receipt, timeout_seconds, ceiling_kib=1536*1024, progress=None):
    samples, failure, growth = [], None, None
    start = time.monotonic()
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - start
            rss = process_rss_kib(process.pid)
            if rss is not None:
                sample = {'wallSeconds': elapsed, 'rssKiB': rss}
                if progress is not None and progress.exists():
                    try:
                        sample['progress'] = json.loads(progress.read_text())
                    except json.JSONDecodeError:
                        pass # the observer may sample an in-progress write
                samples.append(sample)
                if rss > ceiling_kib:
                    raise RuntimeError('emulator exceeded the fixed RSS ceiling (%d KiB)' % ceiling_kib)
            if elapsed >= timeout_seconds:
                raise TimeoutError('emulator exceeded the qualification wall-time guard')
            time.sleep(1)
        if not samples:
            raise RuntimeError('emulator exited without a resource observation')
        if progress is not None and process.returncode == 0:
            growth = workload_growth(samples)
        return process.returncode
    except BaseException as error:
        failure = str(error)
        raise
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        receipt.write_text(json.dumps({'scope': 'owned emulator process sampled RSS; not a continuous peak or guest heap',
                                       'wallSeconds': time.monotonic()-start,
                                       'returncode': process.returncode, 'failure': failure,
                                       'ceilingKiB': ceiling_kib,
                                       'growthBoundKiB': 64*1024 if progress is not None else None,
                                       'growthKiB': growth,
                                       'warmup': {'minimumWallSeconds': 15, 'minimumCycles': 10} if progress is not None else None,
                                       'observedPeakKiB': max((s['rssKiB'] for s in samples), default=None),
                                       'samples': samples}, indent=2)+'\n')
        receipt.chmod(0o600)
