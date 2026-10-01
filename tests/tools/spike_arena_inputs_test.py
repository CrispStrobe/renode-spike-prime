# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
from spike_arena_inputs import apply_arena_inputs, validate_arena_inputs
from spike_state_bridge import RenodeModelObserver

class Color:
    ColorId = 255
    ReflectionPercent = 0
    AmbientPercent = 0
    def SetReading(self, color, reflection, ambient):
        self.ColorId, self.ReflectionPercent, self.AmbientPercent = color, reflection, ambient
class Distance:
    DistanceMillimeters = 1000
    def SetDistance(self, value): self.DistanceMillimeters = value
class Force:
    ForcePercent = 0
    Pressed = False
    def SetReading(self, value, pressed): self.ForcePercent, self.Pressed = value, pressed
class Motor:
    LoadPercent = 0
    def SetLoad(self, percent): self.LoadPercent = percent

class ArenaInputsTests(unittest.TestCase):
    def setUp(self):
        self.devices = {'A': Motor(), 'C': Color(), 'D': Distance(), 'E': Force()}
        self.frame = {'sensors': [
            {'port': 'C', 'kind': 'color', 'values': {'colorId': 3, 'reflectionPercent': 80, 'ambientPercent': 10}},
            {'port': 'D', 'kind': 'distance', 'values': {'distanceMillimeters': -1}},
            {'port': 'E', 'kind': 'force', 'values': {'forcePercent': 60, 'pressed': True}}],
            'loads': [{'port': 'A', 'percent': 100}]}
    def test_complete_frame_reaches_only_public_model_setters(self):
        apply_arena_inputs(self.frame, self.devices.__getitem__)
        self.assertEqual((self.devices['C'].ColorId, self.devices['C'].ReflectionPercent), (3, 80))
        self.assertEqual(self.devices['D'].DistanceMillimeters, 65535)
        self.assertEqual(self.devices['E'].ForcePercent, 60)
        self.assertTrue(self.devices['E'].Pressed)
        self.assertEqual(self.devices['A'].LoadPercent, 100)
    def test_invalid_late_value_preserves_the_entire_previous_frame(self):
        self.frame['loads'][0]['percent'] = 101
        with self.assertRaises(ValueError): apply_arena_inputs(self.frame, self.devices.__getitem__)
        self.assertEqual(self.devices['C'].ColorId, 255)
        self.assertEqual(self.devices['D'].DistanceMillimeters, 1000)
    def test_missing_late_model_preserves_earlier_models(self):
        self.devices['E'] = object()
        with self.assertRaises(ValueError): apply_arena_inputs(self.frame, self.devices.__getitem__)
        self.assertEqual(self.devices['C'].ColorId, 255)
    def test_unknown_fields_duplicates_boolean_numbers_and_boundaries(self):
        for mutate in [lambda f: f.update({'monitor': 'anything'}),
                       lambda f: f['loads'].append({'port': 'C', 'percent': 0}),
                       lambda f: f['loads'][0].update({'percent': True}),
                       lambda f: f['sensors'][1]['values'].update({'distanceMillimeters': -2}),
                       lambda f: f['sensors'][0]['values'].update({'reflectionPercent': 101}),
                       lambda f: f['sensors'][0].update({'port': 'Z'})]:
            frame = copy.deepcopy(self.frame); mutate(frame)
            with self.assertRaises(ValueError): validate_arena_inputs(frame)
    def test_sample_is_read_only_and_has_no_arguments(self):
        observer = RenodeModelObserver({}, {'firmware': 'brickwright-nuttx', 'transport': 'none'}, {})
        observer.dispatch('state.sample', {})
        with self.assertRaises(ValueError): observer.dispatch('state.sample', {'clock': 1})

    def test_observer_refuses_input_for_other_firmware_even_when_models_exist(self):
        observer = RenodeModelObserver({}, {'firmware': 'lego-prime-v3', 'transport': 'none'}, {})
        with self.assertRaises(ValueError): observer.dispatch('arena.inputs', self.frame)

if __name__ == '__main__': unittest.main()
