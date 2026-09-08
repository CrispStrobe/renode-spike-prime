# Simulation roadmap

Execute the numbered tasks in dependency order. Each task is complete only
when every stated gate passes. Committed implementation, fixtures, and derived
data must be MIT-compatible and source-only. Proprietary firmware and
controller binaries are local inputs identified by SHA-256 and must never be
fetched, committed, logged, cached, or uploaded by public CI.

0. Close the Prime button registration regression.
   Acceptance: all four button controls are registered in the machine with
   stable names, drive the two ADC ladders, retain correct reset behavior, and
   pass a runtime platform assertion whose success cannot be inferred from
   echoed monitor input. CI must reject every monitor command error.
1. Complete source evidence for the remaining LPF2 devices.
   Depends on: the bounded UART endpoint contract.
   Acceptance: a pinned MIT/Apache/BSD-compatible primary source supplies the
   complete discovery bytes, units, widths, mappings, and output semantics for
   SPIKE color (type 61), force (type 63), and Large Motor (type 49). Add each
   model only after its evidence is complete. See
   `docs/platforms/lpf2-device-catalog.md` for the missing facts.
2. Add deterministic fault, resource and soak gates.
   Depends on: the unchanged-firmware scenario contract and the
   completed neutral state contract.
   Acceptance: add model-supported storage fault injection; run repeated boot
   cycles for each locally available hash-verified image; enforce a measured
   process-memory ceiling around full-machine runs. Keep fixed emulated-time
   budgets and reproducible seeds. Synthetic protocol and peripheral soak
   coverage is complete and recorded in `HISTORY.md`.
