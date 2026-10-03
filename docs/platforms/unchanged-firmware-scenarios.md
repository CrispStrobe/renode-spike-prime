# Unchanged firmware scenarios

The scenario catalog covers LEGO Prime v2, LEGO Prime v3,
spike-nx, Brickwright NuttX, and LEGO Essential. Firmware
bytes remain local and unchanged. The catalog is versioned separately from
input manifests so incompatible contract changes require a new version.

Prepare one raw image:

```bash
tools/spike-firmware-scenarios/scenario_manifest.py prepare lego-prime-v2 \
  --artifact firmware=raw=0x08008000=/path/to/firmware.bin
```

Prepare a protected NuttX pair:

```bash
tools/spike-firmware-scenarios/scenario_manifest.py prepare brickwright-nuttx \
  --artifact kernel=elf=0x08008000=/path/to/nuttx \
  --artifact userspace=elf=0x08080000=/path/to/nuttx_user.elf
```

The default private input root is `.local/spike-firmware-scenarios`. Override
it with `--root`. `verify TARGET` returns 77 and prints `SKIP` when the manifest
is absent. A missing artifact, changed size, or SHA-256 mismatch returns 1
before Renode is started.

## Observable milestone contract

`vectors-valid` proves that the initial stack and reset handler belong to the
target MCU windows. `cpu-progress` proves bounded instruction progress. Symbol
milestones in locally built NuttX ELF files prove entry into named boot and
device initialization functions. `bluetooth-board-init` proves entry into the
board's controller setup. `daemon-ready` proves that the dedicated Renode
firmware profile auto-started `btsensor` through its permissive in-process HCI
controller. This path does not use USART2, the CC2564C, or a TI service pack.

The present opaque LEGO images have no public symbol contract, and
the device models do not yet expose stable transaction counters to Robot tests.
They therefore claim only vector and CPU progress. Loading a port, display,
storage, or Bluetooth model is not evidence that firmware exercised it. Those
milestones remain pending until observable counters or an equivalent public
contract exists.

With local inputs present, Prime v2 and Prime v3 pass this
bounded vector/progress gate; spike-nx passes its protected two-ELF boot-symbol
gate. These results do not imply full peripheral compatibility.

The Prime machine currently has display, IMU, storage, power, speaker, and H4
building blocks but no source-cited LPF2 port wiring overlay. Prime port traffic
is therefore not claimed. Runtime dictionary expansion, monitor numeric
conversion, two-ELF symbol lookup, device initialization, SPI1 RX/TX DMA, and
entry into USART2 board initialization pass with the local Brickwright image.
That run also validates a bounded state-service snapshot after these milestones.

Public CI tests only the catalog, loader, skip behavior, and tamper rejection
with synthetic bytes. It never obtains or uploads firmware, manifests, hashes,
test logs derived from private images, or TI controller data.

The catalog Robot scenarios above and the separate
`tools/spike_local_image.py` Prime raw/HEX probe have different assertions.
The separate probe requires an explicit vector address. It observes unsigned
64-bit instruction counts before and after
single stepping and requires the exact requested delta. Final PC must be even
and point to two bytes present in the original input; final SP must remain
eight-byte aligned in SRAM. An NVIC ICSR read rejects active fault exceptions
3 through 6. A self-loop can pass when the instruction count proves execution.
These private observations establish bounded execution only, not boot, REPL,
program, or peripheral success. Direct application entry also does not prove
that an earlier bootloader reached the application. The probe connects no
console transport and retains its observations beneath the private output.
Its explicitly selected local platform, model sources, and Renode runtime must
support the same model interfaces. Platform-loading or model-compilation errors
fail the probe before CPU execution; they establish no firmware behavior.

For a locally compiled pacing-capable SPI model, the probe also accepts
`--storage-spi-frequency 48000000` to select a 48 MHz SPI2 input clock.
The model divides that input clock by `2 << BR` and rounds each supported
eight-bit transfer up to a nanosecond. It schedules a shifting byte and a
holding byte, exposes TXE/BSY, and cancels pending work on reset or SPI disable.
The default clock is zero, retaining instantaneous transfers; the receive queue
still holds four bytes. Only the explicitly selected storage SPI interface is
changed. Clock selection does not establish a REPL, USB device support or
complete STM32 timing/overflow behavior. DFF/16-bit transfers remain unsupported.

`--storage-spi-buffer-capacity 1` selects a one-byte storage receive queue;
omitting it retains the local model's default. The accepted range is 1..65536
bytes. This changes only SPI2 in the staged copy. It is useful for callers that
discard command responses with one data-register read before receiving a block:
a larger queue can leave stale command responses ahead of that block. This
setting does not add an overrun flag or reproduce every silicon overflow rule.

A separate local console qualification of unchanged upstream MicroPython
v1.26.1 used a 50 MHz SPI2 clock, one-byte receive queue, 100 MHz SysTick,
normal application-entry reset mode, and an authored FAT16 `boot.py` that
selected UART2 with `os.dupterm`. It observed the program's print marker,
arithmetic, Ctrl-C interruption of a running loop, and subsequent execution.
The seeded filesystem remained unchanged. These are application-entry and
UART observations; USB device transport, original bootloader handoff, port
programs and foreign-image GUI execution remain unqualified. Images, generated
filesystem fixtures, transcripts and diagnostic output stay private. The
bounded CPU probe itself does not mount a filesystem or attach this console,
and retains its existing instruction and wall-time limits.

## Local repeated-boot resource gate

After building headless Renode, run:

```bash
tools/spike-fault-resource-soak.py
```

The gate re-verifies every locally present catalog image, runs its exact Robot
scenario three times, and deletes the private Robot results when the run ends.
It suppresses Renode output so artifact paths and hashes cannot enter console
logs. Each target has a 180-second wall guard, opaque execution is exactly
2,000 instructions per cycle, and protected execution must remain below 100
million instructions per cycle. The default aggregate resident-set ceiling for
the runner and its descendant processes is 1,536 MiB. Command-line overrides
are intended for explicit local calibration; a one-cycle run is rejected.

The W25Q256-compatible model exposes `FailNextProgramOperations` and
`FailNextEraseOperations`. Set either counter before a recovery scenario to
make that many complete operations consume write-enable while leaving storage
unchanged. `InjectedProgramFailures` and `InjectedEraseFailures` make the
consumed faults observable. These simulation controls do not alter image bytes.
