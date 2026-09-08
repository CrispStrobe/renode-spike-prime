# Simulation roadmap

Execute the numbered tasks in dependency order. Each task is complete only
when every stated gate passes. Committed implementation, fixtures, and derived
data must be MIT-compatible and source-only. Proprietary firmware and
controller binaries are local inputs identified by SHA-256 and must never be
fetched, committed, logged, cached, or uploaded by public CI.

1. Complete source evidence for the remaining LPF2 devices.
   Depends on: the bounded UART endpoint contract.
   Acceptance: a pinned MIT/Apache/BSD-compatible primary source supplies the
   complete discovery bytes, units, widths, mappings, and output semantics for
   SPIKE color (type 61), force (type 63), and Large Motor (type 49). Add each
   model only after its evidence is complete. See
   `docs/platforms/lpf2-device-catalog.md` for the missing facts.
2. Complete deterministic brick fidelity gaps.
   Depends on: existing brick-device overlays.
   Acceptance: Prime ADC button ladders connect to the STM32 ADC; TLC5955 GSCLK
   connects to TIM12; DAC sample pacing connects to TIM6/DMA. Each connection
   must have source-cited wiring, emulated-clock behavior, and bounded tests.
3. Add deterministic fault, resource and soak gates.
   Depends on: task 2, the unchanged-firmware scenario contract, and the
   completed neutral state contract.
   Acceptance: add model-supported storage fault injection; run repeated boot
   cycles for each locally available hash-verified image; enforce a measured
   process-memory ceiling around full-machine runs. Keep fixed emulated-time
   budgets and reproducible seeds. Synthetic protocol and peripheral soak
   coverage is complete and recorded in `HISTORY.md`.
4. Finish generic Renode replay validation.
   Depends on: the replay branches and manifest in
   `docs/upstream-review.md`, plus a fully initialized current Renode checkout.
   Acceptance: port the remaining UART, SPI-DMA, and STM32F7-I2C changes; build
   each independent topic on current upstream; run its focused fixture and the
   complete peripheral suite. Keep product history unchanged and do not open
   upstream pull requests automatically.
