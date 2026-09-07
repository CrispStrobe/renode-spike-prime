# Deterministic Bluetooth controller model

This MIT-licensed package models the public byte-level boundary between a hub
firmware Bluetooth host and a dual-mode controller. It does not contain,
decode, or replace TI controller firmware and it does not model RF behavior.

The core accepts bytes through `feed()` and emits complete H4 frames through a
callback. In-memory and raw TCP adapters keep transport concerns outside
protocol state. The normative layering, limits, and vendor-command policy are
defined in [`docs/bluetooth-controller.md`](../../docs/bluetooth-controller.md).

Run the focused suite from the repository root:

```bash
python3 -m unittest discover -s tests/tools -p 'bluetooth_controller*_test.py'
```

Attach the raw TCP adapter to a local Renode UART with:

```bash
python3 tools/spike-bluetooth-controller.py 127.0.0.1 3456
```

Add `--acknowledge-vendor-commands` only for a separately supplied bootstrap
stream that requires opaque command-complete events.

This is a deterministic software test peer. Successful initialization or data
exchange does not demonstrate TI silicon behavior, Bluetooth qualification,
radio interoperability, timing fidelity, or physical-hardware safety.
