# SPIKE Essential simulation map

This machine is a distinct, evidence-bounded SPIKE Essential Hub target. It is
not a SPIKE Prime alias. The map is derived from Pybricks commit
`101c6babb592148bda9a8fd912b7953c7d561c0a`, whose relevant source files are
MIT-licensed:

- [linker map](https://github.com/pybricks/pybricks-micropython/blob/101c6babb592148bda9a8fd912b7953c7d561c0a/lib/pbio/platform/essential_hub/platform.ld)
- [peripheral and pin definitions](https://github.com/pybricks/pybricks-micropython/blob/101c6babb592148bda9a8fd912b7953c7d561c0a/lib/pbio/platform/essential_hub/platform.c)
- [enabled drivers and device sizes](https://github.com/pybricks/pybricks-micropython/blob/101c6babb592148bda9a8fd912b7953c7d561c0a/lib/pbio/platform/essential_hub/pbdrvconfig.h)

## Verified map

| Component | Verified Essential configuration | Model status |
|---|---|---|
| MCU memory | STM32F413; firmware `0x08008000`–`0x080fffff`; contiguous SRAM `0x20000000`–`0x2004ffff` | Shared STM32F4 model plus the upper 64 KiB SRAM. The shared model exposes 2 MiB flash, so loaders enforce image bounds. |
| IMU | LSM6DS3TR-C at I2C3; SCL PA8, SDA PC9, INT1 PC13 | Deterministic I2C register model at address `0x6a`; interrupt routing and timing are not yet modeled. |
| External store | W25Q32-class device on SPI2; PB12 active-low CS; DMA1 streams 3 RX and 4 TX | Generic 4 MiB SPI NOR with JEDEC `ef 40 16`; SPI2 RX/TX DMA requests connect to streams 3/4. |
| Bluetooth | CC256x H4 on USART2; DMA1 streams 6 TX and 7 RX; enable PC8 | Controller and lawful external responder are not part of this source-only checkpoint. |
| User ports | Two ports: UART5 for A and USART3 for B, with the GPIO map in the cited platform file | MCU UARTs exist, but Powered Up electrical devices and motor loads are not modeled. |
| LEDs | LP50xx on FMPI2C1, enable PB13 | Not modeled because this Renode baseline lacks an evidenced FMPI2C1/LP50xx pair. |
| Button/power/charger | Center button PB2 active-low; power hold PB1; MP2639A mode PA10 and CHG PC6 | GPIOs exist; board-level behavior is not modeled. |

`platforms/boards/spike-essential.repl` contains only the verified executable
subset. Unsupported devices are deliberately absent rather than silently
borrowed from Prime.

## Local image gates

No firmware is downloaded, tracked, or uploaded. Prepare a user-supplied image:

```sh
tools/spike-essential/prepare-local-image.sh pybricks path/to/firmware.bin raw 0x08008000
tools/spike-essential/prepare-local-image.sh official path/to/firmware.bin raw 0x08000000
# ELF input also requires the address of its vector table:
tools/spike-essential/prepare-local-image.sh pybricks path/to/firmware.elf elf 0x08008000
```

The loader copies it beneath ignored `.local/spike-essential-images/`, records
its SHA-256, size, format and vector address. Raw images that exceed the
verified 1 MiB internal-flash window are rejected. `SPIKE_Essential_images.robot` rechecks
the hash before loading. Its present milestone is deliberately narrow: a valid
vector table, reset PC inside internal flash, and bounded instruction progress.
It does not claim successful board initialization, BLE, LEDs, ports, or an
application prompt.
