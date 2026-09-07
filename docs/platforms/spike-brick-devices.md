# SPIKE brick-device observation layer

The optional `spike-*-brick-devices.repl` files expose deterministic state for
tests and frontends. They contain no LEGO firmware or TI service-pack data.

## Interfaces

| Device | Observable or controllable state | Limit |
|---|---|---|
| Center button | Essential PB2 active-low press/release | Prime uses ADC resistor ladders, so its buttons are not falsely represented as digital GPIOs. |
| Power policy | Battery millivolts, low/power-good, charger connection, suspended/charging/complete state, power-hold and latched shutdown request | This is a board-policy abstraction, not an electrical MP2639A charger model. Inputs and outputs are active-high internally. Essential PB1 power-hold and PA10 charger-mode are wired. |
| Prime display | TLC5955 raw latches, all 48 decoded 16-bit channels, the source-cited 5x5 matrix channel map, latch counters and explicit GSCLK phase | GSCLK advances through explicit edges; TIM12 output wiring and optical response are not modeled. |
| Essential LEDs | Supplied by the separate LP50xx/FMPI2C1 layer | This overlay deliberately does not duplicate that model. |
| IMU | Explicit deterministic samples, CTRL1/CTRL2 ODR scheduling, output registers, 4 KiB byte FIFO, threshold status and INT1/INT2 | Time advances only through `AdvanceTimeMicroseconds`; sensor physics and unimplemented FIFO modes remain outside the contract. |
| Prime speaker | Byte observations plus bounded 12-bit DAC sample input, explicit sample-clock advancement, overflow counters and PC10 amplifier enable | The deterministic sample clock is not yet connected to the STM32 TIM6 TRGO/DMA request path; analog output and host playback are excluded. |

The Prime mappings are sourced from the MIT-tagged Pybricks `prime_hub/platform.c`
at commit `101c6babb592148bda9a8fd912b7953c7d561c0a`: I2C2 IMU with PB4 INT1,
SPI1 TLC5955 with PA15 LAT, PA13 power hold, DAC1 channel 1 with DMA1 stream 5,
and PC10 amplifier enable. The 5x5 map is the `pwm_chs` table in the same
source. Essential mappings use that pinned source and are summarized in
`spike-essential.md`. The IMU ODR table follows ST's public LSM6DS3TR-C data
sheet register encodings.

## Verification

Run `tests/platforms/spike-brick-devices-source-test.sh` for static wiring
checks. Focused NUnit fixtures cover power transitions, disabled and overflowing
audio writes, IMU FIFO/interrupt behavior, and TLC5955 snapshots. The checks do
not download or retain firmware.
