# Simulation roadmap

Execute the numbered tasks in dependency order. Each task is complete only
when every stated gate passes. Committed implementation, fixtures, and derived
data must be MIT-compatible and source-only. Proprietary firmware and
controller binaries are local inputs identified by SHA-256 and must never be
fetched, committed, logged, cached, or uploaded by public CI.

1. Validate the unchanged-firmware runner against Renode.
   Depends on: a complete local Renode build and hash-manifested images.
   Acceptance: Robot Framework parses with Renode's keyword library; dictionary
   access and hexadecimal monitor values work at runtime; each available image
   reaches only its catalogued milestones; two-ELF symbol lookup and the
   USART2/H4 path pass for Brickwright NuttX. Prime port traffic remains out of
   scope until a source-cited Prime LPF2 wiring overlay exists.
2. Model LPF2 attachment and scheduling.
   Depends on: existing UART endpoint contract.
   Acceptance: both Essential ports expose source-cited attachment GPIO state;
   attach, detach, reconnect, timeout, and report cadence use the emulated clock
   and pass deterministic focused tests.
3. Expand the lawful device catalog and fault cases.
   Depends on: task 2.
   Acceptance: each added device has a cited public type/mode contract, exact
   byte fixtures, bounded parser state, and deterministic disconnect, stall,
   truncation, checksum, and recovery tests.
4. Complete deterministic brick fidelity gaps.
   Depends on: existing brick-device overlays.
   Acceptance: Prime ADC button ladders, decoded 5x5 display state, LED phase,
   charger transitions, DAC sample width/pacing, and IMU ODR/FIFO interrupts
   have source-cited wiring, emulated-clock behavior, and bounded tests.
5. Export one versioned, transport-neutral brick snapshot/control contract.
   Depends on: stable observable states from tasks 2 and 4.
   Acceptance: Brickwright consumes the same port, motor, sensor, display,
   button, battery and IMU state used by Renode tests, with generation IDs and
   bounded malformed-input handling; schema compatibility and round-trip tests
   cover every field and reject unsupported versions.
6. Add deterministic fault, resource and soak gates.
   Depends on: the unchanged-firmware scenario contract and task 5.
   Acceptance: reset, disconnect, corrupt frames, exhausted buffers, stalled
   motors, low battery, storage failures and repeated boot/connect cycles pass
   with fixed emulated-time budgets, bounded queues, stable memory ceilings,
   reproducible seeds, and no wall-clock-dependent assertions.
7. Rebase generic Renode changes and split upstream submissions.
   Depends on: stable focused tests for each generic change.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable; each patch has a focused regression test and no
   LEGO firmware, TI binary, or Brickwright-specific interface dependency.
