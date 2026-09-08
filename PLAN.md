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
