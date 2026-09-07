#!/usr/bin/env python3
import unittest
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from spike_state_bridge import LiveStateSession, ProtocolError, RenodeModelObserver


class Device:
    SpeedPercent = 25
    PositionDegrees = 90


class Port:
    def __init__(self):
        self.Device = Device()
        self.TopologyGeneration = 3
        self.calls = []
    def Attach(self, value): self.calls.append(("attach", value))
    def Detach(self): self.calls.append(("detach",))
    def AdvanceEmulatedTime(self, value): self.calls.append(("advance", value))


class Power:
    BatteryMillivolts = 7200
    PowerHold = True
    ChargerConnected = False
    def SetBatteryMillivolts(self, value): self.BatteryMillivolts = value
    def SetChargerConnected(self, value): self.ChargerConnected = value


def command(request_id, name, arguments=None, expected=0):
    return {"schemaVersion": 1, "type": "command", "requestId": request_id,
            "expectedSeq": expected, "command": name, "arguments": arguments or {}}


class LiveStateTests(unittest.TestCase):
    def setUp(self):
        self.port = Port()
        self.machine = {"power": Power(), "portA": self.port}
        identity = {"board": "spike-prime", "firmware": "brickwright-nuttx",
                    "transport": "none", "imageSha256": None}
        self.observer = RenodeModelObserver(self.machine, identity,
            {"power": "power", "portA": "portA"})
        self.session = LiveStateSession(self.observer, queue_capacity=2)

    def test_observes_real_public_model_properties(self):
        self.session.connect()
        snapshot = self.session.sample(100)
        self.assertEqual(snapshot["battery"]["millivolts"], 7200)
        self.assertEqual(snapshot["motors"][0], {"port": "A", "speed": 25.0, "position": 90.0})
        self.assertEqual(snapshot["lifecycle"]["generation"], 3)

    def test_backpressure_and_clock(self):
        self.session.connect()
        for clock in (10, 20, 30): self.session.sample(clock)
        self.assertEqual(self.session.queue.drain()[0]["type"], "gap")
        with self.assertRaisesRegex(ProtocolError, "backwards"): self.session.sample(29)

    def test_commands_dispatch_and_fail_closed(self):
        self.session.connect(); self.session.sample(1)
        self.assertTrue(self.session.command(command("a", "lpf2.detach", {"port": "A"}))["accepted"])
        self.assertEqual(self.port.calls, [("detach",)])
        self.assertFalse(self.session.command(command("a", "lpf2.detach", {"port": "A"}))["accepted"])
        unknown = self.session.command(command("b", "host.shell"))
        self.assertFalse(unknown["accepted"])
        self.assertEqual(unknown["error"], "unknown command")

    def test_disconnect_reconnect_preserves_sequence(self):
        self.session.connect(); self.assertEqual(self.session.sample(1)["seq"], 0)
        self.session.disconnect()
        with self.assertRaisesRegex(ProtocolError, "disconnected"): self.session.sample(2)
        self.session.connect(); self.assertEqual(self.session.sample(3)["seq"], 1)


if __name__ == "__main__": unittest.main()
