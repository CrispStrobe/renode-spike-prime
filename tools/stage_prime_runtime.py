#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Stage offline Prime topology and source extensions for an older Renode.

No firmware is copied or fetched. Retained C# source notices remain intact.
Type aliases isolate these fork models from the installed runtime's classes.
"""
import argparse
from pathlib import Path
import re
import shutil

CORE = {"I2C/STM32F4_I2C.cs": "STM32F4_I2C", "Analog/ADCChannel.cs": "ADCChannel", "Analog/STM32_ADC.cs": "STM32_ADC",
        "SPI/STM32SPI.cs": "STM32SPI", "SPI/GenericSpiFlash.cs": "GenericSpiFlash",
        "Timers/STM32_Timer.cs": "STM32_Timer", "DMA/STM32DMA.cs": "STM32DMA",
        "Miscellaneous/STM32_SYSCFG.cs": "STM32_SYSCFG"}
OTHER = ("Sensors/LSM6DS3TRC.cs", "SPI/TLC5955.cs", "Miscellaneous/BrickPowerController.cs",
         "Sound/PCMAudioSink.cs", "Analog/PrimeButtonLadder.cs", "UART/Lpf2Devices.cs",
         "UART/Lpf2ArenaSensors.cs", "UART/LegoLpf2Port.cs", "UART/LegoLpf2ElectricalPort.cs", "UART/PrimeElectricalPorts.cs")


def stage(infrastructure, output, aggregate_display=False):
    if output.exists():
        raise ValueError("output already exists; prior packages are preserved")
    root = Path(__file__).resolve().parents[1]
    peripheral = infrastructure / "src/Emulator/Peripherals/Peripherals"
    bodies, imports = [], set()
    substitutions = {name: "Brickwright" + name for name in CORE.values()}
    sources = tuple(CORE) + OTHER + (("Timers/STM32TLCClock.cs",) if aggregate_display else ())
    for name in sources:
        source = (peripheral / name).read_text()
        for original, alias in substitutions.items():
            source = re.sub(r"\b" + original + r"\b", alias, source)
        imports.update(re.findall(r"^using [^\n]+;", source, re.M))
        bodies.append(re.sub(r"^using [^\n]+;\n", "", source, flags=re.M))
    output.mkdir(parents=True, mode=0o700)
    (output / "models.cs").write_text("\n".join(sorted(imports)) + "\n" + "\n".join(bodies))
    for name in ("boards/spike-prime.repl", "boards/spike-prime-brick-devices.repl",
                 "cpus/stm32f413vg.repl", "cpus/stm32f4.repl"):
        source = (root / "platforms" / name).read_text()
        source = "\n".join(line for line in source.splitlines() if "ApplySVD @https://" not in line) + "\n"
        for original, alias in substitutions.items():
            source = re.sub(r"\b" + original + r"\b", alias, source)
        if aggregate_display and name == "cpus/stm32f4.repl":
            source = source.replace("timer12: Timers.BrickwrightSTM32_Timer", "timer12: Timers.STM32TLCClock")
            source = source.replace("    -> nvic@43\n", "")
            source = re.sub(r"^timer12:\n(?:    [^\n]*\n)+", "", source, flags=re.M)
        if aggregate_display and name == "boards/spike-prime-brick-devices.repl":
            source = source.replace("timer12:\n    1 -> display@1", "timer12:\n    display: display")
        if "http://" in source or "https://" in source:
            raise ValueError("network-dependent platform cannot be staged")
        target = output / "platforms" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    (output / "licenses").mkdir()
    shutil.copyfile(infrastructure / "licenses/MIT.txt", output / "licenses/renode-models-MIT.txt")
    shutil.copyfile(root / "licenses/arena-BSD-3-Clause.txt", output / "licenses/brickwright-BSD-3-Clause.txt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregate-display-clock", action="store_true",
                        help="use the qualified TIM12 PWM subset without individual GSCLK pulse traces")
    arguments = parser.parse_args()
    stage(arguments.infrastructure.resolve(), arguments.output.resolve(), arguments.aggregate_display_clock)
