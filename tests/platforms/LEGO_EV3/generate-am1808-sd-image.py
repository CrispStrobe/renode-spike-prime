#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the deterministic 1 MiB SDSC image used by the AM1808 MMC tests."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


IMAGE_SIZE = 1024 * 1024
BLOCK_SIZE = 512
PATTERN_BASE = 0xA5A50000


def build_image() -> bytes:
    image = bytearray(b"\xff" * IMAGE_SIZE)
    for index in range(BLOCK_SIZE // 4):
        struct.pack_into("<I", image, index * 4, PATTERN_BASE + index)
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    args.output.write_bytes(build_image())


if __name__ == "__main__":
    main()
