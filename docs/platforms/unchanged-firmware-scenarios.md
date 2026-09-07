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
device initialization functions. `bluetooth-bootstrap` and `daemon-ready`
additionally require the transport-neutral H4 controller.

The present opaque LEGO and Pybricks images have no public symbol contract, and
the device models do not yet expose stable transaction counters to Robot tests.
They therefore claim only vector and CPU progress. Loading a port, display,
storage, or Bluetooth model is not evidence that firmware exercised it. Those
milestones remain pending until observable counters or an equivalent public
contract exists.

Public CI tests only the catalog, loader, skip behavior, and tamper rejection
with synthetic bytes. It never obtains or uploads firmware, manifests, hashes,
test logs derived from private images, or TI controller data.
