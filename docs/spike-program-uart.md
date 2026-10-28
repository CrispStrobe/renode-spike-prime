# Program UART through the shared state service

The existing loopback brick-state connection carries three closed commands:

| Command | Arguments | Accepted result data |
| --- | --- | --- |
| `micropython.uart.write` | `generation`, `bytes` (1–32 integers, 0–255) | `generation`, `count` equal to input length |
| `micropython.uart.read` | `generation`, `maxBytes` (1–4096) | `generation`, `bytes` (0–requested maximum) |
| `micropython.uart.close` | `generation` | `generation`, `closed: true` |

Generation must be an integer from 1 through 9007199254740991. Objects have
exact fields. Calls cannot choose paths, ports, code strings or monitor commands.
Write acceptance means queued, not consumed by firmware. Read is immediate;
clients implement their own bounded polling deadlines. Close disposes only the
configured UART, leaving the state service and shared hub model available.

The native launch and its `programUartGeneration` own the UART for the entire
route lifetime; individual TCP state-service connections do not own it.
Disconnect/reconnect preserves queued input, unread output and the same UART
generation. A replacement connection deliberately resumes that FIFO, rather
than receiving a fresh program session. `connectionGeneration` changes when
TCP reconnects; it is separate from `programUartGeneration`.

`micropython.uart.close` permanently disposes this native route. Reconnecting
or restarting the state listener cannot reopen the disposed external. A later
connection sees `closed` and its UART reads/writes fail, while state sampling
remains available. Starting another program session requires the native owner
to attach a new external with a fresh generation and matching launch config;
replacing the configured external under an existing binding is refused.
Clients that require private output must request a fresh native launch, rather
than treating a TCP reconnect as an ownership boundary. Two-connection host
tests in `spike_program_uart_test.py` cover FIFO continuation, generation
mismatch, persistent close and continued state sampling.

The native launch config identifies `spike-prime`, `micropython-prime`, transport
`none`, a canonical admitted image SHA-256, `paths.programUart` as a fixed
`external:NAME`, and `programUartGeneration`. The service retains the exact
external object, checks its qualified class and generation, and rejects route
replacement. Snapshot capability `micropython-uart/v1` accompanies lifecycle
`micropythonUart` with generation and ready/closed/faulted state. Generation is
correlation, not authentication; the listener remains loopback-only. Native
launch ownership and broker authorization remain separate requirements.

The adapter never advances simulated time. The bounded C# external releases a
byte every 100 microseconds. Motor and sensor observations continue to come from
the existing hub models; arena inputs use those same models. Result data carries
the exact request ID/sequence through the existing result envelope and is sent
before the next fresh snapshot. Existing commands keep their previous behavior.

Coordinator qualification used an explicitly supplied local MicroPython image
in Renode: arithmetic, infinite-loop Ctrl-C, recovery, invalid requests, UART
close and subsequent state sampling passed. The production Rust feed passed
against that service, including strict correlated data validation. Evidence,
images, generated scripts/JSON and complete transcripts remain private.

Run `python3 -m unittest discover -s tests/tools -p 'spike_*test.py'` for synthetic
and retained protocol coverage without firmware. The model-test CI includes the
new adapter tests. Native image startup and GUI selection are not enabled by
this service contract alone. No original LEGO firmware, USB/bootloader, complete
hub API or physical accuracy claim follows from these tests.

New adapter/tests are BSD-3-Clause, Brickwright contributors. The retained
Renode runtime/public interfaces remain MIT with their original attribution.
