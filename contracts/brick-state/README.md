# Neutral brick-state contract

Version 1 is a UTF-8 NDJSON protocol. Each line is one canonical JSON object
and is at most 256 KiB. Producers assign strictly increasing `seq` values and
an emulated `clockNs`; consumers reject replayed snapshots. A queue overflow
must emit a `gap` naming `firstDroppedSeq`, `dropped`, and the retained
`nextSeq` before that snapshot. This representation works when sequence zero
is the first dropped item.

Snapshots identify the board, firmware family, transport, image SHA-256,
capabilities, and known limitations. They carry lifecycle, ports, motors,
sensors, display, buttons, battery, power, IMU, audio, storage, and Bluetooth
state. Commands carry a unique `requestId` and may carry `expectedSeq` for
optimistic concurrency. Results echo the request ID.

The version-1 identity vocabulary is board-qualified. Prime accepts
`lego-prime-v2`, `lego-prime-v3`, `spike-nx`,
`brickwright-nuttx`, and the simulation-only `brickwright-arena-demo`. Essential accepts `lego-essential`. EV3 accepts `brickwright-ev3-smoke` with transport `none`.
Unknown identities fail closed; adding a family requires a reviewed contract extension.

Unknown `schemaVersion` values and missing required fields fail closed.
Unknown fields within version 1 are optional and ignored by consumers. Numbers
must be finite; serializers sort object keys, omit insignificant whitespace,
and escape non-ASCII text. Implementations must bound line length, queues,
arrays, and replay memory.

`v1/schema.json` is normative. The NDJSON files are canonical fixtures. The
Python boundary in `tools/spike_state_bridge.py` is the Renode-side reference
codec and command gate. It exposes plain data only; emulator objects stay
behind that boundary.

`RenodeModelObserver` is an adapter seam that reads only public properties exposed by the
power, IMU, display, audio, storage, Bluetooth, and LPF2 models. Its explicit
path map makes absent models a reported limitation. `LiveStateSession` owns
connection state, monotonic emulated time, sequence continuity, bounded
backpressure, replay rejection, and the small command allowlist. An embedding
monitor or socket must frame input with `parse_line()` and output with
`canonical_bytes()`; arbitrary monitor or host commands are never dispatched.
`scripts/spike-state-server.py` is an opt-in Renode monitor include. Its start
command binds `monitor.Machine`, Renode's external registry, and the master
`ElapsedVirtualTime` clock to its bounded IronPython TCP service. The reusable
CPython service in `tools/spike_state_socket.py` enforces the same boundary for
source-only integration tests. Paths use `machine:name` or `external:name`;
unprefixed paths mean machine peripherals. The example config is intentionally
not auto-started and contains no firmware. A scenario must select the identity,
paths, and port explicitly. Non-loopback binds require an explicit source-level
opt-in in the reusable service; the monitor command always refuses it. Input
lines, clients, queues, reads, command replay memory, and socket
timeouts are bounded; arbitrary monitor and host commands are never exposed.
The monitor implementation intentionally accepts one active client; the
reusable source-test service has a validated maximum of four.
Before listening, the monitor validates the board-qualified firmware pairs,
required transport, and a null or lowercase SHA-256 image identity. Commands
bound request IDs to 128 characters and names to 64, require object arguments,
and reject negative or non-integer expected sequences. Framing applies the
256-KiB limit per record and separately caps each read and records per batch.
The monitor service obtains Renode's paused-state guard around every model read
and mutation. `spike_state_sample` emits a snapshot at the current virtual time,
so Robot scenarios can sample after deterministic emulated-time milestones.
There is no wall-clock telemetry loop; periodic virtual-time sampling remains
a scenario responsibility.

For the Prime script, the six port paths are `external:primePortA` through
`external:primePortF`; the checked-in example config includes them. Start the
machine with `include @scripts/single-node/spike-prime.resc`, include
`@scripts/spike-state-server.py`, then run
`spike_state_start 127.0.0.1 8765 @contracts/brick-state/renode-prime.example.json`.
The boundary is raw loopback TCP, not WebSocket; an application broker must
translate or forward canonical NDJSON without exposing Renode's monitor.

EV3 uses `renode-ev3.example.json` and the same loopback service. Its observer
reads actual public GPIO button/LED states, ST7586 grayscale framebuffer
(178x128, exactly 22,784 integer luminances 0..255), ADS7957 raw channels
(16 ten-bit samples), and configured PWM-driven motor electrical/tachometer
state. Missing buttons are null; unavailable battery and IMU explicitly say
`available:false`. No speed, physical sensor decoding, or mechanical position
is fabricated. Missing motor ports, including C/D before their PWM sources
exist, are explicit unattached ports and limitations.

EV3 commands are only `state.sample` (empty arguments), `ev3.button.set`
(`button`: center/left/back/right/down/up, boolean `pressed`), and
`ev3.analog.set-channel` (integer channel0..15, value0..1023). Extra arguments,
unknown commands, replayed requests and stale sequences are rejected. Samples
are requested on demand under Renode's paused-state guard; there is no
unbounded wall-clock publisher. Frame events are a separate video-model API;
the neutral stream carries bounded defensive grayscale snapshots.
