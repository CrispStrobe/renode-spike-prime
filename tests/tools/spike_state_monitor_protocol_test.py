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
        pairs = {"spike-prime": ("lego-prime-v2", "lego-prime-v3",
                 "spike-nx", "brickwright-nuttx", "brickwright-arena-demo"),
                 "spike-essential": ("lego-essential",)}
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

    def test_six_motor_declaration_requires_own_verified_image(self):
        value = config()
        value['identity']['imageSha256'] = 'a' * 64
        value.update(programMailbox=0x20021000, motorPorts=6)
        validate_config(value)
        for count in (True, 0, 2, 5, 6.0, 7, '6', None):
            with self.assertRaises(ValueError): validate_config(dict(value, motorPorts=count))
        for mutation in ('no_hash', 'no_mailbox', 'other_firmware'):
            bad = dict(value, identity=dict(value['identity']))
            if mutation == 'no_hash': bad['identity']['imageSha256'] = None
            if mutation == 'no_mailbox': del bad['programMailbox']
            if mutation == 'other_firmware': bad['identity']['firmware'] = 'brickwright-arena-demo'
            with self.assertRaises(ValueError): validate_config(bad)

    def test_storage_marker_requires_full_firmware_and_flash_bounds(self):
        value = config()
        value.update(programMailbox=0x20021000, programStorageAbiAddress=0x08061234)
        validate_config(value)
        for address in (True, 0x20021000, 0x08061235, 0x08100000):
            bad = dict(value, programStorageAbiAddress=address)
            with self.assertRaises(ValueError): validate_config(bad)
        del value['programMailbox']
        with self.assertRaises(ValueError): validate_config(value)


if __name__ == "__main__": unittest.main()
