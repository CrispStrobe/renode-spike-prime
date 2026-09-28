# LEGO EV3 / AM1808 executable baseline

This test is an MIT-licensed, source-built validation image. It does not use,
derive from, or redistribute LEGO recovery firmware.

Build it with:

```sh
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-smoke.elf am1808-smoke.S
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-timer64-smoke.elf am1808-timer64-smoke.S
```

Then load `platforms/boards/lego-ev3.repl`, load the ELF, attach a UART analyzer
to `uart1`, and start. `EV3 ARM9 IRQ` proves ARM926 instruction execution,
the EV3 debug UART address and the AM1808 AINTC IRQ/acknowledge path.

The Timer64 image prints `EV3 TIMER64 IRQ` only from the ARM IRQ handler after
Timer64P0 reaches its programmed period and raises physical AINTC event 21. It
does not use the AINTC software-set register, so it is executable evidence for
the modeled timer and its SoC routing rather than another interrupt-controller
smoke test.

This is deliberately not described as full EV3 emulation. The next required
models are PSC/PLL and pinmux sufficient for U-Boot/Linux, EDMA, MMC/SD, GPIO,
LCDC, SPI/ADC sensor and motor front ends, and optionally PRU.
