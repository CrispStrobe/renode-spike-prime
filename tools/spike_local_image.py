#!/usr/bin/env python3
"""Load a caller-supplied Prime image into Renode without fetching firmware.

SPDX-License-Identifier: BSD-3-Clause
Copyright (c) 2026 Brickwright contributors

This bounded CPU probe does not establish peripheral/program compatibility.
Images, generated monitor scripts and diagnostic output must remain private.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess

FLASH_START = 0x08000000
FLASH_END = 0x08100000


def read_hex(data):
    memory = {}
    upper = 0
    eof = False
    for line in data.decode("ascii").splitlines():
        if not line.strip():
            continue
        if eof or not line.startswith(":"):
            raise ValueError("invalid Intel HEX record order")
        row = bytes.fromhex(line[1:])
        if len(row) < 5 or len(row) != row[0] + 5 or sum(row) % 256:
            raise ValueError("invalid Intel HEX length/checksum")
        count, address, kind = row[0], int.from_bytes(row[1:3], "big"), row[3]
        payload = row[4:-1]
        if kind == 0:
            for index, value in enumerate(payload):
                target = upper + address + index
                if not FLASH_START <= target < FLASH_END:
                    raise ValueError("HEX data outside physical Prime flash")
                if target in memory and memory[target] != value:
                    raise ValueError("conflicting HEX data")
                memory[target] = value
        elif kind == 1 and count == 0 and address == 0:
            eof = True
        elif kind in (2, 4) and count == 2 and address == 0:
            upper = int.from_bytes(payload, "big") << (4 if kind == 2 else 16)
        elif kind in (3, 5) and count == 4 and address == 0:
            pass  # Explicit vector-table selection determines CPU entry.
        else:
            raise ValueError("unsupported/malformed Intel HEX record")
    if not eof or not memory:
        raise ValueError("incomplete Intel HEX image")
    return memory


def read_image(path, kind, load_address):
    data = path.read_bytes()
    if kind == "hex":
        return read_hex(data)
    if len(data) < 8 or not FLASH_START <= load_address < FLASH_END or load_address + len(data) > FLASH_END:
        raise ValueError("raw image outside physical Prime flash")
    return dict(enumerate(data, load_address))


def vectors(memory, address):
    if address % 128:
        raise ValueError("unaligned vector table")
    try:
        sp, pc = struct.unpack("<II", bytes(memory[address + index] for index in range(8)))
    except KeyError as error:
        raise ValueError("missing vector table") from error
    if not 0x20000000 < sp <= 0x20050000 or sp % 8 or not pc & 1 or (pc & ~1) not in memory:
        raise ValueError("invalid Prime stack/reset vectors")
    return sp, pc


def stage_platform(root, output):
    relative = ("boards/spike-prime.repl", "boards/spike-prime-brick-devices.repl",
                "cpus/stm32f413vg.repl", "cpus/stm32f4.repl")
    for name in relative:
        source = (root / "platforms" / name).read_text()
        # Register names are debug metadata; the topology never needs an SVD download.
        source = "\n".join(line for line in source.splitlines() if "ApplySVD @https://" not in line) + "\n"
        if "https://" in source or "http://" in source:
            raise ValueError("platform still has a network dependency")
        target = output / "platforms" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    return output / "platforms/boards/spike-prime.repl"


def probe(args):
    output = args.private_output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    if any(output.iterdir()):
        raise ValueError("private output must be empty; prior evidence is preserved")
    memory = read_image(args.image, args.format, args.load_address)
    sp, pc = vectors(memory, args.vector_address)
    start, end = min(memory), max(memory) + 1
    image = output / "image.bin"
    image.write_bytes(bytes(memory.get(address, 255) for address in range(start, end)))
    image.chmod(0o600)
    platform = stage_platform(args.platform_root.resolve(), output)
    # Quote paths for the Renode monitor, never a shell.
    def quote(path):
        value = str(path)
        if any(character.isspace() or character in ('"', ';', "'") for character in value):
            raise ValueError("unsupported monitor path characters")
        return '@' + value
    script = output / "probe.resc"
    snapshot = output / "cpu.json"
    includes = tuple("include " + quote(path.resolve()) for path in args.model_source)
    script.write_text("\n".join(includes + (
        "mach create", "machine LoadPlatformDescription " + quote(platform),
        "sysbus LoadBinary " + quote(image) + " " + hex(start),
        "cpu VectorTableOffset " + hex(args.vector_address), "cpu SP " + hex(sp), "cpu PC " + hex(pc),
        "cpu ExecutionMode SingleStep", "cpu Step " + str(args.steps),
        "python \"import json; f=open('" + str(snapshot).replace("'", "\\'") + "','w'); json.dump({'pc':int(self.Machine['sysbus.cpu'].PC.RawValue), 'sp':int(self.Machine['sysbus.cpu'].SP.RawValue)},f); f.close()\"",
        "quit", "")))
    script.chmod(0o600)
    with (output / "renode.log").open("wb") as log:
        result = subprocess.run([str(args.renode.resolve()), "--disable-xwt", "--console", "--plain", str(script)],
                                stdout=log, stderr=subprocess.STDOUT, timeout=60)
    log = (output / "renode.log").read_text(errors="replace")
    if result.returncode or "There was an error" in log or not snapshot.is_file():
        raise ValueError("Renode probe failed; diagnostics remain in private output")
    state = json.loads(snapshot.read_text())
    if state["pc"] == (pc & ~1):
        raise ValueError("CPU did not change PC; inspect private diagnostics")
    print("Vector validation and bounded CPU probe completed; program/peripheral compatibility remains unproven.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--format", choices=("raw", "hex"), required=True)
    parser.add_argument("--load-address", type=lambda s: int(s, 0), default=0x08008000)
    parser.add_argument("--vector-address", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--renode", type=Path, required=True)
    parser.add_argument("--model-source", type=Path, action="append", default=[],
                        help="local C# peripheral source required by the installed Renode")
    parser.add_argument("--platform-root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="local offline platform source root")
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=2000)
    args = parser.parse_args()
    if not 1 <= args.steps <= 100000:
        parser.error("CPU probe requires 1..100000 instructions")
    try:
        probe(args)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, "Local firmware probe failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
