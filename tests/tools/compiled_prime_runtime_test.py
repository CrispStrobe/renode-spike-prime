#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compiled route admission controls; these do not execute a guest."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import check_prime_nuttx as checker
from stage_prime_runtime import stage_compiled


class CompiledRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.infrastructure = self.root / 'infrastructure'
        (self.infrastructure / 'licenses').mkdir(parents=True)
        (self.infrastructure / 'licenses/MIT.txt').write_text('synthetic notice')

    def test_compiled_topology_has_no_source_extensions_or_network_inputs(self):
        output = self.root / 'runtime'
        stage_compiled(self.infrastructure, output, True)
        self.assertFalse(list(output.rglob('*.cs')))
        cpus = (output / 'platforms/cpus/stm32f4.repl').read_text()
        self.assertIn('timer12: Timers.STM32TLCClock', cpus)
        self.assertNotIn('timer12: Timers.STM32_Timer', cpus)
        self.assertNotIn('    -> nvic@43', cpus)
        board = (output / 'platforms/boards/spike-prime-brick-devices.repl').read_text()
        self.assertIn('timer12:\n    display: display', board)
        for path in output.rglob('*.repl'):
            text = path.read_text()
            self.assertNotIn('BrickwrightSTM32', text)
            self.assertNotIn('BrickwrightGenericSpiFlash', text)
            self.assertNotIn('https://', text)
            self.assertNotIn('http://', text)
        self.assertEqual((output / 'licenses/renode-models-MIT.txt').read_text(), 'synthetic notice')
        with self.assertRaisesRegex(ValueError, 'prior packages are preserved'):
            stage_compiled(self.infrastructure, output, True)

    def test_checker_compiled_route_does_not_include_models(self):
        output = self.root / 'result'
        firmware = self.root / 'firmware'
        def simulated_run(command, **kwargs):
            script = output / 'check.resc'
            text = script.read_text()
            self.assertNotIn('include @', text)
            self.assertIn('emulation CreatePrimeElectricalPorts', text)
            self.assertIn('portF Attach "motor"', text)
            settings = json.loads((output / 'config.json').read_text())
            self.assertEqual(settings['electricalModelRoute'], 'compiled-runtime')
            (output / 'result.json').write_text('{"passed": true}')
            return type('Result', (), {'returncode': 0})()
        argv = ['check_prime_nuttx.py', '--firmware-root', str(firmware),
                '--infrastructure', str(self.infrastructure), '--renode', str(self.root / 'unused'),
                '--output', str(output), '--compiled-runtime', '--all-motors-test']
        with patch.object(sys, 'argv', argv), patch.object(checker, 'vector', return_value=(0x20010000, 0x08008001)), \
             patch.object(checker.subprocess, 'check_output', side_effect=[
                 '20021000 D g_bw_program_debug\n', '20000100 00001000 D g_sysbuffer\n']), \
             patch.object(checker.subprocess, 'run', side_effect=simulated_run), \
             patch.object(checker, 'stage', side_effect=AssertionError('source route must not execute')):
            checker.main()


if __name__ == '__main__':
    unittest.main()
