#!/usr/bin/env python3
"""Tests for the local full-machine fault/resource/soak gate.

SPDX-License-Identifier: MIT
"""

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/spike-fault-resource-soak.py"
SPEC = importlib.util.spec_from_file_location("spike_fault_resource_soak", TOOL)
SOAK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOAK)


class StubManifest:
    def __init__(self, available=(), failure=None):
        self.available = set(available)
        self.failure = failure

    def verify(self, target, _root):
        if target == self.failure:
            raise ValueError("secret /path digest")
        return {} if target in self.available else None

    @staticmethod
    def catalog():
        return {"targets": dict.fromkeys(SOAK.FIXTURES)}


class FaultResourceSoakTests(unittest.TestCase):
    def test_discovers_every_and_only_verified_local_target(self):
        expected = ["lego-prime-v2", "brickwright-nuttx"]
        actual = SOAK.available_targets("unused", StubManifest(expected))
        self.assertEqual(actual, expected)

    def test_verification_failure_suppresses_private_details(self):
        with self.assertRaises(SOAK.SoakError) as caught:
            SOAK.available_targets("unused", StubManifest(failure="lego-prime-v3"))
        self.assertNotIn("/path", str(caught.exception))
        self.assertNotIn("digest", str(caught.exception))

    def test_catalog_drift_fails_closed(self):
        manifest = StubManifest()
        manifest.catalog = lambda: {"targets": {"new-target": {}}}
        with self.assertRaisesRegex(SOAK.SoakError, "fixture map differ"):
            SOAK.available_targets("unused", manifest)

    def test_command_has_fixed_repeat_and_isolated_results(self):
        command = SOAK.test_command("pybricks-prime", 5, pathlib.Path("results"))
        self.assertEqual(command[command.index("--repeat") + 1], "5")
        self.assertEqual(command[command.index("--fixture") + 1], SOAK.FIXTURES["pybricks-prime"])
        self.assertIn("--stop-on-error", command)

    @unittest.skipUnless(pathlib.Path("/proc/self/status").exists(), "requires Linux procfs")
    def test_measures_process_tree_rss(self):
        with tempfile.TemporaryDirectory() as temporary:
            returncode, peak_kib = SOAK.run_measured(
                [sys.executable, "-c", "x=bytearray(16*1024*1024); import time; time.sleep(.15)"],
                cwd=temporary, environment=os.environ.copy(), timeout_seconds=2,
            )
        self.assertEqual(returncode, 0)
        self.assertGreaterEqual(peak_kib, 12 * 1024)


if __name__ == "__main__":
    unittest.main()
