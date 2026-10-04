#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check the actual monitor snapshot clock without a listener or emulator."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from spike_arena_inputs import PRIME_HUB_PATHS, resolve_prime_hub_models, observe_prime_hub, apply_arena_inputs
from spike_arena_inputs_test import hub_models, hub_input, Motor


class TimeInterval:
    """Renode SDK TimeInterval ticks are nanoseconds, unlike .NET TimeSpan."""
    def __init__(self, nanoseconds):
        self.Ticks = nanoseconds
        self.TotalNanoseconds = nanoseconds


class SnapshotClockTests(unittest.TestCase):
    def snapshot_function(self, interval, ports=None):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        snapshot = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == '_snapshot')
        hub = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == '_prime_hub_models')
        def observe(config, resolve, seq, clock, generation):
            return {'clockNs': clock, 'seq': seq, 'generation': generation}
        env = {'integer_types': (int,), 'emulationManager': SimpleNamespace(CurrentEmulation=SimpleNamespace(
                   MasterTimeSource=SimpleNamespace(ElapsedVirtualTime=interval))),
               'ev3_state_observer': SimpleNamespace(observe=observe),
               'resolve_prime_hub_models': resolve_prime_hub_models, 'observe_prime_hub': observe_prime_hub,
               '_resolve': lambda path: next(((ports or {}).get(role) for role, fixed in PRIME_HUB_PATHS.items() if path == fixed), None),
               '_optional': lambda paths, role: (ports or {}).get(role),
               '_kind': lambda device: getattr(device, 'kind', None)}
        exec(compile(ast.Module(body=[hub, snapshot], type_ignores=[]),
                     'actual-monitor-snapshot', 'exec'), env)
        return env['_snapshot']

    def test_one_sdk_second_is_one_billion_nanoseconds_for_prime_and_ev3(self):
        snapshot = self.snapshot_function(TimeInterval(1_000_000_000))
        for board in ('spike-prime', 'spike-essential', 'ev3'):
            with self.subTest(board=board):
                result = snapshot({'identity': {'board': board, 'firmware': 'test',
                                  'transport': 'none'}, 'paths': {}}, 7, 3)
                self.assertEqual(result['clockNs'], 1_000_000_000)
                self.assertEqual(result['seq'], 7)

    def test_micro_arena_requires_uart_and_both_observed_drive_motors(self):
        device = SimpleNamespace(kind='motor', SpeedPercent=10, PositionDegrees=90,
            AngularVelocityDegreesPerSecond=110, Stalled=False, Power=10)
        port = SimpleNamespace(Device=device, TopologyGeneration=1)
        uart = SimpleNamespace(status=lambda: {'state': 'ready', 'generation': 7})
        config = {'identity': {'board': 'spike-prime', 'firmware': 'micropython-prime',
                              'transport': 'none'}, 'paths': {}}
        for ports, transport in [({}, uart), ({'portA': port}, uart),
                ({'portA': port, 'portB': port}, None),
                ({'portA': port, 'portB': port}, uart)]:
            result = self.snapshot_function(TimeInterval(123456789), ports)(config, 1, 3, program_uart=transport)
            qualified = len(ports) == 2 and transport is not None
            self.assertEqual('arena-clock/v1' in result['target']['capabilities'], qualified)
            self.assertEqual('guest-motor-output/v1' in result['target']['capabilities'], qualified)
            self.assertEqual(result['clockNs'], 123456789)
            if qualified:
                self.assertEqual(result['motors'][0]['position'], 90)
                self.assertEqual(result['motors'][1]['speedDps'], 110)
                self.assertEqual(result['lifecycle']['micropythonUart']['generation'], 7)

    def test_micro_six_requires_all_observed_motors_and_owned_ready_uart(self):
        device = SimpleNamespace(kind='motor', SpeedPercent=0, PositionDegrees=0,
            AngularVelocityDegreesPerSecond=0, Stalled=False, Power=0)
        ports = {'port'+p: SimpleNamespace(Device=device, TopologyGeneration=1) for p in 'ABCDEF'}
        config = {'identity': {'board': 'spike-prime', 'firmware': 'micropython-prime',
                  'transport': 'none'}, 'paths': {}, 'motorPorts': 6, 'programUartGeneration': 7}
        for defect in (None, 'missing', 'sensor', 'unready', 'wrong_generation', 'bool_generation', 'no_declaration'):
            models=dict(ports); cfg=dict(config); status={'state':'ready','generation':7}
            if defect=='missing':del models['portF']
            if defect=='sensor':models['portF']=SimpleNamespace(Device=None,TopologyGeneration=1)
            if defect=='unready':status['state']='closed'
            if defect=='wrong_generation':status['generation']=8
            if defect=='bool_generation':status['generation']=True
            if defect=='no_declaration':del cfg['motorPorts']
            uart=SimpleNamespace(status=lambda:status)
            result=self.snapshot_function(TimeInterval(1),models)(cfg,1,1,program_uart=uart)
            self.assertEqual('micropython-six-motors/v1' in result['target']['capabilities'],defect is None)

    def test_snapshots_use_explicit_nanoseconds_property(self):
        class ExplicitInterval:
            TotalNanoseconds = 1_234_567_890
            @property
            def Ticks(self):
                raise AssertionError('snapshot must use the explicit SDK unit')
        snapshot = self.snapshot_function(ExplicitInterval())
        for board in ('spike-prime', 'ev3'):
            with self.subTest(board=board):
                result = snapshot({'identity': {'board': board, 'firmware': 'test',
                                  'transport': 'none'}, 'paths': {}}, 1, 1)
                self.assertEqual(result['clockNs'], 1_234_567_890)

    def test_hub_capability_requires_complete_closed_profile_and_ready_uart(self):
        for defect in (None, 'missing_button', 'missing_imu', 'missing_speaker', 'missing_display',
                       'redirected_path', 'other_firmware', 'other_board', 'transport',
                       'unready_uart', 'missing_uart', 'wrong_generation', 'bool_generation'):
            with self.subTest(defect=defect):
                models=hub_models()
                config={'identity': {'board':'spike-prime', 'firmware':'micropython-prime', 'transport':'none'},
                        'paths':dict(PRIME_HUB_PATHS), 'programUartGeneration':7}
                status={'state':'ready', 'generation':7}
                if defect == 'missing_button': del models['bluetoothButton']
                if defect == 'missing_imu': del models['imu']
                if defect == 'missing_speaker': del models['speaker']
                if defect == 'missing_display': del models['display']
                if defect == 'redirected_path': config['paths']['imu']='machine:other'
                if defect == 'other_firmware': config['identity']['firmware']='brickwright-nuttx'
                if defect == 'other_board': config['identity']['board']='spike-essential'
                if defect == 'transport': config['identity']['transport']='usb'
                if defect == 'unready_uart': status['state']='closed'
                if defect == 'wrong_generation': status['generation']=8
                if defect == 'bool_generation': status['generation']=True
                uart=None if defect == 'missing_uart' else SimpleNamespace(status=lambda:status)
                result=self.snapshot_function(TimeInterval(1),models)(config,1,1,program_uart=uart)
                self.assertEqual('prime-hub-io/v1' in result['target']['capabilities'], defect is None)
                if defect is None:
                    self.assertEqual(result['buttons'], hub_input()['buttons'] | {'left':False,'right':False})
                    self.assertEqual(result['imu']['semantics'], 'signed-16bit-raw')
                    self.assertEqual(result['display'], {'width':5,'height':5,
                        'pixels':list(range(25)), 'semantics':'grayscale-16bit'})
                    self.assertEqual(result['audio']['pcm8']['totalBytes'],15)
                else:
                    self.assertEqual(result['buttons'], {})
                    self.assertEqual(result['audio'], {'active':False,'bufferedBytes':0})

    def test_actual_dispatch_gates_hub_and_preflights_before_lpf2_mutation(self):
        tree=ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        dispatch=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_dispatch')
        for defect in (None, 'wrong_profile', 'wrong_path', 'missing_model', 'invalid_input'):
            with self.subTest(defect=defect):
                models=hub_models(); motor=Motor()
                config={'identity':{'board':'spike-prime','firmware':'micropython-prime','transport':'none'},
                        'paths':dict(PRIME_HUB_PATHS, portA='external:portA'), 'programUartGeneration':7}
                args={'sensors':[], 'loads':[{'port':'A','percent':60}], 'hub':hub_input()}
                if defect=='wrong_profile':config['identity']['firmware']='brickwright-nuttx'
                if defect=='wrong_path':config['paths']['imu']='machine:other'
                if defect=='missing_model':del models['imu']
                if defect=='invalid_input':args['hub']['imuRaw']['temperature']=True
                env=self.snapshot_function(TimeInterval(1), models).__globals__
                resolve=env['_resolve']
                env['_resolve']=lambda path: SimpleNamespace(Device=motor) if path=='external:portA' else resolve(path)
                env['apply_arena_inputs']=apply_arena_inputs
                exec(compile(ast.Module(body=[dispatch],type_ignores=[]),'actual-monitor-dispatch','exec'),env)
                call=lambda:env['_dispatch'](config,{'command':'arena.inputs','arguments':args},
                    program_uart=SimpleNamespace(status=lambda:{'state':'ready','generation':7}))
                if defect is None:
                    call(); self.assertEqual(motor.LoadPercent,60)
                    self.assertTrue(models['leftButton'].Pressed)
                else:
                    with self.assertRaises(ValueError):call()
                    self.assertEqual(motor.LoadPercent,0)
                    self.assertFalse(models['leftButton'].Pressed)


if __name__ == '__main__':
    unittest.main()
