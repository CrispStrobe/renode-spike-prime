# LEGO EV3 / AM1808 executable baseline

This test is an MIT-licensed, source-built validation image. It does not use,
derive from, or redistribute LEGO recovery firmware.

Build it with:

```sh
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-smoke.elf am1808-smoke.S
```

Then load `platforms/boards/lego-ev3.repl`, load the ELF, attach a UART analyzer
to `uart1`, and start. `EV3 ARM9 IRQ` proves ARM926 instruction execution,
the EV3 debug UART address and the AM1808 AINTC IRQ/acknowledge path.

This is deliberately not described as full EV3 emulation. The next required
models are the DA8xx 64-bit timer, PSC/PLL stubs sufficient for U-Boot/Linux,
GPIO, LCDC, MMC/SD, SPI/ADC sensor and motor front ends, and optionally PRU.
