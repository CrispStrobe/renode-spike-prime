# Completed simulation work

- Repository provenance and source-only CI were established on pinned Renode
  1.16.1 and public MIT Infrastructure revisions.
- Generic STM32 DMA, SPI and UART behavior was corrected and covered by focused
  tests; protected Prime firmware reaches its daemon-ready boundary.
- Deterministic TLC5955, LSM6DS3TR-C and W25Q256-compatible models were added.
- A distinct SPIKE Essential platform, local hash-manifest image loaders and
  bounded official/Pybricks execution gates were added.
- A versioned unchanged-firmware matrix now covers seven Prime and Essential
  targets. It verifies every local artifact before machine creation, skips
  absent inputs explicitly, and runs target-specific vector, progress, symbol,
  device-initialization, and H4 boundaries where the available image and model
  expose them. Public CI exercises only synthetic loader contracts.
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

Commit history and CI retain detailed evidence.
