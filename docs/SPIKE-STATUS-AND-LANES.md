# SPIKE Runtime state and actionable lanes

Recorded 2026-10-05. This guide owns Runtime adapters, public source support
packages and real guest qualification. Refresh main and the consumer pins before
starting. [Brickwright's cross-repository handover](https://github.com/CrispStrobe/brickwright-lite/blob/1127285873b03ff6540809c15e627b946412f0c9/docs/SPIKE-STATUS-AND-LANES.md)
and [firmware L01–L13](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/docs/project/next-steps.md)
identify the frontend and firmware owners. Tasks below are proposed, not claimed.

## Established state

- Renode executes the small ARM simulation guest, source-built protected NuttX
  kernel/userspace and a separately supplied upstream MicroPython application.
  They are distinct program runners. The bounded state/input/UART adapters feed
  one existing Brickwright hub and arena; the native guest owns motor evolution.
- [PR #50](https://github.com/CrispStrobe/renode-spike-prime/pull/50), main
  `72a1c8a82681efdc035af71b0397a0cff40cdb1c`, provides bounded `bwspike`/`bwhub`
  APIs for the upstream MicroPython route. Read the exact
  [support contract](spike-micropython-support.md): motor feedback is synchronous,
  selected sensor identities/topologies are supported, and raw/model hub I/O is
  not a physical calibration or complete LEGO module implementation.
- Source-only support assembly contains model/adaptor sources and a synthetic
  boot seed, not an application image. Image admission validates geometry and
  integrity, not authenticity. Desktop images are operator-selected inputs.
- Firmware's newer matrix consumes Runtime candidate
  `756b684eee56ba698a931a14b3f4885cb8d8ada6`. That is distinct from Runtime main
  above. MicroPython staging also validates a specific model source closure;
  a repository head, submodule and staged manifest must not be interchanged.
- ADC/DMA request suppression/rearm and receive callback regressions are covered
  within the declared synchronous model. Full FIFO/channel mux, interruption
  status, remapping and asynchronous hardware timing remain outside that claim.
- Unchanged-image gates establish only their named loader/execution milestones.
  No complete stock LEGO boot, modern IMU wire mapping or Code-tab upload is
  established. Public CI uses synthetic inputs, never restricted application images.

## Electrical detach candidate — 2026-10-07

This review branch explicitly consumes Infrastructure
`adf40d980` from [model PR #35](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/35).
Its [attachment contract](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/adf40d980/docs/SPIKE-ELECTRICAL-ATTACHMENT.md)
resolves stale detached inputs and exposes bridge demand even without a device.
The synthetic idle policy does not establish physical unplug behavior.

The canonical model workflow now includes the new attachment fixture and the
complete managed peripheral suite, retaining the native translator/full Runtime
build and existing board/guest regressions. Source-compiled model controls and
one real own-firmware detach/reconnect sequence already passed separately; they
are not results for this newly pinned Runtime build. Canonical-consumer guest
qualification and firmware's independent mandatory gates remain required before
adoption. The offline MicroPython support source-closure reference advances explicitly
with the Infrastructure gitlink; generated manifests still hash every staged
member. This candidate support package requires fresh MicroPython guest/consumer
qualification before adoption. Firmware and desktop package pins are unchanged
by this review branch.

## Execution rules

Read `README.md`, `HISTORY.md`, the relevant route contract and
`.github/workflows/model-tests.yml` before editing. Write observable bounds,
clock/sequence rules, cancellation and ownership first. Keep state DTOs closed;
never expose firmware bytes or editor-provided native paths. Preserve dependency
notices and upstream model ownership. Land model changes in the model fork first,
then consume exact reviewed revisions. Do not replace guest functions, patch
reference bytes or invent healthy persisted reference media.

Completion requires a failing regression on the previous behavior, relevant
host/model tests and actual guest evidence where advertised. A package assembly
unit test is not proof that a CPU ran a robot program. Record tested source,
model closure and consumer qualification separately. Public records contain public
source/evidence only; operational inputs and raw transcripts stay outside them.

## R01 — Couple measured Classic jobs to real guest encoder feedback

**Start:** `tests/firmware/nuttx-six-motor-fixture.py`,
`tools/check_prime_nuttx.py`, `docs/prime-nuttx-qualification.md`; coordinate firmware L01.

Add a bounded real guest scenario using firmware command handling, PWM/UART
models and observed encoder displacement. Cover signed targets, concurrent
ports, cancellation/disconnect, stale ownership, attachment loss and replacement.
Preserve the existing six-motor regression. **Done:** displacement and owned end
actuation establish completion, failures are explicit, old jobs cannot stop new
owners, and the current firmware's actual guest passes. Doable now; firmware
controller changes belong to its lane, not a Runtime imitation.

## R02 — Extend capability-aware robot and hub APIs

**Start:** `tools/micropython/bwspike.py`, `bwhub.py`, `_bwlpf2.py`,
`tests/tools/bwspike_readers_test.py`, `bwspike_control_test.py`,
`bwhub_api_test.py`, and `docs/platforms/lpf2-device-catalog.md`.

Choose one documented identity/mode or hub operation. Specify port identity,
attachment generation, freshness, units, bounds and unsupported errors. Preserve
single-thread feedback limits until scheduling is deliberately redesigned.
Coordinate arbitrary-port sensors and motor ownership with firmware L02/L05/L06;
do not claim their APIs are identical. **Done:** host boundary/failure fixtures
and actual upstream MicroPython guest observations pass, and unsupported devices
cannot be actuated or return stale sensor data. API contract work is doable now;
new identities require public device evidence and model implementation first.

## R03 — Close cold-process persistence and recovery evidence

**Start:** `tests/firmware/nuttx-storage-fixture.py`,
`tools/spike_nuttx_mailbox.py`, `tools/spike-arena-mailbox.py`,
`tests/tools/spike_flash_checkpoint_test.py`; coordinate firmware L03/L04.

Carry exact persistent media into a new owned emulator process; distinguish flash
from RAM/service caches. Exercise saved native/Python program restart and
calibration reload after completion, fault and interruption. Add corrupt/nonblank
media and failed-load preservation. Bluetooth bond reuse requires independent
matching peer keys, not cached same-process reconnection. **Done:** actual guest
cold-restart results and declared failure policy pass; host LittleFS crash cases
remain separately labeled. Doable now; no physical brownout claim.

## R04 — Bound sessions, fault recovery and resource use

**Start:** `tools/spike-state-bridge.py`, `tools/spike_state_socket.py`,
`tools/spike_program_uart.py`, `tools/spike-fault-resource-soak.py`,
`tests/tools/spike_fault_resource_soak_test.py`, `spike_state_server_clock_test.py`.

Test startup/Stop races, empty reads, generation changes, replacement ownership,
queue saturation, malformed input, process loss and reopen. Add bounded concurrent
motor/sensor/program/storage workloads; measure host and guest time and resource
high-water marks separately. A no-fault interval is not completed boot. **Done:**
admitted work terminates or fails explicitly, state/clock sequences remain valid,
cleanup touches only the owned session, and repeated recovery has bounded growth.
Doable now; long soak follows short deterministic failure regressions.

## R05 — Adopt models and advance unchanged-image milestones

**Start:** `tools/stage_prime_micropython.py`,
`tools/check_prime_micropython.py`, `tools/renode_check_prime_adc_dma.py`,
`tests/tools/stage_prime_micropython_test.py`,
`docs/platforms/unchanged-firmware-scenarios.md` and
[model tasks](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/5a519ce5d9b5122bcf2ecedcbfd6f49d2735bbeb/docs/SPIKE-STATUS-AND-LANES.md).

Take one publicly evidenced model correction; update submodule/source closure,
platform wiring and manifests together. Run native and staged board regressions
and affected guest routes. Diagnose bounded unchanged-image experiments with
passive public-register/CPU observations, keeping host console/resource faults
separate from guest faults. **Done:** exact consumed bytes and notices agree,
source/model checks pass and each claimed guest milestone has repeatable evidence.
Public fixtures are doable now; reference boot experiments need lawful separately
supplied inputs. Unknown IMU conversion stays unqualified.

## R06 — Qualify consumer refresh and installed route contracts

**Start:** `tools/stage_prime_micropython.py`, `docs/spike-micropython-support.md`,
`docs/spike-program-uart.md`; coordinate Lite G01/G02/G05 and firmware L09/L11.

Publish a route/version/module capability table and preserve its units and errors.
Verify staged support plus installed runtime identity, six-port topology, final
telemetry, cancellation and explicit startup refusal for missing/tampered inputs.
Refresh consumers only after their own installed GUI tests. **Done:** actual CPU
program observations, world motion and lifecycle match the declared contract;
new Runtime main is never silently credited to an older package. Linux work is
doable now; non-Unix packaging is separately environment-gated.

## Starting checks

### Compiled consumer qualification route

`tools/check_prime_nuttx.py --compiled-runtime` uses the supplied Runtime's
compiled peripheral types. It stages offline board data and the same aggregate
display clock, without generating or including `models.cs`. Keep the exact
Runtime build identity with the private invocation; copied notices alone do not
authenticate that binary. Add `--all-motors-test` for the existing six-port
native/Python scenario, or `--storage-test` for fresh-process persistence. The
default remains the separately labeled source-staged qualification route.

Restaging a packaged MicroPython support profile now replaces requested storage
SPI2 properties instead of duplicating them. Twenty local image/profile checks
cover repeat staging, independent clock/capacity overrides and duplicate-property
rejection. A supplied upstream MicroPython 1.26.1 application passed the repaired
source-staged raw-REPL execution/error/cancellation/recovery, GPIO motor/load/
cleanup and fresh-process filesystem checks. The preceding duplicate-property
startup failure is preserved privately. This does not qualify full SDK behavior,
installed GUI adoption or the new compiled Runtime consumer.

From this repository root, with the prescribed dependencies:

```sh
python3 tests/tools/stage_prime_micropython_test.py
python3 tests/tools/bwspike_api_test.py
python3 tests/tools/bwspike_control_test.py
python3 tests/tools/bwspike_readers_test.py
python3 tests/tools/bwhub_api_test.py
python3 tests/tools/spike_program_uart_test.py
```

Use the exact model/build/guest commands in `.github/workflows/model-tests.yml`
and the linked qualification guides for affected source changes. Documentation
changes do not require re-running ARM builds. LabWired does not currently replace
Renode's qualified SPIKE device integration. Physical transport, radio/electrical
behavior and hardware flashing/release remain separate operator-qualified work.

## LPF2 DATA budget qualification candidate

The [DATA budget qualification record](LPF2-DATA-BUDGET-QUALIFICATION.md) tracks
an explicit Infrastructure candidate pin, full model suites and compiled mutation
controls for exact external UART bursts. Compiled results and own-firmware
consumer regressions remain pending; firmware/desktop pins remain unchanged.


## Addressed-distance live discovery candidate — 2026-10-09

Owner: Codex SPIKE integration, branch
`feat/addressed-sensor-live-capability-20261009`, base
`df69192de7a84f56cced783b913fd2b7bb15d9d0`. Scope: NuttX mailbox discovery,
monitor configuration validation and snapshot capability publication, their
focused controls, model-workflow registration and this record. No model gitlink,
firmware, package pin, native program interpreter or sensor topology is changed.

The optional `addressedSensorCapability` configuration object must contain
exactly `abi`, `address`, `userspaceSha256`: integer version1, an aligned
userspace flash address and lowercase SHA256 equal to the manifest-bound image
identity. Present malformed/foreign metadata is rejected before marker access.
Only own Prime NuttX/transport-none configurations with a program mailbox and
verified image may declare it. Absent metadata keeps legacy behavior.

`nuttx-addressed-distance/v1` is published only after observing an initialized
version1 program mailbox, a nonzero even publication and a live marker value1.
Unready workers and unsupported live values do not advertise it. The operation
is read-only and runs inside the existing state snapshot; it does not change
simulated time, issue a program or assert any attached sensor type. Reading
errors propagate. Configuration and marker validation do not authenticate an
arbitrary firmware image; use the existing own-source manifest/admission gates.

Host controls exercise the actual snapshot function, old packages, bad hashes,
closed metadata, mailbox/worker readiness and live marker refusals. Three actual
Python source mutants for image binding, live marker and readiness must fail
named assertions, never import/setup errors. These are adapter controls, not
actual guest qualification. The candidate requires hosted Runtime checks and a
new clean firmware matrix using its exact Runtime source before adoption.

Next separately declare E/F ultrasonic topology and connect native chooser,
shared hub/arena inputs and returned device observations. Consumers must require
both this API capability and the declared topology before emitting addressed
native/Python calls. Existing default D-distance/E-force and six-motor routes
retain their contracts. No arbitrary A–F, physical accuracy, stock firmware or
installed GUI equivalence is claimed.
