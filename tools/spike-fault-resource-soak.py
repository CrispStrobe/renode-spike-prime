#!/usr/bin/env python3
"""Run privacy-safe repeated full-machine SPIKE gates with an RSS ceiling.

SPDX-License-Identifier: MIT
"""

import argparse
import importlib.util
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_TOOL = ROOT / "tools/spike-firmware-scenarios/scenario_manifest.py"
DEFAULT_IMAGE_ROOT = ROOT / ".local/spike-firmware-scenarios"
DEFAULT_CYCLES = 3
DEFAULT_MEMORY_CEILING_MIB = 1536
DEFAULT_SEED = 0x5350494B
POLL_SECONDS = 0.02

FIXTURES = {
    "lego-prime-v2": "LEGO Prime v2 unchanged image progresses",
    "lego-prime-v3": "LEGO Prime v3 unchanged image progresses",
    "pybricks-prime": "Pybricks Prime unchanged image progresses",
    "spike-nx": "spike-nx unchanged protected image reaches boot boundaries",
    "brickwright-nuttx": "Brickwright NuttX Renode profile reaches daemon and state boundaries",
    "lego-essential": "LEGO Essential unchanged image progresses",
    "pybricks-essential": "Pybricks Essential unchanged image progresses",
}


class SoakError(RuntimeError):
    pass


def load_manifest_module():
    spec = importlib.util.spec_from_file_location("spike_scenario_manifest", MANIFEST_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def available_targets(image_root, manifest_module=None):
    manifest_module = manifest_module or load_manifest_module()
    if set(manifest_module.catalog()["targets"]) != set(FIXTURES):
        raise SoakError("scenario catalog and repeated-boot fixture map differ")
    result = []
    for target in FIXTURES:
        try:
            verified = manifest_module.verify(target, image_root)
        except Exception as error:
            # Do not propagate a potentially identifying artifact path or digest.
            raise SoakError(f"local input verification failed for {target}") from error
        if verified is not None:
            result.append(target)
    return result


def process_tree_rss_kib(root_pid):
    descendants = set()
    pending = [root_pid]
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        try:
            children = pathlib.Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii")
            pending.extend(int(child) for child in children.split())
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            pass

    total = 0
    for pid in descendants:
        try:
            for line in pathlib.Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
                    break
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
            continue
    return total


def run_measured(command, *, cwd, environment, timeout_seconds):
    process = subprocess.Popen(
        command, cwd=cwd, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    peak_kib = 0
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            peak_kib = max(peak_kib, process_tree_rss_kib(process.pid))
            if time.monotonic() >= deadline:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise SoakError("full-machine gate exceeded its fixed wall-time guard")
            time.sleep(POLL_SECONDS)
        peak_kib = max(peak_kib, process_tree_rss_kib(process.pid))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return process.returncode, peak_kib


def test_command(target, cycles, results_directory):
    return [
        sys.executable,
        str(ROOT / "tests/run_tests.py"),
        str(ROOT / "tests/platforms/SPIKE_Unchanged_Firmware.robot"),
        "--fixture", FIXTURES[target],
        "--repeat", str(cycles),
        "--results-dir", str(results_directory),
        "--stop-on-error",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=pathlib.Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--memory-ceiling-mib", type=int, default=DEFAULT_MEMORY_CEILING_MIB)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    if args.cycles < 2:
        parser.error("--cycles must be at least 2")
    if args.memory_ceiling_mib <= 0 or args.timeout_seconds <= 0:
        parser.error("resource ceilings must be positive")

    try:
        targets = available_targets(args.image_root)
        if not targets:
            print("SKIP: no locally supplied hash-verified images")
            return 77

        environment = os.environ.copy()
        environment["SPIKE_FIRMWARE_IMAGE_ROOT"] = str(args.image_root.resolve())
        environment["PYTHONHASHSEED"] = str(args.seed & 0xFFFFFFFF)
        ceiling_kib = args.memory_ceiling_mib * 1024
        with tempfile.TemporaryDirectory(prefix="spike-soak-") as temporary:
            results = pathlib.Path(temporary)
            for target in targets:
                returncode, peak_kib = run_measured(
                    test_command(target, args.cycles, results / target),
                    cwd=ROOT, environment=environment,
                    timeout_seconds=args.timeout_seconds,
                )
                if returncode != 0:
                    raise SoakError(f"repeated full-machine gate failed for {target}; private diagnostics suppressed")
                if peak_kib > ceiling_kib:
                    raise SoakError(
                        f"process-memory ceiling exceeded for {target}: "
                        f"{peak_kib // 1024} MiB > {args.memory_ceiling_mib} MiB"
                    )
                print(f"PASS {target}: {args.cycles} cycles, peak aggregate RSS {peak_kib // 1024} MiB")
    except SoakError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("error: unable to execute the local full-machine gate; private diagnostics suppressed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
