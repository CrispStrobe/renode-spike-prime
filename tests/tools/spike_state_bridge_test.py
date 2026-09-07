import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from spike_state_bridge import CommandGate, ProtocolError, SnapshotQueue, canonical_bytes, parse_line


class BridgeTest(unittest.TestCase):
    def fixture(self, name):
        return parse_line((ROOT / "contracts/brick-state/v1" / name).read_bytes())

    def test_snapshot_round_trip_is_canonical(self):
        snapshot = self.fixture("snapshot.ndjson")
        self.assertEqual(canonical_bytes(snapshot), (ROOT / "contracts/brick-state/v1/snapshot.ndjson").read_bytes().rstrip())

    def test_unknown_optional_fields_are_preserved(self):
        snapshot = self.fixture("snapshot.ndjson")
        snapshot["futureOptional"] = {"safe": True}
        self.assertTrue(parse_line(canonical_bytes(snapshot))["futureOptional"]["safe"])

    def test_every_board_qualified_firmware_identity(self):
        snapshot = self.fixture("snapshot.ndjson")
        identities = {
            "spike-prime": ("lego-prime-v2", "lego-prime-v3", "pybricks-prime",
                            "spike-nx", "brickwright-nuttx"),
            "spike-essential": ("lego-essential", "pybricks-essential"),
        }
        for board, firmwares in identities.items():
            for firmware in firmwares:
                candidate = {**snapshot, "target": {**snapshot["target"],
                                                     "board": board, "firmware": firmware}}
                canonical_bytes(candidate)

    def test_version_and_malformed_input_fail_closed(self):
        with self.assertRaises(ProtocolError):
            parse_line('{"schemaVersion":2,"type":"snapshot"}')
        with self.assertRaises(ProtocolError):
            parse_line("not json")
        with self.assertRaises(ProtocolError):
            parse_line(b"{" + b" " * (256 * 1024))
        snapshot = self.fixture("snapshot.ndjson")
        with self.assertRaises(ProtocolError):
            canonical_bytes({**snapshot, "target": {**snapshot["target"], "firmware": "unknown"}})

    def test_replay_and_stale_commands_are_rejected(self):
        command = self.fixture("command.ndjson")
        gate = CommandGate()
        gate.seq = 7
        self.assertTrue(gate.accept(command)["accepted"])
        self.assertFalse(gate.accept(command)["accepted"])
        command = dict(command, requestId="req-2", expectedSeq=4)
        self.assertFalse(gate.accept(command)["accepted"])

    def test_overflow_emits_gap(self):
        queue = SnapshotQueue(2)
        snapshot = self.fixture("snapshot.ndjson")
        for seq in (7, 8, 9):
            queue.publish(dict(snapshot, seq=seq))
        drained = queue.drain()
        self.assertEqual(drained[0]["type"], "gap")
        self.assertEqual(drained[0]["dropped"], 1)
        self.assertEqual([item["seq"] for item in drained[1:]], [8, 9])

    def test_zero_origin_overflow_is_valid(self):
        queue = SnapshotQueue(2)
        snapshot = self.fixture("snapshot.ndjson")
        for seq in (0, 1, 2):
            queue.publish(dict(snapshot, seq=seq))
        gap = queue.drain()[0]
        self.assertEqual(gap, {"schemaVersion": 1, "type": "gap",
                              "firstDroppedSeq": 0, "nextSeq": 1, "dropped": 1})
        parse_line(canonical_bytes(gap))

    def test_multiple_physical_lines_are_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_line(b'{}\n{}\n')

    def test_non_finite_numbers_are_not_serialized(self):
        with self.assertRaises(ProtocolError):
            canonical_bytes({"schemaVersion": 1, "type": "result",
                             "requestId": "x", "accepted": True, "extra": float("nan")})

    def test_service_end_to_end(self):
        process = subprocess.run([sys.executable, str(ROOT / "tools/spike-state-bridge.py"), "--seq", "7"],
                                 input=(ROOT / "contracts/brick-state/v1/command.ndjson").read_bytes(),
                                 stdout=subprocess.PIPE, check=True)
        result = json.loads(process.stdout)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["requestId"], "req-1")


if __name__ == "__main__":
    unittest.main()
