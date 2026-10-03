#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import ast
import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from spike_program_uart import ProgramUartBinding, COMMANDS, validate_request
from spike_state_monitor_protocol import validate_config, validate_command, split_frames


def config():
    return {'identity': {'board': 'spike-prime', 'firmware': 'micropython-prime',
                        'transport': 'none', 'imageSha256': 'a' * 64},
            'paths': {'programUart': 'external:programUart'}, 'programUartGeneration': 7}


class Terminal:
    Generation = 7
    IsFaulted = False
    IsAttached = True
    IsDisposed = False
    def __init__(self):
        self.writes, self.output = [], [0, 255, 4]
    def GetType(self):
        return SimpleNamespace(FullName='Antmicro.Renode.Tools.BrickwrightProgramUart')
    def QueueWrite(self, generation, data):
        self.writes.append(list(data))
    def Read(self, generation, maximum):
        data, self.output = self.output[:maximum], self.output[maximum:]
        return data
    def Dispose(self):
        self.IsDisposed = True


class ProgramUartTests(unittest.TestCase):
    def test_legacy_profile_validation_does_not_require_micro_helper(self):
        # Run the real validator from an isolated old-package layout containing
        # no MicroPython helper, rather than testing a mirrored validator.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'spike_state_monitor_protocol.py').write_bytes(
                (ROOT / 'tools/spike_state_monitor_protocol.py').read_bytes())
            program = ("from spike_state_monitor_protocol import validate_config; "
                       "validate_config({'identity':{'board':'spike-prime',"
                       "'firmware':'brickwright-arena-demo','transport':'none',"
                       "'imageSha256':None},'paths':{}})")
            result = subprocess.run([sys.executable, '-c', program], cwd=path,
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def binding(self):
        self.model = Terminal()
        self.route = {'external:programUart': self.model}
        return ProgramUartBinding(config(), self.route.__getitem__, list)

    def test_binding_requires_verified_micro_profile_and_closed_external_route(self):
        validate_config(config())
        for field, values in [('programUartGeneration', [0, True, 7.0, '7', 9007199254740992])]:
            for value in values:
                bad = config(); bad[field] = value
                with self.assertRaises(ValueError): validate_config(bad)
        for path in ['machine:sysbus.usart2', 'external:x.y', 'external:x\n', 'external:', None]:
            bad = config(); bad['paths']['programUart'] = path
            with self.assertRaises(ValueError): validate_config(bad)
        for field, value in [('board', 'ev3'), ('firmware', 'brickwright-nuttx'),
                             ('transport', 'usb'), ('imageSha256', None)]:
            bad = config(); bad['identity'][field] = value
            with self.assertRaises(ValueError): validate_config(bad)
        bad = config(); del bad['paths']['programUart']
        with self.assertRaises(ValueError): validate_config(bad)

    def test_strict_request_bounds_before_model_mutation(self):
        binding = self.binding()
        for data in [[], [0] * 33, [True], [-1], [256], [1.0], 'bytes']:
            with self.assertRaises(ValueError): binding.dispatch(COMMANDS[0], {'generation': 7, 'bytes': data})
        for maximum in [0, 4097, True, 1.0, '1']:
            with self.assertRaises(ValueError): binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': maximum})
        for name, args in [(COMMANDS[0], {'generation': 7, 'bytes': [0]}),
                           (COMMANDS[1], {'generation': 7, 'maxBytes': 1}),
                           (COMMANDS[2], {'generation': 7})]:
            for key in ['path', 'port', 'endpoint', 'code', 'monitor']:
                with self.assertRaises(ValueError): binding.dispatch(name, dict(args, **{key: 'synthetic'}))
            for generation in [0, 8, True, 7.0, '7']:
                with self.assertRaises(ValueError): binding.dispatch(name, dict(args, generation=generation))
        self.assertEqual(self.model.writes, [])
        self.assertFalse(self.model.IsDisposed)

    def test_correlated_fifo_data_close_and_existing_connection_state(self):
        binding = self.binding()
        self.assertEqual(binding.dispatch(COMMANDS[0], {'generation': 7, 'bytes': [0, 255]}),
                         {'generation': 7, 'count': 2})
        self.assertEqual(binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 2}),
                         {'generation': 7, 'bytes': [0, 255]})
        self.assertEqual(binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 4096})['bytes'], [4])
        self.assertEqual(binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 1})['bytes'], [])
        self.assertEqual(binding.dispatch(COMMANDS[2], {'generation': 7}), {'generation': 7, 'closed': True})
        self.assertEqual(binding.status(), {'generation': 7, 'state': 'closed'})
        with self.assertRaises(ValueError): binding.dispatch(COMMANDS[0], {'generation': 7, 'bytes': [1]})

    def test_replaced_object_wrong_type_generation_and_fault_fail_closed(self):
        binding = self.binding()
        self.route['external:programUart'] = Terminal()
        with self.assertRaises(ValueError): binding.status()
        binding = self.binding(); self.model.Generation = 8
        with self.assertRaises(ValueError): binding.status()
        binding = self.binding(); self.model.GetType = lambda: SimpleNamespace(FullName='OtherTerminal')
        with self.assertRaises(ValueError): binding.status()
        binding = self.binding(); self.model.IsFaulted = True
        self.assertEqual(binding.status()['state'], 'faulted')
        with self.assertRaises(ValueError): binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 1})

    def test_model_errors_and_bad_output_do_not_expose_diagnostics(self):
        binding = self.binding()
        def broken(*args): raise RuntimeError('private synthetic /private/image.bin')
        self.model.Read = broken
        with self.assertRaisesRegex(ValueError, '^program UART operation failed$'):
            binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 1})
        for output in [[0, 1], [-1], [256]]:
            self.model.Read = lambda *args: output
            with self.assertRaisesRegex(ValueError, '^program UART operation failed$'):
                binding.dispatch(COMMANDS[1], {'generation': 7, 'maxBytes': 1})

    def test_actual_dispatch_returns_data_and_refuses_other_firmware(self):
        tree = ast.parse((ROOT / 'scripts/spike-state-server.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_dispatch')
        env = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'actual-dispatch', 'exec'), env)
        binding = self.binding()
        command = {'command': COMMANDS[0], 'arguments': {'generation': 7, 'bytes': [13]}}
        self.assertEqual(env['_dispatch'](config(), command, program_uart=binding), {'generation': 7, 'count': 1})
        bad = config(); bad['identity']['firmware'] = 'brickwright-nuttx'
        with self.assertRaises(ValueError): env['_dispatch'](bad, command, program_uart=binding)
        with self.assertRaises(ValueError): env['_dispatch'](config(), command)


if __name__ == '__main__':
    unittest.main()
