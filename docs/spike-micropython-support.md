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
`8be722f931a5d0b82a2b866478e25efc3232df2f` in
[the model repository](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/tree/8be722f931a5d0b82a2b866478e25efc3232df2f).
The assembler checks the bytes of every consumed model and its MIT license
against that commit, and refuses modified inputs before creating output. It
never fetches, resets a checkout or overwrites an existing package. Keep the
assembler and pinned submodule from the same reviewed repository revision.

This revision retains SPI address-mode and ADC EOC ordering corrections plus
SYSCFG bank routing/reset support. It corrects ADC DDS=0 handling: requests
start when DMA is enabled, stop after the programmed DMA buffer completes,
and resume only after the ADC DMA bit is toggled off and on (or ADC reset).
Re-enabling the DMA stream alone does not rearm the ADC. DDS=1 circular
transfers continue across buffer completions.

Compared with the preceding restart-qualified 20-file source closure, only
`STM32DMA.cs` changes; the other 19 inputs, including the MIT license, remain
byte-identical. Existing Antmicro notices remain with scoped modification
credits. The source closure remains 20 files and the output manifest 16 files.

The common F4 platform pairs ADC1's DMA2 stream0 request with a separate model
completion notification (`TransferComplete0` to ADC input16). This is not a
physical GPIO or a TCIE/NVIC interrupt. The ADC accepts acknowledgement only
while its own request is being serviced by the synchronous DMA model; a reused
stream completing for another producer cannot suppress it. Synthetic fixtures
cover EOCS selection, IRQ masking, terminal suppression/rearm, circular buffers,
stream reuse, reset/abort acknowledgement and synchronous IRQ rearm. The
DDS=0/circular combination is tested only as the model's buffer-boundary
interpretation; [ST's LL header](https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Inc/stm32f4xx_ll_adc.h#L2638)
recommends limited requests with noncircular DMA and unlimited requests with
circular DMA. Actual native and staged board checks also exercise the connected
terminal path.

A real DMA stream EN 0→1 transition restarts working pointers at the programmed
PAR/M0AR bases and reloads the last software-programmed NDTR. EN 1→1 writes
preserve progress. To resume a partial transfer, software must adjust the bases
and explicitly write the residual count before enabling. This follows
[RM0430 §9.3.15 and §9.5.6–8](https://www.st.com/resource/en/reference_manual/rm0430-stm32f413423-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
and [ST AN4031's transfer-resume procedure](https://www.st.com/resource/en/application_note/dm00046011.pdf).
The bare-restart count reload is a document-based interpretation, not a physical
measurement. The native and staged board fixture restarts a partial ADC/DMA
buffer at a new base and checks data, guards and terminal acknowledgements.

Receive-request pulses arriving inside a synchronous copy callback are retained
until the copy returns, including a pulse for a descriptor rearmed in that
callback. A real manual-disable edge discards an ended pulse queued by the
old descriptor, while retaining readiness if the request line is still high. Falling edges at rest still
cancel readiness; a held request asserted while disabled remains available on
enable. Automatic buffer completion retains the existing transmit-readiness
behavior. The model stores one pending-readiness bit, not a counted request FIFO.
Synthetic source-read fixtures check matched 8/16/32-bit widths, old/new source
read counts, copied data, guards, reset/disable cancellation and completion
pulses. These callback semantics do not establish physical handshake timing.

These checks do not establish reference firmware boot or asynchronous hardware
timing. SYSCFG memory remapping, native battery/temperature samples, ADC overrun
and full DMA channel-mux/double-buffer/FIFO/error behavior remain outside this
qualification. Software-interruption TCIF behavior and FIFO draining also remain
unmodeled; a successful-buffer acknowledgement is distinct from that status.
The earlier acknowledgement-only recovery tests retain their fixed-address
destination; new restart fixtures cover incrementing pointers.

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
seed now supplies the BSD `bwspike` motor/sensor module described below. Original LEGO firmware, USB bootloader entry, BLE
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
| `Motor(port)` | Select A–F; construction does not actuate or probe. A/B are default drive motors. C–F must pass motor discovery before actuation; the default sensor topology rejects them. |
| `motor.dc(power)` | Integer power percentage, -100 through 100; positive and negative select opposite drive directions. Returns immediately. Zero coasts. |
| `motor.brake()` | Remove drive and request electrical braking; returns immediately. |
| `motor.coast()` | Remove drive and request coasting; returns immediately. |
| `motor.run_for(power, milliseconds)` | Apply power, wait, then brake in `finally`, including on Ctrl-C. Validate both arguments before actuation. |
| `wait(milliseconds)` | Firmware wait for integer milliseconds from 0 through 2147483647; interruptible. |
| `stop_all()` | Brake A/B and every auxiliary port positively verified as a motor by this module, including other instances. Does not probe unused sensor ports. |

Booleans, floating-point values, wrong types and values outside these ranges
raise `ValueError` before a command writes registers. Methods return `None`.
Multiple instances for one port share its physical output; the last command
wins. A/B share TIM1, C/D share TIM4 and E/F share TIM3. Each timer is initialized once per module import; commands preserve
the other port's GPIO and compare settings. Programs must not independently
reconfigure those timers while using this module.

Power is not a speed target. Acceleration, braking/coasting, load and stall
behavior come from the existing retained electrical/mechanical model and its
shared arena observations. The feedback methods below add bounded speed and
position control. The opt-in six-motor topology replaces C–F sensors with motors; default sensor constructors then fail with a device-type error. Robot-level `hub`/`motor` compatibility is not claimed. `run_for` completion means that braking
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

## Read devices through the emulated CPU UARTs

The seed also contains `_bwlpf2.py`, a bounded reader for the default modeled
attachments. `bwspike` uses it lazily, so selecting or driving a motor does not
open its UART. The reader configures the port UART, checks the discovery device
type and frame checksum, acknowledges discovery, selects a mode and reads its
data frame. It does not access native-host or frontend telemetry.

| Operation | Output and units |
| --- | --- |
| `Motor('A').angle()`, `Motor('B').angle()` | Signed 32-bit encoder degrees. Does not reset the encoder. |
| `motor.speed_percent()` | Signed integer speed percentage from -100 through 100, observed rather than commanded. |
| `ColorSensor('C').color_id()` | Model color ID, 0 through 255; 255 means unknown. No color-name mapping is promised. |
| `color.reflection()`, `color.ambient()` | Integer percentages from 0 through 100. |
| `DistanceSensor('D').distance()` | Integer millimeters, 0 through 65534; `None` for the model's no-distance sentinel. |
| `ForceSensor('E').force()` | Integer force percentage from 0 through 100, not Newtons. |
| `force.pressed()` | Boolean. |

Sensor constructors default to C, D and E respectively and reject other ports
before configuring anything. Construction does not open a UART. For example:

```python
from bwspike import Motor, ColorSensor, DistanceSensor, ForceSensor

print(Motor('A').angle())
print(ColorSensor().reflection())
print(DistanceSensor().distance())
print(ForceSensor().pressed())
```

Reads are synchronous and interruptible. Each read has a 1000 ms firmware-time
budget across discovery, writes and reply parsing; wraparound-safe tick checks
apply while waiting or consuming bytes. Bounds also limit frame payloads to
33 bytes, discovery/reply scans to 128 frames and queued-byte draining to 1024
bytes. Missing/wrong attachments, corrupt checksums, UART errors, invalid value
ranges and exhausted limits raise `OSError`; `KeyboardInterrupt` propagates and
releases the reader's busy flag. GUI execution deadlines still apply.

One interpreter serializes calls, with one reader shared per port. Queued old
reports are discarded before requesting a mode report; values are not cached
between calls. These are independently sampled readings, not an atomic snapshot
across devices. A report that arrives during a read can reflect a different
simulation instant from the next reading. Other code must not reconfigure these
UARTs while readers are in use. This is a qualified default-topology reader,
not a general hardware/hotplug driver; restart the session after a discovery
failure or topology change. Motor power/braking continue through the same GPIO
model while its encoder UART is open.

Run `python3 tests/tools/bwspike_readers_test.py` for synthetic protocol/value
coverage: discovery metadata, checksums, lengths, wrong devices, stale queued
reports, mode changes, timeouts/tick wrap, interruption, limits, integer
boundaries and sensor sentinels. Qualification still uses locally supplied
firmware; no upstream firmware or runtime bytes are included in public source.

Coordinator live qualification ran these readers inside the separately supplied
MicroPython application through the production native/frontend session. Exact
sensor values matched three synthetic arena-input sets, including percentages
at 0/100, unknown color, no distance, zero distance and both pressed states.
Changing inputs between reads changed the returned values without reopening
ports. Moving A/B encoders had the expected signs and speed percentages; after
braking, reported encoder positions matched shared motor positions within one
degree and stopped speed was below one degree/second. This compares independently
sampled protocol results with existing model observations, not physical sensors.
The 14 synthetic reader tests detect mutations that disable checksum verification
or decode negative encoders as unsigned. Detailed fixtures, commands, observations
and raw coordinator transcript are preserved privately. No new implementation
independence claim follows from this integration.

## Synchronous motor feedback control

`Motor('A')` and `Motor('B')` also expose these methods:

| Operation | Contract |
| --- | --- |
| `motor.run_speed(target_percent, milliseconds)` | Track a signed integer speed percentage from -100 through 100 for a firmware-time duration, then brake and wait for observed speed percentage to become zero. Returns `None`. |
| `motor.run_to(angle, speed_limit=30, timeout_ms=10000)` | Move to signed 32-bit absolute encoder degrees; return the observed integer angle within two degrees of the target after braking. Speed limit is an integer percentage from 1 through 100. |

Durations are integers from 0 through 2147483647 ms; position timeouts are
integers from 1 through 2147483647 ms. Invalid values and booleans fail before
actuation or UART configuration. Zero speed requests braking for the duration;
zero duration requests braking without a powered interval. The requested speed
ramps at up to 200 percentage points/second. Updates sleep for 20 ms plus UART
work, with elapsed firmware time used for feedback. These methods require the
encoder/speed reader contract and updated support/native build pins.

Use these blocking methods from one program thread. A control owns its selected
port until completion/failure; another control for that port raises `OSError`
without modifying it. Other ports retain their existing outputs. Do not issue
other commands or reconfigure the selected port while a control owns it.
The control duration/deadline begins after initial encoder acquisition, so
module loading and discovery add startup time. Braking adds completion time.
The position deadline is checked between samples and after settling; a UART
read retains its own 1000 ms budget. These are cooperative deadlines, not exact
instruction-time cutoffs.

Both methods request braking on failure or `KeyboardInterrupt` and release
ownership. No two-degree encoder progress for 500 ms while requesting motion
raises `OSError` with a progress/stall message. This detects lack of measurable
progress, not the model's internal stall flag; very slow motion can trigger it.
Position deadline and braking deadline failures also raise `OSError`. Braking
waits at most 1000 ms between bounded reader calls for speed percentage zero;
that quantized observation can include a small residual velocity. Position
completion checks encoder degrees again after braking, retrying an overshoot
until the deadline. It does not maintain active position hold afterward.
Timed speed completion means that the requested control interval ended;
an unreachable moving speed target is not guaranteed to be achieved.

```python
from bwspike import Motor

motor = Motor('A')
motor.run_speed(40, 1500)
print(motor.run_to(180, speed_limit=30, timeout_ms=10000))
```

`python3 tests/tools/bwspike_control_test.py` uses a separate synthetic
first-order plant to check loaded tracking in both directions, absolute moves,
validation, deadlines, interruption, ownership, concurrent B output and tick
wrap. Live MicroPython qualification tracked a 40% request at 38–39% under 25%
modeled load in the tested steady window (tolerance: three percentage points).
Moves to 180/-90 degrees completed at 182/-88 (tolerance: two encoder degrees).
Full load triggered the progress guard; Ctrl-C braked A while B kept running.
Disabling feedback or ownership cleanup makes the comparisons fail. This is
qualified simulation behavior, not physical calibration or complete equivalence.

The assembler compacts only our authored Python modules to fit the synthetic
filesystem. It keeps each contiguous leading comment header, including BSD
SPDX/copyright and retained mapping attribution, removes other comments/docstrings,
uses shorter indentation and verifies the executable AST is unchanged. Readable
sources remain public; staged docstrings are intentionally absent. This uses
standard Python 3.9+ tooling, with no firmware/compiler download. Qualification
used Python 3.13.11; Python formatter versions can produce different package
bytes, so retain the generated manifest/pins for each configured build. The
compacted modules were exercised inside the actual MicroPython application.

## Optional six-motor MicroPython profile

A native launch requests `backend: "micropython", topology: "six-motors"`.
The same board attaches motors on all A–F ports before boot. The state service
advertises `micropython-six-motors/v1` only with six observed motor attachments
and a ready program UART whose generation matches the launch configuration.
Default A/B plus sensor launches remain available. Reassemble the support seed
and regenerate desktop pins to use this profile.

GPIO/PWM directions, per-timer isolation and F's bridge across two GPIO banks
are covered by `bwspike_api_test.py`; F encoder reads use UART9. UART readers
request fresh reports and discard at most 16384 stale bytes within the existing
one-second read deadline. A larger backlog raises an explicit error, rather
than returning stale encoder data. The synthetic reader tests include an idle
motor's queued reports, a fresh sample, malformed frames and both drain bounds.
Feedback commands remain synchronous and require one program thread; power
commands can keep other motors running while one motor executes feedback.
A/B drive the shared arena rover; C–F publish auxiliary motor telemetry and
accept load inputs. Six mode has no mounted arena sensors.

## Recovering from an incorrect reader type

A port reader now records the type in the checksum-verified device announcement,
not the type requested by the program. A wrong request raises
`OSError("LPF2 attachment type mismatch")` before discovery acknowledgment or
motor GPIO/PWM writes. The verified announcement remains available: a later
correct reader on that same port continues discovery and requests fresh data,
without rebooting the interpreter or reopening its UART. Repeated wrong requests
also fail explicitly; they do not consume the pending discovery stream. A wrong
request after successful discovery leaves the working reader intact.

All reader types for a port share one busy guard and the existing one-second
read deadline, frame/checksum/length bounds and bounded stale-report drain.
Conflicting device types in a discovery stream fail explicitly. This supports
recovery from an incorrect reader request on a fixed topology; changing physical
attachments, corrupt-stream resynchronization and general hotplug remain outside
the qualified contract. Reassemble support and regenerate native package pins
before rebuilding the desktop to obtain the updated seed.

Run `python3 tests/tools/bwspike_readers_test.py` for synthetic recovery in both
directions, repeated wrong requests, conflicts, timeout, interruption and
shared-port exclusion. The SDK remains coordinator-authored BSD integration;
no new independent implementation or physical calibration claim is made.

## Hub interfaces inside MicroPython

The seed also supplies `bwhub`, a coordinator-authored BSD integration of the
retained MIT board/model interfaces. Reassemble support and regenerate desktop
pins before use. This adds no implementation-independence or physical-accuracy
claim. It provides a bounded Brickwright simulation API.

```python
from bwhub import Display, Buttons, IMU, Sound

panel = Display()
panel.show([65535 if i in (6, 8, 16, 17, 18) else 0 for i in range(25)])
print(Buttons().pressed())
print(IMU().acceleration_raw())
Sound().write_pcm8(bytes([0, 128, 255]))
panel.clear()
```

| Operation | Contract |
| --- | --- |
| `Display().show(pixels)` | List/tuple of exactly 25 integer grayscale values, 0..65535, row-major in the retained model's `Matrix` orientation. Writes a 97-byte SPI1 grayscale frame and pulses PA15 LAT. Clears all nonmatrix channels. |
| `display.clear()` | Latch all display channels to zero. |
| `Buttons().raw()` | Independently sampled ADC1 channel14/channel1 values as a tuple of integers 0..4095. |
| `buttons.pressed()` | Tuple of currently pressed names in center/left/right/bluetooth order. Decodes only the exact deterministic samples produced by `PrimeButtonLadder`; unknown analog levels raise `OSError`. |
| `IMU().acceleration_raw()` | Signed 16-bit X/Y/Z register samples as a tuple. |
| `imu.angular_rate_raw()` | Signed 16-bit X/Y/Z register samples as a tuple. |
| `imu.temperature_raw()` | Signed 16-bit temperature register sample. |
| `Sound().write_pcm8(samples)` | Immutable `bytes`, length 1..4096; writes their exact values to the retained byte-oriented PCM observation sink with PC10 enable asserted, then releases enable. No host audio playback or sample timing is promised. |

Constructors/imports perform no peripheral writes or discovery. Display/PCM
validation rejects booleans, floats and invalid values before any output write.
Output methods return `None`. Multiple instances share a peripheral; methods
reject an already busy resource without modifying it. Use one program thread;
this cooperative guard is not a thread synchronization primitive. Do not
independently configure SPI1/PA5/PA7/PA15, ADC1/PC4/PA1, I2C2 or PC10 while using
these APIs. GPIO updates preserve other pins, and these methods do not configure
motor timers/UARTs or the storage SPI2.

Display/button polling has a shared 1000 ms firmware-tick budget per call with
wraparound-safe checks and interruptible one-millisecond sleeps. Display commits
a frame only after all bytes have been transferred. An interrupted or timed-out
partial frame is not latched; the next full frame replaces it. LAT is released
and ownership is cleared in `finally`. Buttons turn ADC1 off in `finally`.
Each button ladder is read separately; this is not an atomic button snapshot.

IMU methods access the retained CPU-facing I2C2 registers directly at
`0x40005800`; they do not require a firmware `machine.I2C` module. Each call
resets/configures/enables only that controller, checks WHO_AM_I at address
`0x6a` for `0x6a`, and writes the sensor's register-auto-increment setting.
Register bytes use separate one-byte reads with ACK/POS clear: transmit the
register address, issue repeated START, select the read address, clear ADDR,
request STOP, then consume RXNE/DR. Signed 16-bit assembly preserves raw values.

All transaction waits share one 1000 ms firmware-time budget for the entire
method, with wraparound-safe checks, interruptible sleeps, and explicit I2C
status-error detection. Missing/wrong identity, rejected addresses and exhausted
budgets raise `OSError`; `KeyboardInterrupt` propagates. A `finally` block
requests STOP, resets/disables the controller and releases ownership on every
exit. These settings target the retained model's documented register contract;
no physical I2C timing or board-pin accuracy is qualified.

Reads return current register contents without waiting for a new data-ready
event. They clear the retained model's relevant data-ready flags as output high
bytes are read. No ODR setup, SI conversion, axis remapping, calibration, fusion,
heading or orientation is provided. A sample can change between individual byte
transactions; these APIs do not claim an atomic sensor snapshot.

PCM writes are bounded but immediate; interruption may leave an observed prefix,
with enable released in `finally`. This API does not use the sink's separate
12-bit DAC/TIM6 queued-sample interface and does not implement tones, volume or
asynchronous playback. Display latching exposes the model's grayscale channel
state; it does not configure or qualify TIM12 grayscale-clock timing, brightness
calibration or physical LED scanning.

The model interface facts are retained at the pinned public Infrastructure
revision in `Sensors/LSM6DS3TRC.cs`, `SPI/TLC5955.cs`,
`Analog/PrimeButtonLadder.cs` and `Sound/PCMAudioSink.cs`, together with this
repository's `platforms/boards/spike-prime-brick-devices.repl`. Their MIT notices
and existing attribution remain untouched. TLC5955 retains the matrix mapping
attribution to Copyright (c) 2019–2023 The Pybricks Authors. This integration
uses the licensed retained model contract and does not reproduce firmware
driver code.

Run `python3 tests/tools/bwhub_api_test.py` for synthetic full-frame mapping,
button combinations, signed sample boundaries, invalid inputs, timeouts across
tick wrap, I2C address/NACK handling, single-byte transaction ordering,
interruption/recovery and shared-resource cleanup. Packaging tests
recover all seed files through their FAT chains. To accommodate the added SDK
module, the authored seed uses a 128-entry root directory instead of 512 entries;
its 64 KiB prefix, volume size, 2 KiB clusters and 63-sector FAT are preserved.
The smaller root directory leaves 28 KiB for allocated file data. Old packages
remain valid but must be reassembled to gain `bwhub`. Actual MicroPython/Renode
execution requires separate coordinator qualification; synthetic tests alone
establish the SDK contract and packaging, not firmware equivalence.


Coordinator qualification on 2026-10-04 ran the SDK inside separately supplied
MicroPython 1.26.1 and 1.29.0 applications using the production native image
owner, raw-REPL transport and frontend arena session. The test pressed all four
buttons, supplied signed raw IMU samples including -32768 and 32767, latched 25
distinct display values and wrote six PCM bytes. Python returned the supplied
values; final observations confirmed the display channels, buttons, raw samples,
PCM byte count/last byte, zero drops and disabled speaker enable. This is the
stated deterministic model qualification, not physical hub equivalence.

The closed `prime-hub-io/v1` capability requires the complete retained fixed-path
model set and the owned ready UART generation. Optional arena `hub` inputs contain
four boolean buttons and signed raw temperature/gyro/acceleration samples.
Invalid payloads or unavailable models are rejected before peripheral mutation.
Legacy sensors/loads-only packets remain supported. Frontend/native consumers
validate the observation before changing the shared hub or world; no renderer
model paths or monitor commands are admitted. The UI maps 16-bit display values
to 0–9 brightness with rounding and retains the raw observation. IMU samples are
not converted into the arena's yaw/heading. PCM is observed without host playback.
Firmware images, raw observations and complete qualification transcripts remain
in the private evidence repository.
