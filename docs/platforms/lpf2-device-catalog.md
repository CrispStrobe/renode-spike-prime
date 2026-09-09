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

- SPIKE Color Sensor type 61: Pybricks commit
  `621b830b531ef32c29af7fe12ae963c2bcc19832` is MIT licensed. Its
  `lib/lego/lego/device.h` blob
  `e397dc406bf1f4819f5e23d3a135d5880c579f8e` supplies all ten mode indices,
  names, widths, data types, and the three-byte LIGHT output shape. Its
  `lib/lego/lego/lump.h` blob
  `7b842e04d133ffb8c73dc4203f6d829a7f14397a` supplies type 61. Neither file nor
  the repository's UART tests supplies the complete discovery transcript,
  per-mode units/ranges/mappings, versions, or LIGHT value semantics.
- SPIKE Force Sensor type 63: the same pinned `lump.h` supplies type 63, while
  the same pinned `device.h` supplies only FRAW mode 4 as one `int16_t` and
  CALIB mode 6 as eight `int16_t` values. Modes 0--3 and 5, the complete
  discovery transcript, units/ranges/mappings, versions, and output semantics
  remain absent.
- SPIKE Large Motor type 49: the same pinned `lump.h` supplies the ID. Pybricks
  `lib/pbio/src/motor/servo_settings.c` blob
  `83047c7772d6fe76b1959568d81ea255d0775f69` establishes that its control
  tuning is shared with the Technic Large Angular Motor, but does not establish
  an identical UART discovery contract. No complete type-49 discovery fixture,
  units/widths/mappings/version record, or device-side command semantics is
  present.

Pybricks Technical Information commit
`cce611e0d28278d9d5b4472f101a89fc7c81e778` is also MIT licensed. Its
`assigned-numbers.md` and `uart-protocol.md` corroborate the three IDs and the
generic discovery grammar, but contain no device-specific transcript or mode
table that closes the gaps above. The audit also checked the full history of
Pybricks' `lib/pbio/test/src/test_uartdev.c`; its exact transcripts cover older
devices, including type 46, but not types 49, 61, or 63.

These devices stay unimplemented until a complete MIT/Apache/BSD-compatible
primary capture or specification can be pinned by file and commit.

## Closing the gaps

The BSD-3-Clause Build HAT firmware at commit
`19027849264d8839f7548713219a5982925dd885` provides a permissible acquisition
path. Its `firmware-pico/message.c` blob
`10700817c720ef9f3d308e49187046076cd0f288` parses the discovery messages and
its `firmware-pico/device.c` blob
`3fb471a3572bb3d733c7984b60cd6354e2cedb62` prints the resulting mode table.
Those files do not contain device-specific tables, so they are capture tooling,
not evidence for any pending device.

One evidence set per physical device must contain:

- the raw, byte-exact startup exchange from electrical connection through both
  ACKs and the first data frame in every readable mode;
- the complete parser dump, including device type, baud rate, versions, mode
  count, combinations, names, units, formats, ranges and mappings;
- one raw host-to-device frame and its observed effect for every writable mode;
- the LEGO element number and all visible hardware/firmware revisions;
- SHA-256 hashes of every capture and a signed-off `CC0-1.0`, `MIT`,
  `Apache-2.0` or `BSD-3-Clause` contribution declaration.

Capture facts must agree with the pinned Pybricks declarations above. A model
may cover only the physical revision actually captured; differences between
revisions remain separate evidence sets. Human-readable tables without an
explicit compatible licence and runtime API summaries without raw discovery
bytes cannot satisfy this gate.

The public search through 2026-09-09 found useful tables in third-party pages
and issue reports, but no explicit compatible licence covering their device
data. They were therefore not used. Raspberry Pi's `docs/protocol.md` is also
outside the two source-directory `LICENSE.txt` files and is not treated as
BSD-3-Clause evidence.
