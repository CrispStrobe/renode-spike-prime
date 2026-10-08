# bw-air/1 — one virtual 2.4 GHz air for every simulated node

Status: the one simulated air of the project. Implemented for the emulated
micro:bit V1 / Calliope mini (SoftDevice HLE in Renode and labwired), the
emulated SPIKE Prime hub (its Zephyr host over the Renode UART, through
`hci_node.py`), bumble devices (virtual phone, tests), raw radio, and Scratch
Link clients such as Brickwright lite (through `scratch_link_node.py`).

Home: `renode-spike-prime/tools/bw-air/`. This directory is the only
implementation; other repositories (brickwright-spike-prime-fw, labwired-core)
join it and do not carry their own air.

| file | role |
|---|---|
| `airhub.py` | the hub (the medium); standard library only |
| `bumble_air.py` | `AirLink`: a bumble `LocalLink` whose far side is the hub; virtual-phone central |
| `hci_node.py` | HCI hosts on the air: a Renode UART exported as TCP (`--renode-hci`), HCI hosts dialling in (`--hci-listen`), in-process peers |
| `scratch_link_node.py` | Scratch Link JSON-RPC (`/scratch/ble`, `/scratch/bt`) for browsers and lite |
| `test_air.py` | self-test through the hub: LE GATT between dial-in HCI hosts, BR/EDR page/SSP/encryption/L2CAP |

Read the [HCI stream lifecycle contract](STREAM-LIFECYCLE.md) for ownership,
shutdown, delivery errors and the separate candidate qualification gates.

## Why one air

A micro:bit emulated in Renode, a micro:bit emulated in labwired, a SPIKE hub
emulated in Renode, a virtual phone, and lite in a browser must be able to see
each other: scan, connect, exchange GATT traffic, and (micro:bits) send
MakeCode radio packets. They live in different processes, different
emulators and different languages, and model Bluetooth at different depths:

* the micro:bit's SoftDevice is emulated at **API** level: there is no link
  layer, only "advertise this", "connected", "this ATT PDU arrived";
* the SPIKE hub runs a real host stack against an **HCI** controller (today an
  H4 responder in Renode);
* a phone/central is easiest as a **bumble** device (host + virtual controller);
* MakeCode radio drives the nRF RADIO peripheral **raw** (no BLE at all).

The common denominator is the level of google/bumble's `LocalLink` (Apache-2.0):
advertising PDUs, LL control PDUs and L2CAP frames between device addresses,
without access addresses, channel hopping or timing. An HCI controller turns
into this level with bumble's `Controller`; an API-level SoftDevice speaks it
directly; raw radio frames travel beside it.

## Transport

A hub process (`airhub.py`, standard library only) is the air:

* TCP `127.0.0.1:7461`: newline-delimited JSON, one object per line;
* WebSocket `127.0.0.1:7462`: one JSON object per text frame (browsers).

The hub is a **broadcast medium**: every message a node sends goes to every
other node. Receivers filter (by destination address, frequency, access
address) exactly as radios do. The hub may log every message (`--log`), which
is the sniffer trace used as evidence.

## Messages

All byte strings are lowercase hex. Addresses are `AA:BB:CC:DD:EE:FF` most
significant first; a public address carries the suffix `/P` (bumble's
convention), a random one none.

| `t` | fields | meaning |
|-----|--------|---------|
| `hello` | `node`, `kind`, `proto:"bw-air/1"` | first message of a node |
| `adv` | `addr`, `pdu` (`adv_ind` connectable, `adv_nonconn_ind`, `adv_scan_ind`), `data` (AD structures, <= 31 bytes), `scan_rsp` | one advertising event |
| `connect_ind` | `initiator`, `advertiser`, `interval` (1.25 ms units), `latency`, `timeout` (10 ms units) | a central connects to an advertiser; the advertiser answers nothing — the connection exists from now on |
| `acl` | `src`, `dst`, `data` = one L2CAP basic frame (length u16 LE, CID u16 LE, payload): CID 4 ATT, 5 LE signalling, 6 SMP | data on an established connection |
| `ll` | `src`, `dst`, `op`, `error_code`, `rand`, `ediv`, `ltk` | LL control: `terminate_ind` (error_code = HCI reason), `enc_req` (rand, ediv, and the LTK the initiator uses — a virtual air carries it in the clear so the peer can check it matches instead of running AES-CCM), `start_enc_rsp`, `reject_ext_ind` (error_code), `feature_req`, `feature_rsp` |
| `lmp` | `src`, `dst` (public addresses), `data` = one LMP PDU (opcode, escaped opcodes as two bytes, then parameters) | BR/EDR link manager: connection setup, Secure Simple Pairing, detach |
| `acl_br` | `src`, `dst`, `data` = one L2CAP basic frame | BR/EDR data on an established ACL link (L2CAP signalling CID 1, SDP, RFCOMM) |
| `enc_br` | `src`, `dst`, `state` (0 off, 1 E0, 2 AES-CCM) | BR/EDR link encryption changed; like `enc_req`, the air carries the fact, not ciphertext |
| `raw` | `src`, `freq` (nRF FREQUENCY: 2400+freq MHz), `mode` (nRF RADIO MODE), `address` (BASEn \| PREFIX << 8*BALEN of the logical address used), `balen`, `packet` (the packet image in RAM at PACKETPTR: S0/LENGTH/S1 then payload), `tx_power` (dBm) | one proprietary 2.4 GHz frame (MakeCode radio uses `mode` 0 Nrf_1Mbit, freq 7 + band) |

