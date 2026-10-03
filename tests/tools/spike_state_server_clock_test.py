#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check the actual monitor snapshot clock without a listener or emulator."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]


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
        def observe(config, resolve, seq, clock, generation):
            return {'clockNs': clock, 'seq': seq, 'generation': generation}
        env = {'emulationManager': SimpleNamespace(CurrentEmulation=SimpleNamespace(
                   MasterTimeSource=SimpleNamespace(ElapsedVirtualTime=interval))),
               'ev3_state_observer': SimpleNamespace(observe=observe),
               '_resolve': lambda path: None, '_optional': lambda paths, role: (ports or {}).get(role),
               '_kind': lambda device: getattr(device, 'kind', None)}
        exec(compile(ast.Module(body=[snapshot], type_ignores=[]),
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


if __name__ == '__main__':
    unittest.main()
