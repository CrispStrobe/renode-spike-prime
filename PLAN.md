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
2. Add only source-cited LPF2 devices.
   Depends on: the bounded UART endpoint contract.
   Acceptance: color, force, and large-motor models are added only where a
   public MIT-compatible source identifies type IDs, modes, units, widths, and
   command bytes. Exact fixtures cover discovery, data, output, disconnect,
   stall, truncation, checksum failure, queue exhaustion, and recovery.
3. Complete deterministic brick fidelity gaps.
   Depends on: existing brick-device overlays.
   Acceptance: Prime ADC button ladders, decoded 5x5 display state, LED phase,
   charger transitions, DAC sample width/pacing, and IMU ODR/FIFO interrupts
   have source-cited wiring, emulated-clock behavior, and bounded tests.
4. Add deterministic fault, resource and soak gates.
   Depends on: task 3, the unchanged-firmware scenario contract, and the
   completed neutral state contract.
   Acceptance: reset, disconnect, corrupt frames, exhausted buffers, stalled
   motors, low battery, storage failures and repeated boot/connect cycles pass
   with fixed emulated-time budgets, bounded queues, stable memory ceilings,
   reproducible seeds, and no wall-clock-dependent assertions.
5. Rebase generic Renode changes and split upstream submissions.
   Depends on: stable focused tests for each generic change.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable; each patch has a focused regression test and no
   LEGO firmware, TI binary, or Brickwright-specific interface dependency.
