#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic staging checks; no emulator, firmware or network required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('stage_runtime', Path(__file__).parents[2] / 'tools/stage_prime_runtime.py')
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.infrastructure = self.root / 'infra'
        sources = self.infrastructure / 'src/Emulator/Peripherals/Peripherals'
        for name in tuple(stager.CORE) + stager.OTHER + ('Timers/STM32TLCClock.cs',):
            target = sources / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// retained fixture notice\nusing System;\nnamespace Fixture {}\n')
        for name in ('boards/spike-prime.repl', 'boards/spike-prime-brick-devices.repl',
                     'cpus/stm32f413vg.repl', 'cpus/stm32f4.repl'):
            target = self.root / 'platforms' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('')
        (self.root / 'platforms/cpus/stm32f4.repl').write_text(
            'timer12: Timers.STM32_Timer @ sysbus 0x40001800\n'
            '    -> nvic@43\n    frequency: 10000000\n    initialLimit: 0xFFFF\n\n'
            'timer12:\n    0 -> gpioPortB#14@09\n    1 -> gpioPortB#15@09\n\n'
            'timer13: Timers.STM32_Timer @ sysbus 0x40001C00\n    -> nvic@44\n')
        (self.root / 'platforms/boards/spike-prime-brick-devices.repl').write_text('timer12:\n    1 -> display@1\n')
        (self.root / 'platforms/cpus/stm32f413vg.repl').write_text('timer12:\n    frequency: 96000000\n')
        for parent, name in ((self.root, 'arena-BSD-3-Clause.txt'), (self.infrastructure, 'MIT.txt')):
            (parent / 'licenses').mkdir()
            (parent / 'licenses' / name).write_text('fixture licence')
        original = stager.__file__
        stager.__file__ = str(self.root / 'tools/stage_prime_runtime.py')
        self.addCleanup(setattr, stager, '__file__', original)

    def test_aggregate_replaces_platform_timer_and_wiring(self):
        output = self.root / 'output'
        stager.stage(self.infrastructure, output, True)
        cpu = (output / 'platforms/cpus/stm32f4.repl').read_text()
        self.assertIn('timer12: Timers.STM32TLCClock', cpu)
        self.assertNotIn('nvic@43', cpu)
        self.assertNotIn('gpioPortB#15', cpu)
        self.assertIn('timer13: Timers.BrickwrightSTM32_Timer', cpu)
        self.assertIn('nvic@44', cpu)
        self.assertEqual((output / 'platforms/boards/spike-prime-brick-devices.repl').read_text(), 'timer12:\n    display: display\n')
        self.assertIn('96000000', (output / 'platforms/cpus/stm32f413vg.repl').read_text())
        self.assertIn('retained fixture notice', (output / 'models.cs').read_text())
        self.assertEqual(len(list((output / 'licenses').iterdir())), 2)

    def test_default_preserves_pulse_timer(self):
        output = self.root / 'output'
        stager.stage(self.infrastructure, output)
        cpu = (output / 'platforms/cpus/stm32f4.repl').read_text()
        self.assertIn('timer12: Timers.BrickwrightSTM32_Timer', cpu)
        self.assertIn('nvic@43', cpu)
        self.assertIn('gpioPortB#15', cpu)

    def test_prior_packages_are_preserved(self):
        output = self.root / 'output'
        output.mkdir()
        sentinel = output / 'keep'
        sentinel.write_text('original')
        with self.assertRaises(ValueError):
            stager.stage(self.infrastructure, output)
        self.assertEqual(sentinel.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
