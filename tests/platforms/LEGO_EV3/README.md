# LEGO EV3 / AM1808 executable baseline

This test is an MIT-licensed, source-built validation image. It does not use,
derive from, or redistribute LEGO recovery firmware.

Build it with:

```sh
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-smoke.elf am1808-smoke.S
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-timer64-smoke.elf am1808-timer64-smoke.S
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-control-smoke.elf am1808-control-smoke.S
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wl,-T,am1808-smoke.ld \
  -o am1808-edma-smoke.elf am1808-edma-smoke.S
arm-none-eabi-gcc -mcpu=arm926ej-s -nostdlib -Wa,-defsym,EDMA_HW16=1 \
  -Wl,-T,am1808-smoke.ld -o am1808-edma-hw16-smoke.elf \
  am1808-edma-smoke.S
```

Then load `platforms/boards/lego-ev3.repl`, load the ELF, attach a UART analyzer
to `uart1`, and start. `EV3 ARM9 IRQ` proves ARM926 instruction execution,
the EV3 debug UART address and the AM1808 AINTC IRQ/acknowledge path.

The Timer64 image prints `EV3 TIMER64 IRQ` only from the ARM IRQ handler after
Timer64P0 reaches its programmed period and raises physical AINTC event 21. It
does not use the AINTC software-set register, so it is executable evidence for
the modeled timer and its SoC routing rather than another interrupt-controller
smoke test.

The control image prints `EV3 PSC PLL PINMUX OK` only after it validates the
explicit EV3 post-EEPROM handoff values, performs a PSC module transition,
performs and completes a PLL divider GO transition, proves that pinmux,
suspend and chip-configuration registers remain writable after both wrong and
correct KICK sequences (the documented revision 2+ behavior), and restores the
handoff values. A distinct `FAIL` line makes a bad preset observable rather
than merely timing out.

The EDMA image has two builds. The default programs DRAE0, PaRAM set 0 and
region-0 interrupt enables, starts a 16-byte copy with software `ESR`, receives
the real EDMA0 completion signal through AINTC event 11, and prints exactly
`EV3 EDMA IRQ` only after checking all copied words. The `EDMA_HW16` build
instead uses the public MMC/SD0 receive event mapping. An isolated test button
pulses EDMA0 channel 16 before the CPU starts, proving the request latches with
EER clear and drains when the guest writes EESR; success is
`EV3 EDMA HW16 IRQ`. The button exists only in the test overlay, not the EV3
production platform. This is request-line coverage for the public MMC/SD0 RX
mapping, not a claim that an MMC controller is integrated yet.
Wrong IRQ state, missing completion and corrupt data each produce a distinct
`EV3 EDMA FAIL ...` line, so mutations cannot silently look like success.

EDMA transfers complete synchronously in the current functional model. This
proves programming, bus-copy and interrupt semantics, not cycle-accurate queue
or bus-arbitration timing.

This is deliberately not described as full EV3 emulation. The next required
models are MMC/SD, GPIO, LCDC, SPI/ADC sensor and motor front ends, and
optionally PRU.
