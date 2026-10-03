# Bounded program UART synthetic checks

Run `dotnet run --project tests/tools/program-uart/ProgramUartTests.csproj --configuration Release`.
The harness uses authored interface stubs, not Renode emulation. Its 59 checks
cover clock pacing, FIFO bounds, generation, explicit faults and owned teardown,
including cross-thread output during writes and disposal racing with an in-flight release. No firmware is required.
The .NET SDK is a test-only dependency; Renode includes the C# model directly.

Actual firmware qualification uses `tools/check_prime_micropython.py` with
`--program-uart-model tools/spike_program_uart.cs`, an explicitly supplied image,
Renode, the SPIKE model source and platform root. Add `--motor-test` and
`--raw-repl-test` to test modeled motor load/stall and raw REPL completion,
errors and interruption. All generated artifacts belong in a private output
folder. The model itself has no image, network listener or firmware dependency.

The coordinator qualified this path with a locally supplied upstream MicroPython
LEGO_HUB_NO6 1.26.1 image in Renode 1.16.1: arithmetic, Ctrl-C and recovery,
raw REPL completion/error/cancel, file write/flush/fresh-process restoration,
and port A modeled drive/load/stall/recovery/finally braking passed. Initial
integration failures and resource-related timeouts are preserved privately.
A compiled mutation restoring shared input/output locking fails the synthetic
cross-thread callback test. This does not qualify original LEGO firmware,
USB/bootloader startup, all hub peripherals, or high-level SPIKE Python APIs.

This transport releases one byte per 100 microseconds of simulated time. Host
writes accept 1–32 bytes with a 256-byte pending queue and 65536-byte lifetime
budget per attachment; reads drain 1–4096 bytes from a 65536-byte output queue.
Queue acceptance does not mean the guest consumed the byte. Output overflow or
UART failure faults the attachment. Generation identifies the owned attachment;
it is not authentication. A detached attachment cannot be reused.

Lifecycle operations belong to host control code outside emulation callbacks.
The implementation rejects calls from its own callbacks; callers must exclude
other CPU callbacks. Teardown failures are explicit and require disposal of the
owned process. Native startup, closed state-service UART commands and GUI
selection require additional integration; including this model alone does not
enable those features. No electrical timing or complete firmware compatibility
claim is made.

New transport and synthetic test code: BSD-3-Clause, Brickwright contributors.
Retained Renode public interfaces/runtime: MIT, Antmicro and Realtime Embedded;
retain the runtime's existing copyright notices and licenses/MIT.txt.
