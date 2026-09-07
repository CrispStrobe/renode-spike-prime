# SPIKE Prime Renode extension plan

This public upstream-tracking fork starts at Renode `v1.16.1`
(`d66b0c2aa3d420408eccecfd1d3bab0fd702a6db`). Its infrastructure submodule
starts at the exact pinned commit used by that release
(`add012af003a0f620d3da52828262676f374d121`). Both codebases are MIT-licensed.

The objective is to model STM32F413 SPI and USART DMA behavior accurately
enough to execute unchanged SPIKE Prime firmware. Tests must exercise generic
STM32 behavior; SPIKE-specific firmware remains an ignored, private integration
input and is never uploaded as an artifact.

## R0 — Repository and provenance

- [x] R0.1 Create `CrispStrobe/renode-spike-prime` with `upstream`
  pointing to `renode/renode` and `main` pinned to Renode 1.16.1.
- [x] R0.2 Create public `CrispStrobe/renode-infrastructure-spike-prime` with
  `upstream` pointing to `renode/renode-infrastructure` and `main` pinned to
  the release's infrastructure commit.
- [x] R0.3 Isolate implementation on `feat/spike-prime-stm32-dma` and prohibit
  accidental pushes to either upstream remote.
- [x] R0.4 Add CI with immutable actions, read-only permissions, model
  unit tests, and no firmware artifacts.

## R1 — Reproduce and specify the controller gaps

- [x] R1.1 Add STM32DMA unit coverage for request-driven peripheral transfers,
  exact NDTR decrement, completion flags/IRQs, and circular reload.
- [x] R1.2 Add STM32SPI unit coverage for independent RX and TX DMA request
  signals and paired full-duplex transfer completion.
- [x] R1.3 Add STM32 UART coverage for RX DMA requests, IDLE flag/IRQ clearing,
  and sustained circular reception.

## R2 — Correct generic STM32 models

- [x] R2.1 Make peripheral DMA requests transfer only the configured data unit;
  never underflow NDTR or invent padding.
- [x] R2.2 Implement circular-mode reload of NDTR and memory position while
  preserving transfer-complete flags and interrupts.
- [x] R2.3 Expose and drive SPI TX DMA requests alongside RX requests, honoring
  CR2 enable bits and byte/word accesses.
- [x] R2.4 Verify UART DMA/IDLE behavior and correct it only where the generic
  model violates documented STM32 semantics.

## R3 — SPIKE integration gates

- [x] R3.1 Point the Brickwright SPIKE platform at the custom Renode build.
- [x] R3.2 Run the unchanged protected image through TLC5955 initialization to
  `nsh_main` and `btsensor_main` without board-function hooks.
- [x] R3.3 Connect USART2 RX to DMA1 stream 7 and run the opaque TI HCI command
  stream against the lawful external H4 responder through
  `physical_start_host` and `bt_enable` completion.
- [x] R3.4 Repeat bounded vector/progress gates for official LEGO v2/v3,
  original spike-nx, Brickwright firmware, and Pybricks.

## R4 — Upstream readiness

- [x] R4.1 Keep every model change MIT, generic, documented, and covered by
  tests that require no LEGO or TI material.
- [ ] R4.2 Rebase onto current upstream Renode and infrastructure after the
  pinned 1.16.1 behavior is proven.
- [ ] R4.3 Split reviewable upstream pull requests by DMA, SPI, and UART concern.

## R5 — Deterministic board peripherals

- [x] R5.1 Add an MIT-licensed TLC5955 serial/latch model. Keep SPI shifting
  independent from the external LAT signal, retain the complete 769-bit
  byte-oriented frame, and expose defensive snapshots for deterministic tests
  and UI adapters.
- [x] R5.2 Replace the integration-local IMU subset with a tested generic
  LSM6DS3TR-C register/I2C model. Model WHO_AM_I, immediate software reset,
  control-register persistence, IF_INC burst access, deterministic raw sample
  injection, and data-ready clearing after complete output reads.
- [x] R5.3 Verify and configure the generic NOR flash model for the W25Q256JV
  command subset used by the board: JEDEC/status reads, WEL, dedicated 4-byte
  fast read/program/4 KiB and 64 KiB erase, and chip erase. Keep operations
  deterministic and immediately complete, while exposing BUSY=0 and accurate
  WEL/NOR bit semantics. No device-specific model is required.

## R6 — SPIKE Essential simulation

- [x] R6.1 Add a distinct, source-cited Essential machine subset from pinned
  Pybricks commit `101c6babb592148bda9a8fd912b7953c7d561c0a`. Model the
  verified STM32F413 memory extension, I2C3 IMU, SPI2 W25Q32-class store and
  RX/TX DMA wiring; do not borrow Prime-only devices.
- [x] R6.2 Add ignored, hash-manifested local loaders and opt-in Robot gates
  for user-supplied official and Pybricks Essential images. Limit the initial
  claim to vector validity and bounded instruction progress.
- [ ] R6.3 Model or bridge the Essential-specific FMPI2C1/LP50xx LED path.
- [ ] R6.4 Add lawful external H4 controller response and two-port Powered Up
  device integration gates without bundling controller firmware.

## R7 — Transport-neutral Bluetooth controller

- [x] R7.1 Define a source-only MIT controller boundary independent of TCP,
  UART, Renode, and firmware images, with explicit H4/controller/L2CAP/protocol
  layers and unit-tested channel contracts.
