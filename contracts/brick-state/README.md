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
`lego-prime-v2`, `lego-prime-v3`, `pybricks-prime`, `spike-nx`, and
`brickwright-nuttx`. Essential accepts `lego-essential` and
`pybricks-essential`. Unknown identities require a new contract version.

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
The repository does not yet bind this seam to Renode's Python monitor or a
listening socket. A scenario must supply the actual `machine[path]` binding,
identity, model paths, sampling schedule, and framed transport.
