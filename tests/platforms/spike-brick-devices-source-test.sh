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