- [x] R7.2 Implement incremental H4 command and ACL framing plus deterministic
  dual-mode HCI initialization, advertising, connection, and lifecycle events.
- [x] R7.3 Add minimal extensible BLE ATT/GATT and Classic L2CAP/RFCOMM peers,
  with byte-exact tests and no RF-fidelity claim.
- [x] R7.4 Provide TCP and in-memory adapters and source-only CI gates suitable
  for Renode's raw UART terminal.

## Checkpoints

| UTC date | Checkpoint | Result | Evidence |
|---|---|---|---|
| 2026-09-06 | R0.1–R0.3 | Complete | Created both private mirrors, retained fetch-only upstream remotes, pinned the exact Renode 1.16.1 parent and infrastructure commits, and created the isolated feature branch/worktree. |
| 2026-09-06 | R1.1, R2.1–R2.2 | Complete | Infrastructure commit `780d78774` adds focused DMA tests and corrects short FIFO requests, normal-mode disable, transfer-complete IRQs, and circular NDTR/address reload. Both focused tests pass on .NET 8 Release. |
| 2026-09-06 | R0.4 | Complete | Added source-only private CI with SHA-pinned actions, read-only permissions, an exact private-submodule revision check, and focused STM32 model tests. Installed a repository-scoped, read-only Infrastructure deploy key; no personal token or firmware artifact is used. |
| 2026-09-06 | R2.3–R2.4, R4.1 | Complete | Infrastructure commits through `7acded2e5` add paced SPI TX DMA requests, request-paced peripheral DMA, correct UART enable/IDLE semantics, and MIT-licensed generic tests. All 12 focused DMA/SPI/UART tests pass on .NET 8 Release. |
| 2026-09-07 | R1.2–R1.3, R3.1, R3.4 | Complete | Infrastructure commit `4037da909` preserves level-like requests across DMA setup, drains buffered UART RX, and adds UART TX DMA. Fifteen focused model tests pass. The custom Renode build passes official LEGO v2/v3 and Pybricks vector/progress gates plus original spike-nx and Brickwright protected boot gates. |
| 2026-09-07 | R3.2–R3.3 | Complete | The unchanged Brickwright image completes SPI2 flash DMA, reaches protected userspace, consumes the opaque service pack through the lawful H4 responder, returns from `bt_enable`, registers its transport, and reaches the daemon-ready boundary. The firmware-side `net_buf_pool` linker correction fixed the post-HCI protected-userspace fault. |
| 2026-09-07 | Public release | Complete | Published the Infrastructure fork first, changed its consumer to anonymous HTTPS, removed the deploy-key workflow dependency, retained read-only/no-artifact CI, and prepared anonymous recursive-clone validation before publishing the top fork. |
| 2026-09-07 | R5.1 | Complete | Added a generic TLC5955 SPI/LAT model and three MIT-licensed unit tests covering edge-triggered latching, shift-register overflow, reset, counters, and defensive state snapshots. Public model CI includes the new fixture and remains source-only. |
| 2026-09-07 | R5.2 | Complete | Added a generic LSM6DS3TR-C I2C/register model and five MIT-licensed tests covering identity, immediate reset, control and auto-increment behavior, little-endian accel/gyro/temperature injection, data-ready lifetime, and defensive register snapshots. Timing, FIFO, interrupts, sensor conversion, and physical noise remain explicitly outside this deterministic checkpoint. |
| 2026-09-07 | R5.3 | Complete | Six configuration-level tests prove the generic SPI NOR model against the unchanged board driver's W25Q256JV opcodes and a high 32-bit address. Narrow generic fixes add the 4-byte fast-read dummy cycle, physical NOR bit clearing, WEL-gated chip erase, and an optional second-status opcode. Program/erase complete synchronously, so BUSY intentionally remains zero. |
| 2026-09-07 | R6.1–R6.2 | Complete | Added the distinct `spike-essential.repl`, a source-cited hardware map, safe local-only SHA-256 manifests, loader self-tests, and opt-in image vector/progress gates. Platform parsing and device identity pass; a synthetic user-image fixture proves the executable gate while absent real images skip honestly. No image is fetched, tracked, logged, or uploaded. |
| 2026-09-07 | R7.1 | Complete | Inventoried the earlier firmware-local TCP/H4 responder and defined a reusable MIT protocol core with transport-independent input/output, validated configuration, and tested L2CAP channel routing. No firmware or vendor material is present. |
| 2026-09-07 | R7.2 | Complete | Added fragmented/coalesced H4 framing, deterministic dual-mode initialization commands, explicit opaque-vendor acknowledgement, advertising, LE and Classic connection lifecycle events, ACL reassembly/routing, flow-control completion, and byte-exact tests. |
| 2026-09-07 | R7.3 | Complete | Added replaceable fixed-channel peers: an ATT/GATT attribute database supporting MTU exchange, primary-service and type discovery, reads, writes, and ATT errors; plus an RFCOMM DLCI session supporting SABM, UA, DISC, UIH data, and standards-derived FCS generation. |
| 2026-09-07 | R7.4 | Complete | Added in-memory and raw TCP adapters, a command-line process compatible with Renode's raw UART terminal, fragmented loopback integration coverage, Python compile gates, and source-only CI. The workflow remains read-only and uploads no artifacts. |
