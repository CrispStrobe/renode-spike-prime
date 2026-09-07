# Completed simulation work

- Added a deterministic snapshot adapter seam for public SPIKE model properties
  and a bounded power, IMU, and LPF2 command allowlist.

- Schema version 1, canonical fixtures, a bounded Python codec and queue,
  overflow gaps, command sequencing, and process tests establish the neutral
  Brickwright snapshot/control boundary.

- Repository provenance and source-only CI were established on pinned Renode
  1.16.1 and public MIT Infrastructure revisions.
- Generic STM32 DMA, SPI and UART behavior was corrected and covered by focused
  tests; protected Prime firmware reaches its daemon-ready boundary.
- Deterministic TLC5955, LSM6DS3TR-C and W25Q256-compatible models were added.
- Brick fidelity gained decoded Prime 5x5 display channels and explicit GSCLK
  phase, charger state transitions, bounded 12-bit DAC sample pacing, and IMU
  ODR-driven FIFO/interrupt scheduling. Hardware timer and ADC connections
  remain live roadmap work.
- A distinct SPIKE Essential platform, local hash-manifest image loaders and
  bounded official/Pybricks execution gates were added.
- A versioned unchanged-firmware matrix now covers seven Prime and Essential
  targets. It verifies every local artifact before machine creation, skips
  absent inputs explicitly, and declares target-specific vector, progress,
  symbol, device-initialization, and H4 boundaries. Public CI exercises only
  synthetic loader contracts; live scenario validation remains pending.
- A bounded transport-neutral Bluetooth controller now covers incremental H4,
  dual-mode HCI, ACL/L2CAP, ATT/GATT notifications, Classic signaling, SDP,
  RFCOMM and raw TCP/in-memory adapters in source-only tests.
- The transport-neutral `ILpf2Device` contract, byte-oriented
  UART adapter, type-62 ultrasonic sensor and type-48 medium motor cover exact
  discovery frames, checksums, mode/output traffic, encoder movement, load,
  stall, malformed input and parser recovery. The Essential wrapper wires
  UART5 to the motor and USART3 to the sensor through UART hubs.
- Bounded power-policy and PCM observers plus explicit
  IMU sampling, FIFO, watermark and interrupt behavior passed 12 focused tests.
  Source-only overlays expose verified Prime and Essential connections.
- An LP50xx register/color model and STM32 FMPI2C
  DMA requests cover the firmware-shaped initialization sequence, active-high
  PB13 enable/reset and defensive four-module RGB snapshots in eight tests.
- Steering documents separate pending gates, completed evidence, and normative
  contracts; CI rejects completion logs in the live roadmap and README repeats.
- Essential LPF2 ports gained source-mapped logical attachment indicators for
  PC1/PC0 and PA5/PA4. Attach settling, negotiation timeout, reconnect, motor
  integration, and sensor reporting advance only through explicit emulated
  microseconds. Topology generations and bounded transmit/parser state make
  disconnect and malformed-input recovery observable and deterministic. Large
  time jumps cap emitted reports and expose the coalesced count; zero cadences
  are rejected.
- An opt-in, loopback-only-by-default TCP service now binds explicit
  `monitor.Machine` and external model paths to Renode's master virtual clock.
  Bounded clients, lines, reads, queues, timeouts, command dispatch, and a
  fragmented-stream/reconnect test close the concrete transport seam without
  exposing arbitrary monitor commands. Model access is guarded by Renode's
  paused-state API, and scenarios can request snapshots at deterministic
  virtual-time milestones.
- Deterministic source-only fault gates run 256 seeded malformed-H4 recoveries,
  512 Bluetooth connect/disconnect/reset cycles, and 256 LPF2, power, charger,
  stalled-motor, and denied-flash-write reset cycles. Protocol byte queues and
  reports have explicit ceilings; large advances use emulated microseconds.

Commit history and CI retain detailed evidence.

- Audited the product forks against Renode `ab721d88` and Infrastructure
  `066a7f13c`. Current upstream is too far ahead for a reviewable product-branch
  rebase, so generic work was replayed without rewriting product history.
- Published current-upstream review branches for the clean DMA completion patch
  and separate TLC5955, LSM6DS3TR-C, generic NOR/W25Q256, and LP50xx commits.
  The LP50xx model was separated from its STM32F7 I2C DMA change. Replay diffs
  pass whitespace validation; native validation remains an explicit roadmap
  gate because the standalone checkout found an incompatible legacy dependency.
