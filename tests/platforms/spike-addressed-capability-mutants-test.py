#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Require named assertions for source mutants, never setup/import failures."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT/'tools/spike_nuttx_mailbox.py').read_text()
controls = (ROOT/'tests/platforms/spike-nuttx-mailbox-test.py').read_text()
mutants = [
    ('image', 'digest != image_hash', 'False', 'test_addressed_sensor_metadata_refused_before_any_read'),
    ('marker', 'return int(read_word(address)) == 1', 'return True', 'test_addressed_capability_requires_live_marker_and_ready_mailbox'),
    ('ready', 'if publication == 0 or publication & 1:', 'if False:', 'test_addressed_capability_requires_live_marker_and_ready_mailbox'),
]
for name, old, new, intended in mutants:
    # The legacy storage helper intentionally has the same marker comparison.
    if name == 'marker':
        start = source.index('def supports_addressed_distance(')
        end = source.index('def _header(', start)
        block = source[start:end]
        assert block.count(old) == 1
        broken = source[:start] + block.replace(old, new) + source[end:]
    else:
        assert source.count(old) == 1
        broken = source.replace(old, new)
    with tempfile.TemporaryDirectory(prefix='bw-live-capability-mutant-') as folder:
        tree = Path(folder)
        (tree/'tools').mkdir();(tree/'tests/platforms').mkdir(parents=True)
        (tree/'tools/spike_nuttx_mailbox.py').write_text(broken)
        fixture = tree/'tests/platforms/spike-nuttx-mailbox-test.py'
        fixture.write_text(controls)
        result = subprocess.run([sys.executable, str(fixture)], text=True, capture_output=True)
        assert result.returncode == 1 and 'FAIL: '+intended in result.stderr and 'AssertionError' in result.stderr, name
        assert 'ERROR:' not in result.stderr, name
        print('Assertion-detected addressed capability mutant:', name)
