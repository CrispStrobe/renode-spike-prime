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
`5d2d3a79ed1df755fc261194de0774960d2ae0d3` in
[the model repository](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/tree/5d2d3a79ed1df755fc261194de0774960d2ae0d3).
The assembler checks the bytes of every consumed model and its MIT license
against that commit, and refuses modified inputs before creating output. It
never fetches, resets a checkout or overwrites an existing package. Keep the
assembler and pinned submodule from the same reviewed repository revision.

This revision includes the native SPI flash fast-read address-mode correction:
`0x0B` follows `0xB7`/`0xE9`, while `0x0C` always takes four address bytes.
Compared with the preceding source reference, only `GenericSpiFlash.cs` changes
within the 19-file consumed closure; the other 18 inputs, including the MIT
license, remain byte-identical. The correction is qualified with synthetic
address-mode fixtures and does not establish any opaque application's opcode use.

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
The upstream application has no robot-level `hub`/`motor` modules. The assembled
seed now supplies the BSD `bwspike` drive-motor module described below. Original LEGO firmware, USB bootloader entry, BLE
program upload, full desktop dialog automation, non-Unix staging and portable
installed runtime discovery remain outside this qualification.

The assembler, adapters and synthetic seed are BSD-3-Clause, Brickwright
contributors. Retained model and platform notices stay intact; the package
includes the MIT and BSD license texts. The caller supplies the runtime and
firmware under their own applicable licenses.

## Drive motors inside MicroPython

The support assembler puts `bwspike.py` alongside `boot.py` in the synthetic
filesystem. Reassemble support and rebuild the desktop with its updated pins
to use it. The module runs in the emulated CPU, with firmware waits and GPIO/PWM
register writes; it does not move the arena directly or duplicate motor state.

In the Code tab, select Python and the desktop MicroPython image route:

```python
from bwspike import Motor, wait, stop_all

left = Motor('A')
right = Motor('B')
try:
    left.dc(-50)
    right.dc(50)
    wait(700)
finally:
    stop_all()
wait(200)
print('done')
```

The signs match the default arena's opposite wheel mounting. Other world/robot
configurations may need different signs. This API targets the qualified
simulation profile; it is not a supported hardware-flashing workflow.

| Operation | Contract |
| --- | --- |
| `Motor('A')`, `Motor('B')` | Select a default drive motor; construction does not actuate it. Other ports are refused. |
| `motor.dc(power)` | Integer power percentage, -100 through 100; positive and negative select opposite drive directions. Returns immediately. Zero coasts. |
| `motor.brake()` | Remove drive and request electrical braking; returns immediately. |
| `motor.coast()` | Remove drive and request coasting; returns immediately. |
| `motor.run_for(power, milliseconds)` | Apply power, wait, then brake in `finally`, including on Ctrl-C. Validate both arguments before actuation. |
| `wait(milliseconds)` | Firmware wait for integer milliseconds from 0 through 2147483647; interruptible. |
| `stop_all()` | Brake A and B, including motors selected by other instances. |

Booleans, floating-point values, wrong types and values outside these ranges
raise `ValueError` before a command writes registers. Methods return `None`.
Multiple instances for one port share its physical output; the last command
wins. A and B share TIM1, initialized once per module import; commands preserve
the other port's GPIO and compare settings. Programs must not independently
reconfigure that timer while using this module.

Power is not a speed target. Acceleration, braking/coasting, load and stall
behavior come from the existing retained electrical/mechanical model and its
shared arena observations. No encoder read, position control, sensor read,
closed-loop speed control, six-motor topology or robot-level `hub`/`motor`
compatibility is claimed by this module. `run_for` completion means that braking
has been requested, not that the motor has already reached zero speed.

Run `python3 tests/tools/bwspike_api_test.py` for validation, shared-port isolation,
stop semantics and interruption cleanup tests without firmware. Live execution
qualification uses a separately supplied local application; its firmware and
detailed results remain private.

Coordinator live qualification imported `bwspike` in MicroPython 1.26.1 through
the production native/frontend route. Concurrent A/B power drove the shared
arena robot about 17 cm, followed by braking and completion cleanup. A separate
live UART scenario interrupted A's `run_for` while B kept running, then observed
B coasting with substantial remaining speed and reaching zero after braking.
Stop assertions allow less than 1 degree/second; the coasting assertion requires
more than 100 degrees/second after the short wait. Disabling arena wheel
propagation makes the live movement assertion fail despite Python completion.
These test-specific tolerances distinguish the exposed actions; they do not
establish physical calibration or complete API equivalence.
