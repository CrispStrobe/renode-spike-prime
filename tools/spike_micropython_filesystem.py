# Copyright (c) 2026 Brickwright contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Build an original synthetic FAT16 prefix for retained-system integration.

The firmware supplies a virtual MBR; this prefix begins at the volume boot
sector. It is not a complete disk image or a simulator independence claim.
"""

import re
import struct


SEED_SIZE = 65536
SECTOR_SIZE = 512
CLUSTER_SIZE = 2048
FAT_START = 512
FAT_SIZE = 63 * SECTOR_SIZE
ROOT_START = 32768
ROOT_ENTRIES = 128
DATA_START = ROOT_START + ROOT_ENTRIES * 32

# Canonical lowercase DOS short names: no paths, spaces, or alternate spellings.
_PART = r"[a-z0-9!#$%&'()\-@^_`{}~]"
_NAME = re.compile(rf"{_PART}{{1,8}}(?:\.{_PART}{{1,3}})?", re.ASCII)


def build_seed(files):
    """Return a 65536-byte FAT16 prefix containing the supplied byte payloads.

    ``files`` must be a nonempty dict of canonical ASCII lowercase 8.3 names.
    All directory entries and allocated clusters must fit inside the prefix.
    """
    if not isinstance(files, dict) or not files:
        raise ValueError("files must be a nonempty dict")
    if len(files) > ROOT_ENTRIES:
        raise ValueError("root directory capacity exceeded")

    entries = []
    aliases = set()
    clusters_needed = 0
    for name, payload in files.items():
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            raise ValueError("file names must be canonical lowercase ASCII 8.3")
        if not isinstance(payload, bytes):
            raise TypeError("file payloads must be bytes")
        base, _, extension = name.partition(".")
        alias = (base.upper().ljust(8) + extension.upper().ljust(3)).encode("ascii")
        if alias in aliases:
            raise ValueError("duplicate short-name alias")
        aliases.add(alias)
        count = (len(payload) + CLUSTER_SIZE - 1) // CLUSTER_SIZE
        clusters_needed += count
        entries.append((alias, payload, count))

    if (clusters_needed + 2) * 2 > FAT_SIZE:
        raise ValueError("FAT capacity exceeded")
    if DATA_START + clusters_needed * CLUSTER_SIZE > SEED_SIZE:
        raise ValueError("allocated file data exceeds seed prefix")

    seed = bytearray(SEED_SIZE)
    seed[0:3] = b"\xeb\x3c\x90"
    seed[3:11] = b"BRICKWRT"
    struct.pack_into("<HBHBHHBHHHII", seed, 11,
                     SECTOR_SIZE, CLUSTER_SIZE // SECTOR_SIZE, 1, 1, ROOT_ENTRIES, 63488, 0xF8,
                     63, 32, 64, 256, 0)
    seed[36] = 0x80
    seed[38] = 0x29
    struct.pack_into("<I", seed, 39, 0x42573236)
    seed[43:54] = b"BRICK SEED "
    seed[54:62] = b"FAT16   "
    seed[510:512] = b"\x55\xaa"
    struct.pack_into("<HH", seed, FAT_START, 0xFFF8, 0xFFFF)

    next_cluster = 2
    for index, (alias, payload, count) in enumerate(entries):
        offset = ROOT_START + index * 32
        seed[offset:offset + 11] = alias
        seed[offset + 11] = 0x20  # Regular archive file.
        struct.pack_into("<HI", seed, offset + 26,
                         next_cluster if count else 0, len(payload))
        for cluster in range(next_cluster, next_cluster + count):
            successor = cluster + 1 if cluster < next_cluster + count - 1 else 0xFFFF
            struct.pack_into("<H", seed, FAT_START + cluster * 2, successor)
        data_offset = DATA_START + (next_cluster - 2) * CLUSTER_SIZE
        seed[data_offset:data_offset + len(payload)] = payload
        next_cluster += count
    return bytes(seed)
