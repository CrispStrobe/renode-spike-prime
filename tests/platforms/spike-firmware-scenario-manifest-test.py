#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/spike-firmware-scenarios/scenario_manifest.py"


class ScenarioManifestTests(unittest.TestCase):
    def run_tool(self, root, *arguments):
        return subprocess.run(
            ["python3", str(TOOL), "--root", str(root), *arguments],
            text=True, capture_output=True, check=False,
        )

    def test_catalog_contains_the_seven_required_targets(self):
        result = self.run_tool("unused", "list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), {
            "lego-prime-v2", "lego-prime-v3", "pybricks-prime", "spike-nx",
            "brickwright-nuttx", "lego-essential", "pybricks-essential",
        })

    def test_absent_input_is_an_explicit_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_tool(temporary, "verify", "lego-prime-v2")
        self.assertEqual(result.returncode, 77)
        self.assertIn("SKIP", result.stdout)

    def test_prepare_and_verify_raw_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            image = root / "input.bin"
            image.write_bytes(b"unchanged opaque bytes")
            prepared = self.run_tool(root, "prepare", "lego-essential", "--artifact", f"firmware=raw=0x08000000={image}")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            verified = self.run_tool(root, "verify", "lego-essential", "--json")
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["manifest"]["target"], "lego-essential")

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            image = root / "input.bin"
            image.write_bytes(b"original")
            prepared = self.run_tool(root, "prepare", "pybricks-prime", "--artifact", f"firmware=raw=0x08008000={image}")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            (root / "pybricks-prime/firmware.raw").write_bytes(b"changed")
            verified = self.run_tool(root, "verify", "pybricks-prime")
            self.assertEqual(verified.returncode, 1)
            self.assertRegex(verified.stderr, "size mismatch|SHA-256 mismatch")

    def test_execution_output_does_not_disclose_hash_or_source_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            image = root / "private-name.bin"
            image.write_bytes(b"opaque")
            prepared = self.run_tool(root, "prepare", "lego-prime-v3", "--artifact", f"firmware=raw=0x08008000={image}")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            verified = self.run_tool(root, "verify", "lego-prime-v3", "--execution-json")
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertNotIn("sha256", verified.stdout)
            self.assertNotIn(str(root), verified.stdout)
            self.assertNotIn("private-name", verified.stdout)

    def test_protected_target_requires_both_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            image = root / "kernel.elf"
            image.write_bytes(b"\x7fELFfixture")
            result = self.run_tool(root, "prepare", "spike-nx", "--artifact", f"kernel=elf=0x08008000={image}")
            self.assertEqual(result.returncode, 1)
            self.assertIn("kernel, userspace", result.stderr)


if __name__ == "__main__":
    unittest.main()
