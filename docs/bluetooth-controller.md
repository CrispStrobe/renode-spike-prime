# Transport-neutral Bluetooth controller

The SPIKE simulation uses an external Bluetooth controller service. The service
models the public Bluetooth HCI and L2CAP interfaces; it does not emulate,
interpret, disassemble, or redistribute TI controller firmware.

The protocol core in `tools/bluetooth_controller/` has one input (`feed`) and
one output callback. It has no socket, Renode, UART, or wall-clock dependency.
Adapters may connect it to Renode's raw UART TCP terminal, an in-memory test, or
another byte stream without changing controller behavior.

The initial contract deliberately separates these layers:

1. H4 incrementally frames commands and ACL packets.
2. The controller owns deterministic HCI state and events.
3. ACL data is reassembled and routed as complete basic-mode L2CAP packets.
4. Fixed or dynamically allocated L2CAP channels own ATT/GATT or RFCOMM
   protocol state.

Vendor-specific commands are rejected unless the caller explicitly enables an
opaque acknowledgement policy. When enabled, parameters remain uninterpreted
and unretained; this only models completion of a separately supplied bootstrap
stream.

The implementation is MIT-licensed and contains no LEGO, Pybricks, or TI
firmware. Its deterministic behavior is a software test model, not evidence of
RF, timing, electrical, or physical-controller fidelity.