Security on the virtual air: pairing is real SMP over `acl` CID 6 (legacy Just
Works: c1/s1 computed per Core Vol 3 Part H), so each side derives the STK;
link encryption is then the `enc_req`/`start_enc_rsp` handshake carrying the
key, not ciphertext.

## Joining

* **SoftDevice HLE (micro:bit V1/Calliope, Renode or labwired):**
  `SoftDeviceHle` `air: "127.0.0.1:7461"` (Renode) or `sd_hle_run --air ...`
  (labwired). The Rust core (`nrf_softdevice_hle::air::TcpAir`) speaks the
  protocol.
* **Any bumble device:** `bumble_air.AirLink(host, port, node)` is a
  `LocalLink`; put a `bumble.controller.Controller` on it. `bumble_air.py
  central` is a virtual phone (scan, connect, pair, discover, UART service).
* **SPIKE Prime hub (Renode):** Renode exports the hub's USART2 (the CC2564C
  HCI UART) with `emulation CreateServerSocketTerminal PORT "hci" false` and
  `connector Connect sysbus.usart2 hci`; `hci_node.py --renode-hci
  spike=127.0.0.1:PORT@02:B1:0E:5A:17:01` puts a bumble `Controller` on that
  byte stream. The firmware's own Zephyr host then advertises, accepts LE and
  BR/EDR connections, and serves FD02 GATT and SPP on this air. Only the
  TI-free simulation profile runs here: it sends no vendor commands, and the
  controller refuses any that arrive. End-to-end test:
  brickwright-spike-prime-fw `simulation/bluetooth-air/test_spike_air.py`.
* **Any HCI host in another emulator:** connect to `hci_node.py --hci-listen
  PORT` and speak H4; each connection is one controller on the air.
* **lite (browser):** today, `scratch_link_node.py --port 20111` serves the
  Scratch Link protocol lite already uses for real hardware, with each session
  a bumble central on the air. Later, a direct WebSocket to `:7462` with this
  JSON can back a virtual Web Bluetooth: `requestDevice` = collect `adv`,
  `connect` = send `connect_ind`, GATT = ATT PDUs in `acl` frames.
* **Raw radio (MakeCode radio):** inside one Renode process, machines share a
  Renode wireless medium directly (`emulation CreateBLEMedium`, `connector
  Connect`); across processes/emulators a RADIO model emits/consumes `raw`.
  labwired's `VirtualAirBus` is the in-process equivalent.

## Non-goals

No RF physics (path loss, collisions, timing) — labwired's `RfMedium` and
Renode's range media remain available inside one emulator. BR/EDR is
carried at bumble's LMP level (`lmp`, `acl_br`, `enc_br`); there is no inquiry
procedure, so BR/EDR peers are found through their LE advertisement (a
dual-mode device advertises its public address) or by known address.

## Addresses on `acl`

`src` is the address the sender uses on that connection (the one the peer saw
in `adv`/`connect_ind`). bumble 0.0.235 labels LE data with the controller's
random address, which a host advertising with its public identity never sets;
`AirLink` corrects this.

## Versioning

`lmp`, `acl_br` and `enc_br` were added to bw-air/1 without a version change:
they are new `t` values, and nodes ignore types they do not know (the Rust
`nrf_softdevice_hle::air` parser already does).
