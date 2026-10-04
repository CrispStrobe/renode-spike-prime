# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
from spike_arena_inputs import (apply_arena_inputs, validate_arena_inputs,
    resolve_prime_hub_models, observe_prime_hub, PRIME_HUB_PATHS)
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

class Button:
    Pressed = False
    def Press(self): self.Pressed = True
    def Release(self): self.Pressed = False

class Imu:
    def __init__(self): self.RegisterSnapshot = [0] * 256
    def FeedSample(self, *values):
        for offset, value in zip(range(0x20, 0x2e, 2), values):
            self.RegisterSnapshot[offset] = value & 255
            self.RegisterSnapshot[offset+1] = (value >> 8) & 255

def hub_models():
    return dict({name: Button() for name in ('leftButton', 'centerButton', 'rightButton', 'bluetoothButton')},
                imu=Imu(), speaker=type('Speaker', (), dict(Enabled=True, LastSample=128,
                TotalBytes=15, DroppedBytes=2, DisabledBytes=3, BufferedBytes=13))(),
                display=type('Display', (), {'Matrix': list(range(25))})())

def hub_input():
    return {'buttons': {'left': True, 'center': False, 'right': True, 'bluetooth': False},
            'imuRaw': {'temperature': -32768, 'angularRate': [-1, 0, 32767],
                       'acceleration': [1, -2, 3]}}

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

    def test_hub_combines_real_buttons_and_signed_register_samples(self):
        models = hub_models()
        models['centerButton'].Press()
        self.frame['hub'] = hub_input()
        apply_arena_inputs(self.frame, self.devices.__getitem__, models)
        buttons, imu, audio = observe_prime_hub(models)
        self.assertEqual(buttons, self.frame['hub']['buttons'])
        self.assertEqual(imu, dict(self.frame['hub']['imuRaw'], available=True, semantics='signed-16bit-raw'))
        self.assertTrue(audio['active'])
        self.assertEqual(audio['pcm8'], {'lastSample':128, 'totalBytes':15, 'droppedBytes':2,
                                       'disabledBytes':3, 'bufferedBytes':13})
        self.assertEqual(self.devices['A'].LoadPercent, 100)

    def test_complete_closed_models_required_before_any_mutation(self):
        models = hub_models()
        resolve = lambda path: models[next(role for role, fixed in PRIME_HUB_PATHS.items() if path == fixed)]
        self.assertEqual(resolve_prime_hub_models(PRIME_HUB_PATHS, resolve), models)
        for role in PRIME_HUB_PATHS:
            paths = dict(PRIME_HUB_PATHS); paths[role] = 'machine:other'
            with self.assertRaises(ValueError): resolve_prime_hub_models(paths, resolve)
            missing = dict(models); missing[role] = object()
            with self.assertRaises(ValueError):
                resolve_prime_hub_models(PRIME_HUB_PATHS, lambda path: missing[next(r for r, p in PRIME_HUB_PATHS.items() if p == path)])
        self.frame['hub'] = hub_input()
        for missing in [None, {'leftButton': Button()}] + [dict((r, m) for r, m in models.items() if r != role) for role in PRIME_HUB_PATHS]:
            with self.assertRaises(ValueError): apply_arena_inputs(self.frame, self.devices.__getitem__, missing)
            self.assertEqual(self.devices['C'].ColorId, 255)
            self.assertEqual(self.devices['A'].LoadPercent, 0)

    def test_invalid_hub_frames_preserve_models_and_reject_boolean_integers(self):
        mutations = [lambda h: h.update(path='machine:other'),
                     lambda h: h['buttons'].update(left=1),
                     lambda h: h['buttons'].update(extra=True),
                     lambda h: h['imuRaw'].update(temperature=True),
                     lambda h: h['imuRaw'].update(temperature=32768),
                     lambda h: h['imuRaw'].update(angularRate=[1,2]),
                     lambda h: h['imuRaw'].update(acceleration=[1,2,True]),
                     lambda h: h['imuRaw'].update(acceleration=[1,2,-32769]),
                     lambda h: h['imuRaw'].update(extra=0),
                     lambda h: h.pop('imuRaw')]
        for mutate in mutations:
            frame = copy.deepcopy(self.frame); frame['hub'] = hub_input(); mutate(frame['hub'])
            models = hub_models()
            with self.assertRaises(ValueError): apply_arena_inputs(frame, self.devices.__getitem__, models)
            self.assertEqual(self.devices['C'].ColorId, 255)
            self.assertFalse(models['leftButton'].Pressed)
            self.assertEqual(models['imu'].RegisterSnapshot, [0]*256)

    def test_observation_does_not_consume_audio_or_imu(self):
        models=hub_models(); registers=copy.deepcopy(models['imu'].RegisterSnapshot)
        for enabled, buffered, active in ((True, 0, False), (False, 2, False), (True, 2, True)):
            models['speaker'].Enabled=enabled; models['speaker'].BufferedBytes=buffered
            first=observe_prime_hub(models); second=observe_prime_hub(models)
            self.assertEqual(first, second)
            self.assertEqual(first[2]['active'], active)
            self.assertEqual(models['imu'].RegisterSnapshot, registers)

if __name__ == '__main__': unittest.main()
