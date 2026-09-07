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
   Acceptance: Prime ADC button ladders connect to the STM32 ADC; TLC5955 GSCLK
   connects to TIM12; DAC sample pacing connects to TIM6/DMA. Each connection
   must have source-cited wiring, emulated-clock behavior, and bounded tests.
4. Add deterministic fault, resource and soak gates.
   Depends on: task 3, the unchanged-firmware scenario contract, and the
   completed neutral state contract.
   Acceptance: add model-supported storage fault injection; run repeated boot
   cycles for each locally available hash-verified image; enforce a measured
   process-memory ceiling around full-machine runs. Keep fixed emulated-time
   budgets and reproducible seeds. Synthetic protocol and peripheral soak
   coverage is complete and recorded in `HISTORY.md`.
5. Rebase generic Renode changes and split upstream submissions.
   Depends on: stable focused tests for each generic change.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable; each patch has a focused regression test and no
   LEGO firmware, TI binary, or Brickwright-specific interface dependency.
