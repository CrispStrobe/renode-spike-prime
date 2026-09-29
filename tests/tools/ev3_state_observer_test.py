#!/usr/bin/env python3
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from ev3_state_observer import observe, dispatch
from spike_state_bridge import canonical_bytes, parse_line
from spike_state_monitor_protocol import validate_config


class Button:
    Pressed = False
    def Press(self): self.Pressed = True
    def Release(self): self.Pressed = False


class Panel:
    DisplayEnabled = True
    def GetFrameSnapshot(self): return [0, 255] + [255] * (178 * 128 - 2)


class ADC:
    def __init__(self): self.values = [0] * 16
    def GetChannelValue(self, channel): return self.values[channel]
    def SetChannelValue(self, channel, value): self.values[channel] = value


class Motor:
    State = "Forward"
    Direction = 1
    DutyCycle = 0.25
    TachometerCount = 4
    EmittedEdges = 4


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.config = validate_config(json.loads((ROOT / "contracts/brick-state/renode-ev3.example.json").read_text()))
        self.models = {self.config["paths"]["display"]: Panel(),
                       self.config["paths"]["adc"]: ADC(),
                       self.config["paths"]["centerButton"]: Button()}
        self.config["paths"]["motorA"] = "machine:motorA"
        self.models["machine:motorA"] = Motor()

    def test_full_frame_actual_motor_and_unavailable_fields(self):
        state = observe(self.config, self.models.__getitem__, 7, 100, 2)
        self.assertEqual(state["display"]["pixels"][:2], [0, 255])
        self.assertEqual(len(state["display"]["pixels"]), 178 * 128)
        self.assertEqual(state["motors"][0]["dutyCycle"], 0.25)
        self.assertIsNone(state["buttons"]["left"])
        self.assertFalse(state["ports"][3]["attached"])
        self.assertTrue(any("motorD" in item for item in state["target"]["limitations"]))
        wire = canonical_bytes(state)
        self.assertLess(len(wire), 262144)
        self.assertEqual(parse_line(wire)["seq"], 7)

    def test_normative_schema_matches_live_shape(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional for source-only tests")
        schema = json.loads((ROOT / "contracts/brick-state/v1/schema.json").read_text())
        state = observe(self.config, self.models.__getitem__, 0, 0, 1)
        jsonschema.validate(state, schema)
        state["display"]["pixels"][0] = 256
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(state, schema)

    def test_named_inputs_change_model_and_snapshot(self):
        dispatch(self.config, self.models.__getitem__, {"command": "ev3.button.set", "arguments": {"button": "center", "pressed": True}})
        dispatch(self.config, self.models.__getitem__, {"command": "ev3.analog.set-channel", "arguments": {"channel": 3, "value": 1023}})
        state = observe(self.config, self.models.__getitem__, 0, 0, 1)
        self.assertTrue(state["buttons"]["center"])
        self.assertEqual(state["sensors"][0]["values"]["channels"][3], 1023)

    def test_invalid_inputs_fail_without_side_effect(self):
        for args in ({"channel": True, "value": 3}, {"channel": 16, "value": 3},
                     {"channel": 0, "value": 1024}, {"channel": 0, "value": 3, "code": "eval"}):
            with self.assertRaises(ValueError):
                dispatch(self.config, self.models.__getitem__, {"command": "ev3.analog.set-channel", "arguments": args})
        with self.assertRaises(ValueError):
            dispatch(self.config, self.models.__getitem__, {"command": "host.shell", "arguments": {}})
        self.assertEqual(self.models[self.config["paths"]["adc"]].values, [0] * 16)

    def test_malformed_model_frame_is_not_published(self):
        self.models[self.config["paths"]["display"]].GetFrameSnapshot = lambda: [0]
        with self.assertRaisesRegex(ValueError, "framebuffer"):
            observe(self.config, self.models.__getitem__, 0, 0, 1)


if __name__ == "__main__": unittest.main()
