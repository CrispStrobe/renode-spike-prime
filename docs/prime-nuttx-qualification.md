# Full protected NuttX execution in Renode

Our source-built kernel and userspace execute the robot-program upload ABI and
an embedded MicroPython interpreter. CPU execution owns program scheduling;
the monitor exchanges bounded packets and observes model state. GPIO/PWM
motor drive and LPF2 encoder/sensor traffic pass through the existing Prime
hardware models. The arena supplies sensor values and loads through the same
state service. No monitor-side program interpreter is used.

The supported program contract and licences are documented in the firmware
repository's `docs/hubprogram.md` and `docs/hubprogram-licences.md`. The packet
mailbox is resolved from that firmware's ELF symbol, rather than a client
address. Python output uses a bounded 1024-byte buffer. New components are
BSD-3-Clause; retained model notices and licence texts are preserved.

Run the source model fixtures without a firmware image:

```sh
ulimit -c 0
python3 tools/check_prime_source_models.py \
  --infrastructure /path/to/renode-infrastructure-spike-prime \
  --renode /path/to/renode \
  --output /private/new-source-check
```

After building our full firmware, run the external robot scenarios:

```sh
python3 tools/check_prime_nuttx.py \
  --firmware-root /path/to/brickwright-spike-prime-fw \
  --infrastructure /path/to/renode-infrastructure-spike-prime \
  --renode /path/to/renode \
  --output /private/new-nuttx-check
```

Check that the synthetic SPI regression rejects stale receive requests and
FIFO overreads:

```sh
ulimit -c 0
python3 tools/check_prime_spi_dma_mutations.py \
  --infrastructure /path/to/renode-infrastructure-spike-prime \
  --renode /path/to/renode \
  --output /private/new-spi-mutation-check
```

All output directories must be new. Generated configurations, result JSON,
logs and transcripts belong in private storage. The robot suite qualifies
wait/end sequences, real embedded Python execution and failure, cancellation,
motor speed/braking, relative position control, concurrent motor/sensor waits,
arena force input and load stall/cancellation. The tested 30-degree move is
within three degrees, a synthetic model tolerance. The source suite includes
ADC trigger/halfword reads, I2C receive streaming, repeated SPI receive-DMA
blocks after CPU command reads in both direct and FIFO modes, LPF2 discovery/electrical
motor drive, display-clock behavior and actual UART endpoint wiring. A
mutation disconnecting the ADC trigger is detected by its scan fixture.

Routine qualification seeds the synthetic W25Q256 filesystem partition at
`0x100000` with an 8192-byte empty LittleFS prefix generated from the reviewed
retained filesystem source. The formatter verifies a read-only mount and empty
root before creating its output; remaining flash stays erased. This avoids a
lengthy initial scan without changing firmware preservation checks. Use
`--blank-flash-test` to exercise erased-flash initialization separately. A seeded
boot result does not establish blank-flash first-boot performance. SPI2 receive
DMA is connected to DMA1 stream 3. Receive requests are withdrawn when CPU
reads drain RXNE; each peripheral request transfers one peripheral data unit,
even when a memory-side FIFO threshold is configured. These checks cover the
byte-width SPI path used by this firmware. General FIFO packing across unequal
memory/peripheral widths and memory bursts are not qualified.

These tests do not establish physical accuracy or complete firmware/API
compatibility. USB OTG, a working BLE radio/link, power-loss durability and wider filesystem
operations, and runtime MPU isolation need
further qualification. Cold full-image startup
is expensive on a busy host; desktop launch retains its existing hard limits.

`tools/spike_local_image.py` provides a separate bounded CPU probe for a
user-supplied local image. It does not download or package images, and a CPU
probe does not qualify robot-program execution, peripherals or an arena
backend. Original firmware inputs and their run records stay private.

## Program file and restart qualification

With a source-built firmware implementing SAVE (8) and LOAD (9), run:

```sh
python3 tools/check_prime_nuttx.py \
  --firmware-root /path/to/brickwright-spike-prime-fw \
  --infrastructure /path/to/renode-infrastructure-spike-prime \
  --renode /path/to/renode \
  --storage-test --output /private/new-program-persistence-check
```

This writes maximum-size native (256 rows) and completed Python (4095 source
bytes) programs through the firmware's
packet service, snapshots only the synthetic external flash, and starts
separate emulator processes to restore, load and execute each program. It
checks missing/wrong IDs, upload/execution busy rejection, READY after load
and no automatic load on boot. Generated flash snapshots are private local
test artifacts; the launcher does not accept client-selected storage paths.
A passing test establishes the tested clean-restart cases, not power-loss
durability, physical flash timing or full filesystem compatibility.

On 2026-10-02, the source-built protected firmware passed the SAVE/LOAD
write phase and both fresh-process restart phases for native and completed
Python programs. The full robot suite also passed after the lifecycle change
that retains the Python language flag while waiting for motors to stop.
These observations qualify only the scenarios above.

The zero-compare timer regression also has a source-only mutation check:

```sh
python3 tools/check_prime_timer_mutation.py \
  --infrastructure /path/to/renode-infrastructure-spike-prime \
  --renode /path/to/renode \
  --output /private/new-timer-mutation-check
```

It removes the rollover flag update from a staged copy and requires the
fixture to fail with the missing interrupt count. It does not load firmware.

## Six motor connectors and storage discovery

The electrical-port installer registers A–F. Its normal layout remains two
motors, color, distance and force sensors, and an empty F connector. Motor
bridge wiring is available on every connector when an explicit motor profile
is attached. TIM3/TIM4 use AF2 and F spans GPIO banks C and B. The source
fixtures check forward, reverse and braking against the actual installed
bridge definitions on all six ports.

Run firmware qualification with `--all-motors-test` and a new private output
directory. It checks native speed and relative position on every port,
concurrent activity, and native and embedded-Python cancellation. This
profile changes virtual attachments before boot. The firmware debug mailbox
retains its two-motor ABI; C–F motion is observed through the shared arena's
port models.

A packaged full firmware advertises `nuttx-program-storage/v1` only when
its own ELF provides a read-only userspace-flash marker whose live ABI word
is one and the program mailbox is initialized. Older packages stay
unadvertised. Storage packets are checked again at the state service,
and cannot supply memory addresses or file paths.

## Deferred desktop storage requests

A server with `nuttx-program-storage-deferred/v1` accepts only an eight-byte
SAVE/LOAD packet through `nuttx.program.storage.submit`, after verifying our
full-firmware storage marker. Submission queues the unchanged firmware ABI and
returns without waiting for filesystem I/O. Snapshots expose
`lifecycle.nuttxProgramStorage` with `requestSeq`, `replySeq`, `operation`,
`programId` and `pending`. A client must match the submitted sequence and the
reply's operation and program ID before accepting completion or its signed
errno. READY/COMPLETE program state alone does not establish storage success.
An already pending mailbox request rejects another submission.

The GUI polls through the existing state-read path. Each IPC retains its
two-second guard; startup remains bounded to 60 seconds and the process to
120 seconds. A storage job has a separate bounded completion wait; a timeout
means its final storage outcome is unknown, and does not roll back firmware
I/O. No arbitrary path, memory address, firmware instruction or auto-run is
accepted by this operation.
