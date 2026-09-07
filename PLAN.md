# Pending simulation work

Complete these tasks in order. All committed code and fixtures must be
MIT-compatible and source-only; proprietary firmware remains a local input.

1. Add the Essential FMPI2C1/LP50xx LED path.
   Acceptance: register-level tests and a parsed board integration gate.
2. Exercise both LPF2 ports with unchanged locally supplied Essential firmware.
   Acceptance: the guest completes discovery, selects modes, reads distance,
   commands the motor and observes a changing encoder without firmware patches.
3. Model LPF2 electrical attachment and deterministic scheduling.
   Acceptance: attach/detach GPIO transitions, reconnect, timeout and reporting
   cadence are covered without wall-clock-dependent tests.
4. Expand the lawful device catalog and fault cases.
   Acceptance: each device has a cited type/mode contract, exact wire fixtures,
   bounded parsers and deterministic disconnect/stall/corruption tests.
5. Rebase generic Renode changes and split upstream submissions.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable with no LEGO or TI binary dependency.
