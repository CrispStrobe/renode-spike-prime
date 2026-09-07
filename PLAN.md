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
5. Complete deterministic brick devices.
   Acceptance: buttons, display/LED snapshots, battery/power/charger state,
   bounded audio capture and timed IMU/FIFO/interrupt behavior have focused
   tests and source-cited Prime/Essential wiring.
6. Run unchanged firmware scenarios.
   Acceptance: locally supplied LEGO v2, LEGO v3, Pybricks, spike-nx and
   Brickwright images cross target-specific boot milestones and exercise motor,
   sensor, display and Bluetooth traffic; absent images skip explicitly.
7. Export one versioned, transport-neutral brick snapshot/control contract.
   Acceptance: Brickwright consumes the same port, motor, sensor, display,
   button, battery and IMU state used by Renode tests, with generation IDs and
   bounded malformed-input handling.
8. Add deterministic fault, resource and soak gates.
   Acceptance: reset, disconnect, corrupt frames, exhausted buffers, stalled
   motors, low battery, storage failures and repeated boot/connect cycles pass
   without wall-clock-dependent assertions or unbounded growth.
9. Rebase generic Renode changes and split upstream submissions.
   Acceptance: current upstream builds and DMA, SPI, UART and device changes are
   independently reviewable with no LEGO or TI binary dependency.
