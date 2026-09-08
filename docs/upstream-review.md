# Upstream review manifest

This manifest records generic changes only. It has no LEGO, TI, firmware-image,
or Brickwright interface dependency. Topic branches remain separate so they can
be reviewed or submitted independently. Automation must not open upstream pull
requests.

## Current baselines

- Renode: `6c860c0ae46bd203050e8b247d0b68ed27a13a0c`
- Renode Infrastructure: `556f8cb6f9e50d472728d4946183ccd82a931f86`

## Completed current-upstream topics

- `audit/uart-current`, tip `56590f4c6`: retains upstream's managed paced
  receiver and completes UE/TE transmit gating, the SR-then-DR IDLE-clear
  sequence, and configured frame-length timing. Focused result: 6 passed.
  Complete peripheral result: 106 passed, 5 skipped, 0 failed.
- `audit/spi-dma-current`, tip `6f541e790`: retains upstream's `DMASend` and
  `DMAReceive` API while correcting completion, circular reload, request-paced
  peripheral transfers, pending level requests, and SPI-enable gating.
  Focused result: 7 passed. Complete peripheral result: 107 passed, 5 skipped,
  0 failed.
- `audit/stm32f7-i2c-current`, tip `9e0bfb9d5`: retains upstream's `DmaReceive`
  behavior and adds an independently gated, per-byte `DmaTransmit` request.
  Focused result: 2 passed. Complete peripheral result: 102 passed, 5 skipped,
  0 failed.

Each topic passed `./build.sh --skip-fetch --no-gui`, including all native cores
and the managed solution, with zero errors. The builds reported one existing
unreachable-code warning in `BitmapImageExtensions.cs`. Their elapsed times were
4m00s for UART, 4m23s for SPI-DMA, and 4m28s for STM32F7-I2C.

## Earlier replay topics

- `feat/upstream-generic-stm32-review` contains the isolated STM32 DMA
  completion correction.
- `feat/upstream-generic-devices-review` contains independent TLC5955,
  LSM6DS3TR-C, NOR/W25Q256, and LP50xx model commits.

Before any upstream submission, rebase one topic onto the then-current upstream
tip, rerun its focused fixture, complete peripheral suite, and full headless
build, then review commit authorship and message wording manually.
