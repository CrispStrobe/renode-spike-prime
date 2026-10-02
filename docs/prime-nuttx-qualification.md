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

Both output directories must be new. Generated configurations, result JSON,
logs and transcripts belong in private storage. The robot suite qualifies
wait/end sequences, real embedded Python execution and failure, cancellation,
motor speed/braking, relative position control, concurrent motor/sensor waits,
arena force input and load stall/cancellation. The tested 30-degree move is
within three degrees, a synthetic model tolerance. The source suite includes
ADC trigger/halfword reads, I2C receive streaming, LPF2 discovery/electrical
motor drive, display-clock behavior and actual UART endpoint wiring. A
mutation disconnecting the ADC trigger is detected by its scan fixture.

These tests do not establish physical accuracy or complete firmware/API
compatibility. USB OTG, a working BLE radio/link, external LittleFS formatting
and runtime MPU isolation need further qualification. Cold full-image startup
is expensive on a busy host; desktop launch retains its existing hard limits.

`tools/spike_local_image.py` provides a separate bounded CPU probe for a
user-supplied local image. It does not download or package images, and a CPU
probe does not qualify robot-program execution, peripherals or an arena
backend. Original firmware inputs and their run records stay private.
