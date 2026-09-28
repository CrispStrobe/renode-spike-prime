# SPIKE brick-device observation layer

The optional `spike-*-brick-devices.repl` files expose deterministic state for
tests and frontends. They contain no LEGO firmware or TI service-pack data.

## Interfaces

| Device | Observable or controllable state | Limit |
|---|---|---|
| Prime buttons | Center, left, right and Bluetooth controls feed two resistor-ladder models, which continuously supply ADC1_IN14/PC4 and ADC1_IN1/PA1 | Values are fixed interior points of the source thresholds, so emulated results are deterministic and contain no electrical noise. |
| Center button | Essential PB2 active-low press/release | Essential uses a digital input and does not share the Prime ladder. |
| Power policy | Battery millivolts, low/power-good, charger connection, suspended/charging/complete state, power-hold and latched shutdown request | This is a board-policy abstraction, not an electrical MP2639A charger model. Inputs and outputs are active-high internally. Essential PB1 power-hold and PA10 charger-mode are wired. |
| Prime display | TLC5955 raw latches, all 48 decoded 16-bit channels, the source-cited 5x5 matrix channel map, latch counters and TIM12_CH2-driven GSCLK phase | GSCLK advances from the STM32 timer on Renode's virtual clock; optical response is not modeled. |
| Essential LEDs | Supplied by the separate LP50xx/FMPI2C1 layer | This overlay deliberately does not duplicate that model. |
| IMU | Explicit deterministic samples, CTRL1/CTRL2 ODR scheduling, output registers, 4 KiB byte FIFO, threshold status and INT1/INT2 | Time advances only through `AdvanceTimeMicroseconds`; sensor physics and unimplemented FIFO modes remain outside the contract. |
| Prime speaker | Byte observations plus bounded 12-bit DAC sample input, TIM6 TRGO pacing, DMA1 stream 5 requests, overflow counters and PC10 amplifier enable | One queued sample advances per virtual-clock TRGO pulse; analog output and host playback are excluded. |

The Prime mappings are sourced from the MIT-tagged Pybricks `prime_hub/platform.c`
at commit `101c6babb592148bda9a8fd912b7953c7d561c0a`: I2C2 IMU with PB4 INT1,
SPI1 TLC5955 with PA15 LAT, PA13 power hold, DAC1 channel 1 with DMA1 stream 5,
and PC10 amplifier enable. The 5x5 map is the `pwm_chs` table in the same
source. That file also pins TIM12_CH2/PB15 as the 9.6 MHz GSCLK, TIM6 TRGO as
the DAC1_CH1 trigger, DMA1 stream 5/channel 7 as the DAC request, and the two
button ladders to scan indices 4 and 5. Its `HAL_ADC_MspInit()` maps those scan
inputs to ADC1_IN14/PC4 and ADC1_IN1/PA1. The MIT resistor-ladder decoder and
button mapping at the same commit define the threshold ordering and map center
to ladder 0 CH1 and left/right/Bluetooth to ladder 1 CH0/CH1/CH2. See the
[pinned platform source](https://github.com/pybricks/pybricks-micropython/blob/101c6babb592148bda9a8fd912b7953c7d561c0a/lib/pbio/platform/prime_hub/platform.c)
and [pinned decoder](https://github.com/pybricks/pybricks-micropython/blob/101c6babb592148bda9a8fd912b7953c7d561c0a/lib/pbio/drv/resistor_ladder/resistor_ladder.c).
Essential mappings use that pinned source and are summarized in
`spike-essential.md`. The IMU ODR table follows ST's public LSM6DS3TR-C data
sheet register encodings.

## Verification

Run `tests/platforms/spike-brick-devices-source-test.sh` for static wiring
checks. Focused NUnit fixtures cover power transitions, disabled and overflowing
audio writes, virtual-clock TIM6/TIM12 pulses, ADC ladder combinations, IMU
FIFO/interrupt behavior, and TLC5955 snapshots. The checks do not download or
retain firmware. Public CI also builds headless Renode and loads the complete
source-only Prime platform under a 60-second bound.
