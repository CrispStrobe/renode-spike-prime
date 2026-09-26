# Official MakeCode micro:bit / Calliope firmware with the SoftDevice emulated

Run the **official** MakeCode micro:bit V1 and Calliope mini images in Renode
(and labwired) with Nordic's MBR, SoftDevice and bootloader **never loaded,
executed or disassembled**; their API is served by a clean-room high-level
emulation, and Bluetooth goes onto a simulated air that other emulated devices
and a virtual phone share.

| piece | where |
|-------|-------|
| the HLE (emulator-neutral, Rust) + SPEC + PROVENANCE + conformance vectors | labwired-core `crates/nrf-softdevice-hle` |
| labwired backend | labwired-core `crates/core/src/sd_hle.rs`, `configs/chips/nrf51822.yaml` |
| Renode backend | `renode/SoftDeviceHle.cs` (+ `NrfTimer.cs`, `NrfNvmc.cs`, `nrf51822-app.repl`, `run.py`) |
| app-region extractor | `appimage.py` |
| the shared air | `../bw-air/` (the one air of the project: `AIR.md`, `airhub.py`, `bumble_air.py`, `hci_node.py`, `scratch_link_node.py`); `fake_app.py` drives the HLE with no emulator |
| conformance through the C ABI | `conformance/run_capi.py` |
| interface-fact extraction (BSD-3 headers, fetched, never committed) | `facts/` |
| GDB RSP probe (no ARM gdb needed) | `debug/rsp_probe.py` |

## Quick start (Renode)

```sh
# 1. the HLE library (labwired-core checkout)
cargo build --release -p nrf-softdevice-hle --features capi
export SDHLE_LIB=$CARGO_TARGET_DIR/release/libnrf_softdevice_hle.so
# 2. keep only the application region of an official hex
python3 appimage.py program.hex v1 /tmp/app        # or: calliope
# 3. the air, a run, a virtual phone
python3 ../bw-air/airhub.py &
python3 renode/run.py --app /tmp/app.bin --out /tmp/run --secs 60 --air 127.0.0.1:7461 &
python3 ../bw-air/bumble_air.py central --target C0:EE:AA:BB:CC:01 --send hello
```

`run.py --app A.bin --app B.bin --radio-medium` puts two micro:bits on one
Renode wireless medium (MakeCode radio). `--gdb 3333` starts Renode's GDB
server; `debug/rsp_probe.py` sets a breakpoint in user code and reads a PXT
global.

## Scope

nRF51 + S110 v8 (micro:bit V1, Calliope mini 1). micro:bit V2 (S113) is out
of scope: its SVC facts exist only under Nordic's chip-restricted licence, and
its official application region itself links nRF5 SDK code under that licence
(measured: 37 modules, 29,310 bytes, radio and Bluetooth bases alike). V2
emulation uses the Bluetooth-free bases built from source (lite PR #332).
