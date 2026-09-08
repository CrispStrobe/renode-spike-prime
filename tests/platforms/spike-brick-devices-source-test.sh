#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

essential=platforms/boards/spike-essential-brick-devices.repl
prime=platforms/boards/spike-prime-brick-devices.repl

grep -Fq 'invert: true' "$essential"
grep -Fq '1 -> power@0' "$essential"
grep -Fq '10 -> power@1' "$essential"
grep -Fq '0 -> gpioPortC@13' "$essential"
grep -Fq 'display: SPI.TLC5955 @ spi1' "$prime"
grep -Fq '15 -> display@0' "$prime"
grep -Fq 'speaker: Sound.PCMAudioSink @ sysbus 0x40007408' "$prime"
grep -Fq '10 -> speaker@0' "$prime"
grep -Fq '1 -> display@1' "$prime"
grep -Fq 'TriggerOutput -> speaker@1' "$prime"
grep -Fq 'UpdateDMARequest -> dma1@5' "$prime"
grep -Fq 'buttonLadders: Analog.PrimeButtonLadder' "$prime"
grep -Fq 'adc: adc1' "$prime"
test -x tests/platforms/spike-prime-platform-load-test.sh

tlc=src/Infrastructure/src/Emulator/Peripherals/Peripherals/SPI/TLC5955.cs
imu=src/Infrastructure/src/Emulator/Peripherals/Peripherals/Sensors/LSM6DS3TRC.cs
audio=src/Infrastructure/src/Emulator/Peripherals/Peripherals/Sound/PCMAudioSink.cs
power=src/Infrastructure/src/Emulator/Peripherals/Peripherals/Miscellaneous/BrickPowerController.cs
ladder=src/Infrastructure/src/Emulator/Peripherals/Peripherals/Analog/PrimeButtonLadder.cs
grep -Fq 'public ushort[] Matrix' "$tlc"
grep -Fq 'GrayscaleClockEdges' "$tlc"
grep -Fq 'AdvanceTimeMicroseconds' "$imu"
grep -Fq 'AdvanceSampleClock' "$audio"
grep -Fq 'ChargeStates' "$power"
grep -Fq 'adc.SetChannelValue(14, Ladder0Value)' "$ladder"
grep -Fq 'adc.SetChannelValue(1, Ladder1Value)' "$ladder"
