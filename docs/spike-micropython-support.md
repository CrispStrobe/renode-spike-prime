# Build the native MicroPython support profile

The desktop MicroPython route runs a locally supplied application in Renode.
Brickwright's Code tab uploads Python through a bounded UART, and observed
motor positions feed the existing virtual hub and arena. The browser simulator
remains a separate route for Scratch/native programs.

The support package can now be assembled offline from public source. It contains
retained model sources, platform descriptions, the state/UART adapters and an
authored synthetic FAT16 boot seed. It contains no firmware application,
original LEGO backup, runtime executable, user program or qualification log.

From a checkout of this repository with its pinned Infrastructure submodule:

```sh
git submodule update --init src/Infrastructure
python3 tools/stage_prime_micropython.py \
  --infrastructure src/Infrastructure --output /absolute/new/support
python3 tests/tools/stage_prime_micropython_test.py
```

The consumed Infrastructure source closure must match public commit
`1291ba1e4ddfb0d58e6957df55a56daa2132bf13` in
[the model repository](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/tree/1291ba1e4ddfb0d58e6957df55a56daa2132bf13).
The assembler checks the bytes of every consumed model and its MIT license
against that commit, and refuses modified inputs before creating output. It
never fetches, resets a checkout or overwrites an existing package. Keep the
assembler and pinned submodule from the same reviewed repository revision.

From a Brickwright checkout, freeze the assembled support and a separately
installed, qualified Renode executable for a desktop build:

```sh
node scripts/prepare-spike-micropython-pins.mjs \
  /absolute/new/support /absolute/renode /absolute/new/pinned-support
```

Use the four `BW_RENODE_*` values in the generated `pins.json` as native build
environment variables. These are currently absolute paths; this is a configured
desktop build, not a relocatable runtime bundle. Preserve support files and the
installed runtime at those paths. A build without these pins refuses startup.
The native owner verifies the closed 16-file manifest again before launch.
Firmware is chosen separately through the native image picker; it is not sent
to the editor realm. Only canonical application entry at `0x08010000` is covered.

The application profile uses 100 MHz CPU/SysTick/timer inputs and a 50 MHz
storage SPI with one receive slot. TIM12 uses the retained aggregate display
clock subset. Core model aliases allow dynamic inclusion in the qualified
Renode 1.16.1 runtime. This profile does not alter the retained NuttX profile.

Coordinator qualification with a locally supplied MicroPython 1.26.1 application
passed the production native/frontend session, UART Python execution, shared
hub/arena motor propagation, sensor feedback, completion and ownership cleanup.
A synthetic GPIO/PWM program moved the arena robot about 14.4 cm. Disabling
wheel propagation made the movement assertion fail despite Python completion.
Raw transcripts, images, generated packages, commands and observations remain
in the private evidence repository. No new implementation-independence claim
is made for this integration.

This does not establish physical accuracy or complete firmware equivalence.
The tested application has no robot-level `hub`/`motor` modules; the movement
test uses `machine.mem32`. Original LEGO firmware, USB bootloader entry, BLE
program upload, full desktop dialog automation, non-Unix staging and portable
installed runtime discovery remain outside this qualification.

The assembler, adapters and synthetic seed are BSD-3-Clause, Brickwright
contributors. Retained model and platform notices stay intact; the package
includes the MIT and BSD license texts. The caller supplies the runtime and
firmware under their own applicable licenses.
