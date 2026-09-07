# LPF2 device catalog

Only complete, permissively sourced wire contracts may become device models.
Protocol facts and simulated physics are kept separate.

## Technic Large Linear Motor

The implemented `large-motor`/`technic-large-motor` device is LPF2 type 46.
Its discovery byte stream is reproduced exactly from the logic-analyzer fixture
in Pybricks commit `101c6babb592148bda9a8fd912b7953c7d561c0a`, file
`lib/pbio/test/src/test_uartdev.c`, function `test_technic_large_motor`. That
file is SPDX-MIT. The fixture supplies the six mode names, units, widths,
mappings, checksums, versions, calibration records, and final ACK. Type and
mode declarations are corroborated by the SPDX-MIT files
`lib/lego/lego_uart.h` and `lib/pbio/include/pbdrv/legodev.h` at that commit.

The exact wire facts are type 46 and modes POWER (one int8), SPEED (one int8),
POS (one int32), APOS (one int16), CALIB (two int16), and STATS (fourteen
int16). POWER accepts a one-byte signed command. Other writable-mode meanings
are not implemented because the capture establishes their shape, not complete
command semantics.

The load, stall threshold, 1050-degree-per-second ceiling, and position
integration are deterministic simulator policy, not motor-electronics claims.

## Pending evidence

- SPIKE Color Sensor type 61: SPDX-MIT declarations identify modes, widths,
  and LIGHT output, but not its complete discovery stream and units.
- SPIKE Force Sensor type 63: SPDX-MIT declarations cover only FRAW mode 4 and
  CALIB mode 6; the remaining discovery contract is absent.
- SPIKE Large Motor type 49: the ID is declared, but no complete permissive
  discovery fixture was found. It is not the implemented Technic type-46 motor.

These devices stay unimplemented until a complete MIT/Apache/BSD-compatible
primary capture or specification can be pinned by file and commit.
