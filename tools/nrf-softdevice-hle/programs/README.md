# Test programs: MakeCode micro:bit V1, Bluetooth UART

Two MakeCode programs and their **application regions** (the `.v1.bin` files,
loaded at 0x18000), used by `../e2e_bond_uart.py`. The MBR, SoftDevice and
bootloader are not here: `../appimage.py` drops every byte outside the
application region unread, and the SoftDevice is emulated.

| program | what it does | expected on V1 (`manifest.json`) |
|---------|--------------|----------------------------------|
| `ble-uart-echo` | UART service; each received line is sent back as `echo <line>` | `echo`: three lines round-trip after a bonded reconnect |
| `ble-uart-echo-icons` | the same, plus `showIcon` on connect/disconnect and `showString("B")` | `panic:20`: the DAL runs out of heap at the bonded reconnection |

## Why `ble-uart-echo-icons` panics with 020 (out of memory)

The MakeCode V1 DAL has ONE heap, 4088 bytes (0x20002b08-0x20003b00 in this
build; the rest of the 16 KB RAM is the SoftDevice's reservation, globals and
the stack). Measured in labwired at the moment of the panic
(`e2e_bond_uart.py --dump-ram-at-panic`, heap blocks walked): 3604 bytes used
in 54 blocks, 484 free in 8 fragments, the largest free block 268 bytes. When
the phone reconnects with the bond, the program's `onBluetoothConnected`
handler starts `showIcon` on a fiber; a fiber that blocks has its stack copied
to the heap, here 288 bytes. `malloc` fails and `microbit_panic(20)` follows,
at the same emulated time (19.46 s) in every run: the phone's reconnection is
gated on the board's advertising, which runs on the emulated clock. How far
the phone itself gets before the board stops answering (encryption, discovery,
the first line) depends on wall-clock scheduling, so the test asserts only the
reconnection and the panic code. The connect/disconnect handlers and the
display animation are what the lean program does not allocate. Out-of-memory panics with Bluetooth enabled are a known V1
limitation (the 16 KB nRF51822); this has not been compared with a physical
board.

With the reset-button pull-up modelled (P0.19, labwired-core
`crates/core/src/peripherals/gpio.rs`), the panic loop keeps showing its
code, as on hardware, instead of resetting the board.

## Rebuilding the images

Compiler: pxt-microbit 9.1.1 with pxt-core 13.0.1 (`manifest.json`), packages
`core` + `bluetooth`, with the target's default Bluetooth configuration
(pairing mode on, Just Works, whitelist).

```sh
# compile <program>.ts with pxt-microbit 9.1.1 into <program>.hex, as a
# project whose pxt.json has "dependencies": {"core": "*", "bluetooth": "*"}
python3 ../appimage.py <program>.hex v1 <program>.v1
sha256sum <program>.v1.bin    # compare with manifest.json
```

Both committed images were rebuilt this way through brickwright-lite's
`scripts/lib/pxt-node.mjs` (the pxt-microbit 9.1.1 worker, native compile)
and came out byte-identical to the hashes in `manifest.json`. Other routes to
the same compiler (the web editor at 9.1.1, `pxt build`) have not been
checked for byte identity.
`e2e_bond_uart.py --program NAME` refuses an image whose hash differs.

## Licences of the code in the images

The application region is compiled from:

- the program (`*.ts`, this repository, MIT), the PXT runtime and libraries
  (microsoft/pxt-microbit, pxt-common-packages: MIT);
- lancaster-university/microbit and microbit-dal v2.2.0-rc6 (MIT, Copyright
  (c) 2016 British Broadcasting Corporation, provided by Lancaster University);
- lancaster-university/mbed-classic, BLE_API and nrf51822 (Apache-2.0); the
  nrf51822 module's SoftDevice hex is NOT part of the application region;
- lancaster-university/nrf51-sdk v2.2.0+mb4: Nordic SDK sources under the
  3-clause BSD licence below (checked per file for the modules linked:
  device manager, pstorage, softdevice handler, app_error, DFU handler; none
  carries a Nordic-chip-only clause), the rest Apache-2.0;
- the GCC/newlib runtime (GCC Runtime Library Exception; newlib's permissive
  licences).

Nordic Semiconductor's licence for those SDK files, reproduced as its clause 2
requires for binary redistribution:

```
Copyright (c) Nordic Semiconductor ASA
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

  1. Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

  2. Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.

  3. Neither the name of Nordic Semiconductor ASA nor the names of other
  contributors to this software may be used to endorse or promote products
  derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
