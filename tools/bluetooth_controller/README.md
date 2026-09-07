# Deterministic Bluetooth controller model

This MIT-licensed package models the public byte-level boundary between a hub
firmware Bluetooth host and a dual-mode controller. It does not contain,
decode, or replace TI controller firmware and it does not model RF behavior.

Implemented layers are incremental H4 framing, deterministic HCI lifecycle and
ACL flow control, L2CAP routing and Classic signaling, configurable SDP,
RFCOMM sessions, and a small ATT/GATT server with reads, writes, discovery,
notifications, and indications. The core accepts bytes through `feed()` and
emits complete frames through a callback; in-memory and raw TCP adapters keep
transport concerns outside protocol state.

Run the focused suite from the repository root:

```bash
python3 -m unittest discover -s tests/tools -p 'bluetooth_controller*_test.py'
```

`tools/spike-bluetooth-controller.py` exposes the raw TCP adapter for a local
Renode UART connection. Vendor-command acknowledgement is opt-in and opaque:
parameters are neither interpreted nor retained. Resource limits and malformed
stream recovery are covered by tests.

This is a deterministic software test peer. Successful initialization or data
exchange does not demonstrate TI silicon behavior, Bluetooth qualification,
radio interoperability, timing fidelity, or physical-hardware safety.
