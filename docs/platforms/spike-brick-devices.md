# SPIKE brick-device observation layer

The optional `spike-*-brick-devices.repl` files expose deterministic state for
tests and frontends. They contain no LEGO firmware or TI service-pack data.

## Interfaces

| Device | Observable or controllable state | Limit |
|---|---|---|
| Center button | Essential PB2 active-low press/release | Prime uses ADC resistor ladders, so its buttons are not falsely represented as digital GPIOs. |
| Power policy | Battery millivolts, low/power-good, charger connection/status, power-hold and latched shutdown request | This is a board-policy abstraction, not an electrical MP2639A charger model. Inputs and outputs are active-high internally. Essential PB1 power-hold and PA10 charger-mode are wired. |
| Prime display | TLC5955 97-byte raw shift and latched snapshots plus frame counters | The snapshot does not decode the 5x5 optical matrix or simulate GSCLK brightness. |
| Essential LEDs | Supplied by the separate LP50xx/FMPI2C1 layer | This overlay deliberately does not duplicate that model. |
| IMU | Explicit deterministic samples, output registers, 4 KiB byte FIFO, threshold status and INT1/INT2 | `AdvanceSample` is the model clock. Sensor physics, ODR scheduling, and unimplemented FIFO modes are outside the contract. |
| Prime speaker | One-byte DMA target at DAC1 DHR12R1 (`0x40007408`), bounded PCM snapshot, overflow counters, PC10 amplifier enable | Captures low bytes only. It does not model the STM32 DAC, TIM6 pacing, analog output or host playback. Writes while disabled are counted and discarded. |

The Prime mappings are sourced from the MIT-tagged Pybricks `prime_hub/platform.c`
at commit `101c6babb592148bda9a8fd912b7953c7d561c0a`: I2C2 IMU with PB4 INT1,
SPI1 TLC5955 with PA15 LAT, PA13 power hold, DAC1 channel 1 with DMA1 stream 5,
and PC10 amplifier enable. Essential mappings use the same pinned source and are
also summarized in `spike-essential.md`.

## Verification

Run `tests/platforms/spike-brick-devices-source-test.sh` for static wiring
checks. Focused NUnit fixtures cover power transitions, disabled and overflowing
audio writes, IMU FIFO/interrupt behavior, and TLC5955 snapshots. The checks do
not download or retain firmware.
