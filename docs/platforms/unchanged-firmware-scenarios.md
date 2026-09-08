# Unchanged firmware scenarios

The scenario catalog covers LEGO Prime v2, LEGO Prime v3, Pybricks Prime,
spike-nx, Brickwright NuttX, LEGO Essential, and Pybricks Essential. Firmware
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

The present opaque LEGO and Pybricks images have no public symbol contract, and
the device models do not yet expose stable transaction counters to Robot tests.
They therefore claim only vector and CPU progress. Loading a port, display,
storage, or Bluetooth model is not evidence that firmware exercised it. Those
milestones remain pending until observable counters or an equivalent public
contract exists.

With local inputs present, Prime v2, Prime v3, and Pybricks Prime pass this
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
