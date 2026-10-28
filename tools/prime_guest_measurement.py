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
        for line in status.read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1])
        return None
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'rss='], capture_output=True,
                            text=True, timeout=5)
    return int(result.stdout.strip()) if result.stdout.strip() else None


def run_measured(command, log, receipt, timeout_seconds, ceiling_kib=1536*1024):
    samples, failure = [], None
    start = time.monotonic()
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - start
            rss = process_rss_kib(process.pid)
            if rss is not None:
                samples.append({'wallSeconds': elapsed, 'rssKiB': rss})
                if rss > ceiling_kib:
                    raise RuntimeError('emulator exceeded the fixed RSS ceiling (%d KiB)' % ceiling_kib)
            if elapsed >= timeout_seconds:
                raise TimeoutError('emulator exceeded the qualification wall-time guard')
            time.sleep(1)
        if not samples:
            raise RuntimeError('emulator exited without a resource observation')
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
                                       'observedPeakKiB': max((s['rssKiB'] for s in samples), default=None),
                                       'samples': samples}, indent=2)+'\n')
        receipt.chmod(0o600)
