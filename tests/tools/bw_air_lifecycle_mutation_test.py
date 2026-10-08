#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Require assertions against two mutations of actual helper source."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / 'tests/tools/bw_air_lifecycle_test.py'
source = (ROOT / 'tools/bw-air/hci_node.py').read_text()
mutants = [
    ('leave-drain-running',
     'if isinstance(sink, PacedSink):\n                    await sink.close()',
     'if isinstance(sink, PacedSink):\n                    pass',
     'Lifecycle.test_eof_joins_sink_and_closes_owned_writers'),
    ('replace-delivery-error',
     '                        await sink.task\n',
     '                        await asyncio.gather(sink.task, return_exceptions=True)\n',
     'Lifecycle.test_write_failure_is_observed_and_propagated'),
]
with tempfile.TemporaryDirectory(prefix='bw-air-mutants-') as directory:
    for name, old, new, case in mutants:
        assert source.count(old) == 1, name
        path = Path(directory) / (name + '.py'); path.write_text(source.replace(old, new))
        result = subprocess.run([sys.executable, str(TEST), case],
            env={**os.environ, 'BW_AIR_LIFECYCLE_SOURCE': str(path)},
            text=True, capture_output=True, timeout=10)
        assert result.returncode != 0 and 'AssertionError:' in result.stderr, result.stderr
        assert 'FAILED (failures=1)' in result.stderr, result.stderr
        print(name + ': DETECTED by assertion')
