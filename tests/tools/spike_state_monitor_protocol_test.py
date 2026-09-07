#!/usr/bin/env python3
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from spike_state_monitor_protocol import split_frames, validate_command, validate_config


def config(board="spike-prime", firmware="brickwright-nuttx"):
    return {"identity": {"board": board, "firmware": firmware, "transport": "none",
                         "imageSha256": None}, "paths": {}}


def command(**changes):
    value = {"schemaVersion": 1, "type": "command", "requestId": "r",
             "command": "imu.advance-sample", "arguments": {}, "expectedSeq": 0}
    value.update(changes)
    return value


class MonitorProtocolTest(unittest.TestCase):
    def test_two_individually_legal_records_share_one_read(self):
        lines, pending = split_frames("", "a" * 8 + "\n" + "b" * 8 + "\n", 8, 32)
        self.assertEqual(lines, ["a" * 8, "b" * 8])
        self.assertEqual(pending, "")

    def test_line_read_and_record_bounds_are_independent(self):
        with self.assertRaises(ValueError): split_frames("", "x" * 9, 8, 32)
        with self.assertRaises(ValueError): split_frames("", "x" * 33, 64, 32)
        with self.assertRaises(ValueError): split_frames("", "x\n" * 257, 8, 1024)

    def test_exact_identity_vocabulary_and_hash_shape(self):
        pairs = {"spike-prime": ("lego-prime-v2", "lego-prime-v3", "pybricks-prime",
                 "spike-nx", "brickwright-nuttx"),
                 "spike-essential": ("lego-essential", "pybricks-essential")}
        for board, firmwares in pairs.items():
            for firmware in firmwares: validate_config(config(board, firmware))
        with self.assertRaises(ValueError): validate_config(config("spike-essential", "spike-nx"))
        bad = config(); bad["identity"]["imageSha256"] = "A" * 64
        with self.assertRaises(ValueError): validate_config(bad)
        bad = config(); del bad["identity"]["transport"]
        with self.assertRaises(ValueError): validate_config(bad)

    def test_command_envelope_bounds(self):
        validate_command(command())
        invalid = ({"requestId": ""}, {"requestId": "x" * 129}, {"command": ""},
                   {"command": "x" * 65}, {"arguments": []}, {"expectedSeq": -1},
                   {"expectedSeq": True})
        for changes in invalid:
            with self.assertRaises(ValueError): validate_command(command(**changes))


if __name__ == "__main__": unittest.main()
