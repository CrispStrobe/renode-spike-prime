# Copyright (c) 2026 Brickwright contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Independent BPB, directory, and cluster-chain checks of synthetic seeds."""

import importlib.util
from pathlib import Path
import struct
import unittest


_PATH = Path(__file__).resolve().parents[2] / "tools" / "spike_micropython_filesystem.py"
_SPEC = importlib.util.spec_from_file_location("spike_seed", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build_seed = _MODULE.build_seed


def parse_seed(seed):
    """Locate everything from the on-disk BPB, independently of builder constants."""
    bps, spc, reserved, fats, root_entries, total, media, fat_sectors = struct.unpack_from(
        "<HBHBHHBH", seed, 11)
    fat_start = reserved * bps
    root_start = (reserved + fats * fat_sectors) * bps
    root_sectors = (root_entries * 32 + bps - 1) // bps
    data_start = root_start + root_sectors * bps
    cluster_size = bps * spc
    result = {}
    allocated = set()
    for offset in range(root_start, root_start + root_entries * 32, 32):
        entry = seed[offset:offset + 32]
        if entry[0] == 0:
            break
        base = entry[:8].decode("ascii").rstrip().lower()
        extension = entry[8:11].decode("ascii").rstrip().lower()
        name = base + ("." + extension if extension else "")
        assert name not in result
        assert entry[11] == 0x20
        cluster, size = struct.unpack_from("<HI", entry, 26)
        data = bytearray()
        chain = []
        while cluster:
            assert 2 <= cluster < 0xFFF0
            assert cluster not in allocated
            allocated.add(cluster)
            chain.append(cluster)
            start = data_start + (cluster - 2) * cluster_size
            assert start + cluster_size <= len(seed)
            data.extend(seed[start:start + cluster_size])
            successor = struct.unpack_from("<H", seed, fat_start + cluster * 2)[0]
            if successor >= 0xFFF8:
                break
            assert successor >= 2
            cluster = successor
        assert len(chain) == (size + cluster_size - 1) // cluster_size
        assert not any(data[size:])
        result[name] = bytes(data[:size])
    return result, (bps, spc, reserved, fats, root_entries, total, media, fat_sectors), allocated


class SeedTests(unittest.TestCase):
    def test_bpb_and_round_trip(self):
        files = {"boot.py": b"print('hello')\n", "trial.py": bytes(range(256)) * 19,
                 "empty.py": b""}
        seed = build_seed(files)
        self.assertIsInstance(seed, bytes)
        self.assertEqual(len(seed), 65536)
        parsed, bpb, allocated = parse_seed(seed)
        self.assertEqual(parsed, files)
        self.assertEqual(bpb, (512, 4, 1, 1, 128, 63488, 0xF8, 63))
        self.assertEqual(allocated, {2, 3, 4, 5})
        self.assertEqual(struct.unpack_from("<I", seed, 28)[0], 256)
        self.assertEqual(struct.unpack_from("<I", seed, 32)[0], 0)
        self.assertEqual(seed[510:512], b"\x55\xaa")
        self.assertEqual(seed[512:516], b"\xf8\xff\xff\xff")
        self.assertEqual(seed[54:62], b"FAT16   ")
        self.assertEqual(seed[38], 0x29)
        self.assertEqual(seed[524:32768], bytes(32768 - 524))
        self.assertEqual(seed[32768 + 96:36864], bytes(36864 - 32768 - 96))

    def test_exact_prefix_capacity(self):
        files = {"trial.py": b"x" * 28672}
        self.assertEqual(parse_seed(build_seed(files))[0], files)
        for files in ({"trial.py": b"x" * 28673},
                      {"boot.py": b"a", "trial.py": b"b" * 28672}):
            with self.assertRaises(ValueError):
                build_seed(files)

    def test_empty_files_and_root_capacity(self):
        files = {f"f{i}.py": b"" for i in range(128)}
        seed = build_seed(files)
        self.assertEqual(parse_seed(seed)[0], files)
        self.assertEqual(seed[516:32768], bytes(32768 - 516))
        self.assertEqual(seed[36864:], bytes(28672))
        files["extra.py"] = b""
        with self.assertRaises(ValueError):
            build_seed(files)

    def test_bad_names_and_aliases(self):
        for name in ("BOOT.PY", "Boot.py", "abcdefghij.py", "boot.python", "boot.",
                     ".py", "a.b.py", "a/b.py", "a\\b.py", "a b.py", "é.py", "", 1):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_seed({name: b""})
        with self.assertRaises(ValueError):
            build_seed({"boot.py": b"a", "BOOT.PY": b"b"})

    def test_bad_payloads_and_container(self):
        for payload in ("text", bytearray(b"x"), memoryview(b"x"), None, 3):
            with self.subTest(payload=payload), self.assertRaises(TypeError):
                build_seed({"boot.py": payload})
        for files in ({}, [], None, [("boot.py", b"")]):
            with self.subTest(files=files), self.assertRaises(ValueError):
                build_seed(files)


if __name__ == "__main__":
    unittest.main()
