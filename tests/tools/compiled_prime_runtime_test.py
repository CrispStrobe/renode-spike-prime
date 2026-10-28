#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compiled route admission controls; these do not execute a guest."""
import json
from pathlib import Path
import sys
import tempfile
import struct
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
        (firmware / 'nuttx').mkdir(parents=True)
        (firmware / 'nuttx/nuttx').write_bytes(b'synthetic kernel')
        (firmware / 'nuttx/nuttx_user.elf').write_bytes(b'synthetic userspace')
        (self.root / 'unused').write_bytes(b'synthetic runtime')
        def simulated_run(command, *args, **kwargs):
            script = output / 'check.resc'
            text = script.read_text()
            self.assertNotIn('include @', text)
            self.assertIn('emulation CreatePrimeElectricalPorts', text)
            self.assertIn('portF Attach "motor"', text)
            settings = json.loads((output / 'config.json').read_text())
            self.assertEqual(settings['electricalModelRoute'], 'compiled-runtime')
            (output / 'result.json').write_text('{"passed": true}')
            return 0
        argv = ['check_prime_nuttx.py', '--firmware-root', str(firmware),
                '--infrastructure', str(self.infrastructure), '--renode', str(self.root / 'unused'),
                '--output', str(output), '--compiled-runtime', '--all-motors-test']
        with patch.object(sys, 'argv', argv), patch.object(checker, 'vector', return_value=(0x20010000, 0x08008001)), \
             patch.object(checker.subprocess, 'check_output', side_effect=[
                 '20021000 D g_bw_program_debug\n', '20000100 00001000 D g_sysbuffer\n']), \
             patch.object(checker, 'run_measured', side_effect=simulated_run), \
             patch.object(checker, 'stage', side_effect=AssertionError('source route must not execute')):
            checker.main()

    def test_saved_record_damage_changes_only_payload_and_preserves_original(self):
        marker = struct.pack('<4s4BIII', b'BWP1', 1, 0, 0, 0, 301, 256, 4096)
        original = b'filesystem-metadata' + marker + bytes(4096) + b'crc'
        source, target = self.root / 'flash.bin', self.root / 'damaged.bin'
        source.write_bytes(original)
        receipt = checker.corrupt_program_snapshot(source, target)
        damaged = target.read_bytes()
        self.assertEqual(source.read_bytes(), original)
        differences = [i for i, (a, b) in enumerate(zip(original, damaged)) if a != b]
        self.assertEqual(differences, [len(b'filesystem-metadata') + len(marker)])
        self.assertEqual(damaged[differences[0]], 1)
        self.assertNotEqual(receipt['sourceSha256'], receipt['damagedSha256'])
        with self.assertRaises(FileExistsError):
            checker.corrupt_program_snapshot(source, target)
        for invalid in (b'no matching record', original + marker):
            source.write_bytes(invalid)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                checker.corrupt_program_snapshot(source, self.root / 'refused.bin')
            self.assertFalse((self.root / 'refused.bin').exists())


if __name__ == '__main__':
    unittest.main()
