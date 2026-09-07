# Simulation roadmap

Execute the numbered tasks in dependency order. Each task is complete only
when every stated gate passes. Committed implementation, fixtures, and derived
data must be MIT-compatible and source-only. Proprietary firmware and
controller binaries are local inputs identified by SHA-256 and must never be
fetched, committed, logged, cached, or uploaded by public CI.

1. Add only source-cited LPF2 devices.
   Depends on: the bounded UART endpoint contract.
   Acceptance: color, force, and large-motor models are added only where a
   public MIT-compatible source identifies type IDs, modes, units, widths, and
   command bytes. Exact fixtures cover discovery, data, output, disconnect,
   stall, truncation, checksum failure, queue exhaustion, and recovery.
2. Complete deterministic brick fidelity gaps.
   Depends on: existing brick-device overlays.
   Acceptance: Prime ADC button ladders, decoded 5x5 display state, LED phase,
   charger transitions, DAC sample width/pacing, and IMU ODR/FIFO interrupts
   have source-cited wiring, emulated-clock behavior, and bounded tests.
3. Run unchanged firmware scenarios.
   Depends on: tasks 1 and 2.
   Acceptance: locally supplied LEGO v2, LEGO v3, Pybricks, spike-nx and
   Brickwright images cross versioned target-specific milestones and exercise
   port, display, storage, and Bluetooth traffic without patches. Missing local
   images produce explicit skips; hash mismatches fail before execution.
4. Export one versioned, transport-neutral brick snapshot/control contract.
   Depends on: stable observable states from tasks 1 and 2.
   Acceptance: Brickwright consumes the same port, motor, sensor, display,
   button, battery and IMU state used by Renode tests, with generation IDs and
   bounded malformed-input handling; schema compatibility and round-trip tests
   cover every field and reject unsupported versions.
5. Add deterministic fault, resource and soak gates.
   Depends on: tasks 3 and 4.
   Acceptance: reset, disconnect, corrupt frames, exhausted buffers, stalled
   motors, low battery, storage failures and repeated boot/connect cycles pass
   with fixed emulated-time budgets, bounded queues, stable memory ceilings,
   reproducible seeds, and no wall-clock-dependent assertions.
6. Rebase generic Renode changes and split upstream submissions.
   Depends on: stable focused tests for each generic change.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable; each patch has a focused regression test and no
   LEGO firmware, TI binary, or Brickwright-specific interface dependency.
