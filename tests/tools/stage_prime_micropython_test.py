# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Packaging contract tests; no firmware or physical-model equivalence claim."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import stage_prime_micropython as profile


class SupportProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.infrastructure = self.root / "infrastructure"
        self.infrastructure.mkdir()
        names = ["src/Emulator/Peripherals/Peripherals/" + name for name in
                 tuple(profile.CORE) + profile.OTHER + ("Timers/STM32TLCClock.cs",)]
        names.append("licenses/MIT.txt")
        for name in names:
            target = self.infrastructure / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture source " + name + "\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "synthetic source closure")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.pin = patch.object(profile, "INFRASTRUCTURE_COMMIT", self.commit)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.infrastructure), *args], text=True)

    def staged_fixture(self, infrastructure, output, aggregate_display):
        self.assertTrue(aggregate_display)
        output.mkdir()
        for name in profile.FILES:
            if name in ("boot-seed.bin", "program-uart.cs") or name.startswith(("tools/", "scripts/")):
                continue
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture\n")
        (output / "platforms/cpus/stm32f413vg.repl").write_text(
            "cpu:\n    PerformanceInMips: 96\nnvic:\n    systickFrequency: 96000000\n"
            "timer1:\n    frequency: 96000000\n")
        (output / "platforms/boards/spike-prime.repl").write_text("spi2:\n")

    def test_manifest_seed_clocks_and_closed_file_set(self):
        output = self.root / "support"
        with patch.object(profile, "stage", self.staged_fixture):
            profile.assemble(self.infrastructure, output)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(set(manifest), set(profile.FILES))
        self.assertEqual({str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()},
                         set(profile.FILES) | {"manifest.json"})
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
        seed = (output / "boot-seed.bin").read_bytes()
        self.assertEqual(len(seed), 65536)
        self.assertIn(profile.BOOT, seed)
        self.assertEqual(seed[510:512], b"\x55\xaa")
        clock = (output / "platforms/cpus/stm32f413vg.repl").read_text()
        self.assertIn("systickFrequency: 100000000", clock)
        self.assertIn("PerformanceInMips: 100", clock)
        self.assertNotIn("96000000", clock)
        self.assertIn("bufferCapacity: 1", (output / "platforms/boards/spike-prime.repl").read_text())

    def test_modified_model_or_license_refused_before_output(self):
        for name in ("licenses/MIT.txt", "src/Emulator/Peripherals/Peripherals/" + next(iter(profile.CORE))):
            with self.subTest(name=name):
                target = self.infrastructure / name
                original = target.read_bytes()
                target.write_bytes(original + b"mutation\n")
                output = self.root / "refused"
                with self.assertRaisesRegex(ValueError, "pinned public commit"):
                    profile.assemble(self.infrastructure, output)
                self.assertFalse(output.exists())
                target.write_bytes(original)

    def test_unavailable_reference_refused_before_output_without_checkout_changes(self):
        output = self.root / "missing-reference"
        original_head = self.git("rev-parse", "HEAD")
        with patch.object(profile, "INFRASTRUCTURE_COMMIT", "0" * 40):
            with self.assertRaisesRegex(ValueError, "reference commit is unavailable"):
                profile.assemble(self.infrastructure, output)
        self.assertFalse(output.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), original_head)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_existing_package_preserved(self):
        output = self.root / "existing"
        output.mkdir()
        (output / "important").write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "prior packages are preserved"):
            profile.assemble(self.infrastructure, output)
        self.assertEqual((output / "important").read_bytes(), b"preserve")

    def test_unknown_clock_geometry_refused(self):
        def broken(infrastructure, output, aggregate_display):
            self.staged_fixture(infrastructure, output, aggregate_display)
            (output / "platforms/cpus/stm32f413vg.repl").write_text("cpu:\n")
        with patch.object(profile, "stage", broken):
            with self.assertRaisesRegex(ValueError, "clock profile"):
                profile.assemble(self.infrastructure, self.root / "broken")


if __name__ == "__main__":
    unittest.main()
