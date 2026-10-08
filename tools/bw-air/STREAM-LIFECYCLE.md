<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# HCI stream ownership and failure contract

This candidate addresses an unobserved background `PacedSink._drain` failure
seen after a passing peer report in firmware
[matrix 37816489598](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37816489598).
It does not change the qualified firmware's Runtime pin or retroactively qualify
that helper's teardown. `hci_node.py` retains its Apache-2.0 licence; newly authored
controls and this contract use [BSD-3-Clause](LICENSE.BSD-3-Clause). No independent-origin claim follows.

## Inputs and observable lifecycle

`Air.attach_hci_client` attaches a TCP H4 stream using a `PacedSink` when its
existing positive pacing gap is selected. Packets are copied into the FIFO and
written in order. Each packet waits for `writer.drain()` followed by the existing
pacing gap. This is host pacing, not simulated time or physical UART calibration.
No queue bound or new radio/controller semantics are introduced by this change.

The stream pump owns its reader task and paced drain task. Normal reader EOF
or explicit `Air.remove(name)` closes admission, cancels and joins pending work,
and attempts to close both the HCI writer and its air-link writer. The station
remains discoverable in a closing state until these joins/close attempts finish;
a concurrent remover joins without cancelling cleanup again. Immediate removal
waits for the pump to enter its cleanup-capable lifetime before cancellation.

Shutdown aborts delivery; it does not flush or establish that queued bytes
reached firmware. `extra['abandoned_packets']` counts queued and indeterminate
in-flight packets, and nonzero counts are logged. A sink rejects new packets
after closure/failure. Writer closure has a cooperative one-second timeout;
`extra['close_errors']` and warning logs retain close failures/timeouts while
cleanup attempts the other writer. These are diagnostics, not a resource-release
guarantee or hard process deadline.

Callers retain the returned `Station` and await `station.wait_closed()` to
observe terminal read/delivery errors. The waiter shields owned cleanup from
caller cancellation; cancelling or timing out a waiter alone does not remove
the station. Use `Air.remove(name)` for explicit removal. Its own cancellation
is not suppressed while cleanup remains live.

A failed write stops the stream and propagates the original error. Simultaneous
EOF, or a failure arriving during cleanup, must not turn it into success. A
primary read failure remains primary if a write also fails during cleanup;
`extra['sink_failure']` retains the latter. Joined reader failures are retained
in `extra['read_failure']`; explicit removal must not hide a reader error that
completed before the join. `extra['failure']` and an explicit
error log observe failed pump completion even if a caller forgets to await it.
A passing peer report alone remains insufficient: consumers must observe stream
completion before claiming clean teardown. A failed initial air connection also
joins the pre-created paced sink and attempts HCI-writer closure.

## Reproducible controls and remaining gates

```sh
python3 tests/tools/bw_air_lifecycle_test.py
python3 tests/tools/bw_air_lifecycle_mutation_test.py
python3 -m pip install -r tools/bw-air/requirements-test.txt
python3 tools/bw-air/test_air.py
```

Seventeen local controls compile the actual lifecycle class ASTs with synthetic
Bumble/I/O boundaries. They cover FIFO/copying, EOF, immediate and in-progress
removal, blocked drain, late and simultaneous failure, primary/secondary error
preservation, cancelled waiters, failed attachment, closed admission and close
diagnostics. The old helper fails the EOF join assertion. Two mutations of the
actual source must fail assertions: omitted drain join and replaced delivery
error. Syntax/setup failures do not count as detection.

The separate hosted workflow imports the real helper and Bumble, exchanges an
actual TCP HCI Reset through `attach_hci_client`, checks joined normal EOF, and
runs the existing LE GATT and Classic pairing/encryption/L2CAP smoke tests. Its
host-only requirements mirror the firmware suite's existing pinned versions;
these are test dependencies, not a newly bundled release or complete licence
clearance. Local synthetic controls do not qualify that network integration.

Before firmware adoption, require the hosted smoke, all enabled Runtime checks,
and the affected actual firmware air suite with the exact new Runtime source.
No new firmware pin, installed GUI, original firmware, physical radio, bounded
queue/backpressure, whole-AirLink lifecycle or process teardown claim is made.
