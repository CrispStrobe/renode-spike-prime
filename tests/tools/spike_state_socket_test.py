#!/usr/bin/env python3
import json
import ast
import pathlib
import socket
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from spike_state_socket import BoundedStateServer, validate_endpoint


class Power:
    BatteryMillivolts = 7200
    PowerHold = True
    ChargerConnected = False
    def SetBatteryMillivolts(self, value): self.BatteryMillivolts = value


class Machine:
    def __init__(self): self.models = {"power": Power()}
    def __getitem__(self, path): return self.models[path]


class DeterministicClock:
    def __init__(self): self.value = 100
    def __call__(self):
        value = self.value
        self.value += 100
        return value


def receive_line(stream):
    return json.loads(stream.readline())


class SocketTest(unittest.TestCase):
    def setUp(self):
        identity = {"board": "spike-prime", "firmware": "brickwright-nuttx",
                    "transport": "none", "imageSha256": None}
        self.machine = Machine()
        self.executions = []
        def execute(callback):
            self.executions.append("synchronized")
            return callback()
        self.server = BoundedStateServer(self.machine, identity, {"power": "power"},
                                         DeterministicClock(), max_clients=2, socket_timeout=1,
                                         execute=execute)
        self.endpoint = self.server.start()

    def tearDown(self): self.server.close()

    def connect(self):
        client = socket.create_connection(self.endpoint, timeout=1)
        return client, client.makefile("rb")

    def test_fragmented_command_result_snapshot_and_reconnect(self):
        client, stream = self.connect()
        first = receive_line(stream)
        self.assertEqual((first["seq"], first["clockNs"]), (0, 100))
        command = {"schemaVersion": 1, "type": "command", "requestId": "r1",
                   "expectedSeq": 0, "command": "power.set-battery-millivolts",
                   "arguments": {"value": 7000}}
        wire = (json.dumps(command, separators=(",", ":")) + "\n").encode()
        client.sendall(wire[:7]); client.sendall(wire[7:])
        self.assertTrue(receive_line(stream)["accepted"])
        updated = receive_line(stream)
        self.assertEqual((updated["seq"], updated["clockNs"], updated["battery"]["millivolts"]),
                         (1, 200, 7000))
        self.assertGreaterEqual(len(self.executions), 3)
        stream.close(); client.close()
        client, stream = self.connect()
        self.assertEqual(receive_line(stream)["clockNs"], 300)
        stream.close(); client.close()

    def test_oversized_partial_line_disconnects_without_dispatch(self):
        self.server.close()
        identity = {"board": "spike-prime", "firmware": "brickwright-nuttx",
                    "transport": "none", "imageSha256": None}
        self.server = BoundedStateServer(self.machine, identity, {"power": "power"},
                                         DeterministicClock(), line_limit=256, socket_timeout=1,
                                         execute=lambda callback: callback())
        self.endpoint = self.server.start()
        client, stream = self.connect(); receive_line(stream)
        client.sendall(b"x" * 257)
        self.assertEqual(stream.readline(), b"")
        self.assertEqual(self.machine.models["power"].BatteryMillivolts, 7200)
        client.close()

    def test_multiple_legal_lines_in_one_read_are_not_an_oversized_line(self):
        client, stream = self.connect(); receive_line(stream)
        commands = []
        for request in ("one", "two"):
            commands.append(json.dumps({"schemaVersion": 1, "type": "command",
                "requestId": request, "expectedSeq": 0 if request == "one" else 1,
                "command": "power.set-battery-millivolts", "arguments": {"value": 7000}}))
        client.sendall(("\n".join(commands) + "\n").encode())
        self.assertTrue(receive_line(stream)["accepted"]); receive_line(stream)
        self.assertTrue(receive_line(stream)["accepted"]); receive_line(stream)
        stream.close(); client.close()

    def test_endpoint_and_limits_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "loopback"): validate_endpoint("0.0.0.0", 1)
        with self.assertRaises(ValueError): validate_endpoint("localhost", 1)
        with self.assertRaises(ValueError): validate_endpoint("127.0.0.1", 70000)
        identity = {"board": "spike-prime", "firmware": "brickwright-nuttx"}
        with self.assertRaisesRegex(TypeError, "execute"):
            BoundedStateServer(self.machine, identity, {}, DeterministicClock())

    def test_monitor_launcher_is_direct_and_opt_in(self):
        source = (ROOT / "scripts/spike-state-server.py").read_text()
        ast.parse(source)
        self.assertIn('monitor.Machine[', source)
        self.assertIn('MasterTimeSource.ElapsedVirtualTime.Ticks', source)
        self.assertIn('finally:\n                self.stream = None', source)
        self.assertIn('split_frames(pending, chunk', source)
        self.assertNotIn('_Server(str(host)', source.split('def mc_spike_state_start')[0])
        self.assertIn('SocketOptionName.ReuseAddress', source)
        self.assertIn('def mc_spike_state_port():', source)


if __name__ == "__main__": unittest.main()
