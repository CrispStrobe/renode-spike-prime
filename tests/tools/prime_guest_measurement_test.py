#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import prime_guest_measurement as measurement


class MeasurementTests(unittest.TestCase):
    def test_growth_keeps_the_post_warmup_baseline_across_reclamation(self):
        def sample(rss, cycle=10, wall=15):
            return {'rssKiB':rss,'wallSeconds':wall,'progress':{'cycle':cycle}}
        samples=[sample(900000,9),sample(100000),sample(10000),sample(110000)]
        self.assertEqual(measurement.workload_growth(samples),10000)
        self.assertEqual(measurement.workload_growth([sample(100000),sample(165536)]),65536)
        with self.assertRaisesRegex(RuntimeError,'growth exceeded'):
            measurement.workload_growth([sample(100000),sample(165537)])
        with self.assertRaisesRegex(RuntimeError,'insufficient'):
            measurement.workload_growth([sample(100000),sample(200000,wall=14)])

    def test_real_child_exit_and_guard_failures_leave_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root/'run.log').open('wb') as log:
                for label, timeout, ceiling, failure in (
                        ('pass', 5, 1536*1024, None),
                        ('timeout', 0, 1536*1024, TimeoutError),
                        ('memory', 5, 1, RuntimeError)):
                    receipt = root/(label+'.json')
                    release = root/(label+'.release')
                    def observed(pid):
                        release.write_text('sampled')
                        return 1024
                    # Real owned subprocess; only RSS values are controlled to
                    # make the ceiling branch independent of host load.
                    with patch.object(measurement, 'process_rss_kib', side_effect=observed):
                        command = [sys.executable, '-c',
                                   'import pathlib,sys,time\n'
                                   'while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)', str(release)]
                        if failure:
                            with self.assertRaises(failure):
                                measurement.run_measured(command, log, receipt, timeout, ceiling)
                        else:
                            self.assertEqual(measurement.run_measured(command, log, receipt, timeout, ceiling), 0)
                    record = json.loads(receipt.read_text())
                    self.assertEqual(record['observedPeakKiB'], 1024)
                    self.assertEqual(record['failure'] is None, failure is None)
                    self.assertIsInstance(record['returncode'], int)
                    self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
