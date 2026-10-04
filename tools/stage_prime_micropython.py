#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Assemble the closed native MicroPython support profile, offline.

Only pinned public model sources and an authored synthetic boot seed are used.
No firmware, executable, user program, or qualification log is packaged.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from spike_micropython_filesystem import build_seed
from stage_prime_runtime import CORE, OTHER, stage

INFRASTRUCTURE_COMMIT = "43741b47a7fbdb74ae8c9abd670a6491c61642e8"
FILES = (
    "models.cs", "program-uart.cs", "boot-seed.bin",
    "platforms/boards/spike-prime.repl",
    "platforms/boards/spike-prime-brick-devices.repl",
    "platforms/cpus/stm32f413vg.repl", "platforms/cpus/stm32f4.repl",
    "scripts/spike-state-server.py", "tools/spike_state_monitor_protocol.py",
    "tools/ev3_state_observer.py", "tools/spike_arena_inputs.py",
    "tools/spike_arena_mailbox.py", "tools/spike_nuttx_mailbox.py",
    "tools/spike_program_uart.py", "licenses/renode-models-MIT.txt",
    "licenses/brickwright-BSD-3-Clause.txt",
)
BOOT = (b"# SPDX-License-Identifier: BSD-3-Clause\n"
        b"# Copyright (c) 2026 Brickwright contributors\n"
        b"import os, machine\n"
        b"os.dupterm(machine.UART(2, 115200), 0)\n"
        b"print('BW_MICRO_READY')\n")


def compact_module(source):
    """Remove our comments/docstrings, keeping attribution and executable AST."""
    class StripDocs(ast.NodeTransformer):
        def visit(self, node):
            node = super().visit(node)
            if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                    and node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
            return node
    header = "\n".join(source.splitlines()[:2]) + "\n"
    if "SPDX-License-Identifier: BSD-3-Clause" not in header or "Copyright" not in header:
        raise ValueError("authored module must retain its license and copyright header")
    tree = ast.fix_missing_locations(StripDocs().visit(ast.parse(source)))
    body = ast.unparse(tree)
    body = "\n".join(" " * ((len(line) - len(line.lstrip())) // 2) + line.lstrip()
                     for line in body.splitlines()) + "\n"
    if ast.dump(ast.parse(body)) != ast.dump(tree):
        raise ValueError("module compaction changed executable syntax")
    return (header + body).encode("utf8")


def verify_sources(infrastructure):
    """Check only the consumed source closure; never reset another checkout."""
    available = subprocess.run(
        ["git", "-C", str(infrastructure), "cat-file", "-e",
         INFRASTRUCTURE_COMMIT + "^{commit}"], capture_output=True, check=False)
    if available.returncode:
        raise ValueError("pinned public reference commit is unavailable; fetch " +
                         INFRASTRUCTURE_COMMIT + " before offline assembly")
    names = ["src/Emulator/Peripherals/Peripherals/" + name
             for name in tuple(CORE) + OTHER + ("Timers/STM32TLCClock.cs",)]
    names.append("licenses/MIT.txt")
    for name in names:
        result = subprocess.run(
            ["git", "-C", str(infrastructure), "show", INFRASTRUCTURE_COMMIT + ":" + name],
            capture_output=True, check=False)
        if result.returncode:
            raise ValueError("pinned public reference lacks required source: " + name)
        if result.stdout != (infrastructure / name).read_bytes():
            raise ValueError("model source does not match the pinned public commit: " + name)


def assemble(infrastructure, output):
    if output.exists():
        raise ValueError("output already exists; prior packages are preserved")
    verify_sources(infrastructure)
    root = Path(__file__).resolve().parents[1]
    stage(infrastructure, output, aggregate_display=True)
    # This application profile uses 100 MHz HCLK/timer inputs and a paced
    # 50 MHz storage SPI with one receive slot. It is not the NuttX profile.
    clock = output / "platforms/cpus/stm32f413vg.repl"
    source, count = re.subn(r"(?m)^(    systickFrequency:) [0-9]+$",
                            r"\1 100000000", clock.read_text())
    if count != 1 or source.count("PerformanceInMips: 96") != 1:
        raise ValueError("unexpected Prime clock profile")
    source = source.replace("PerformanceInMips: 96", "PerformanceInMips: 100")
    source = source.replace("frequency: 96000000", "frequency: 100000000")
    clock.write_text(source)
    board = output / "platforms/boards/spike-prime.repl"
    source = board.read_text()
    if source.count("spi2:\n") != 1:
        raise ValueError("unexpected Prime storage configuration")
    board.write_text(source.replace("spi2:\n", "spi2:\n    frequency: 50000000\n    bufferCapacity: 1\n"))
    shutil.copyfile(root / "tools/spike_program_uart.cs", output / "program-uart.cs")
    modules = {"boot.py": BOOT}
    for name in ("bwspike.py", "_bwlpf2.py", "_bwctrl.py"):
        modules[name] = compact_module((root / "tools/micropython" / name).read_text())
    (output / "boot-seed.bin").write_bytes(build_seed(modules))
    for name in FILES:
        target = output / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
    manifest = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                for name in FILES}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        assemble(args.infrastructure.resolve(), args.output.resolve())
    except (OSError, ValueError) as error:
        parser.exit(1, "Support assembly failed: " + str(error) + "\n")
    print("Closed support profile assembled; supply firmware separately.")
