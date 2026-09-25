# bw-air/1 — one virtual 2.4 GHz air for every simulated node

Status: implemented for the emulated micro:bit V1 / Calliope mini (SoftDevice
HLE in Renode and labwired), bumble devices (virtual phone), and raw radio.
Open for the SPIKE Prime hub (renode-spike-prime / brickwright-spike-prime-fw)
and lite (browser) — see "Joining" below.

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
* **SPIKE Prime hub (proposed, owned by the SPIKE lane):** its NuttX BT host
  speaks HCI over the CC2564 UART. Replace the H4 responder with a bumble
  `Controller` on an `AirLink`, bridged to the Renode UART by bumble's
  transport (`tcp-server:` / `pty:`) — the hub then advertises and accepts
  connections on this air, and a micro:bit or the virtual phone sees it. The
  TI vendor commands (service pack) are answered before the bumble controller
  sees the stream, as today.
* **lite (browser):** a WebSocket to `:7462`, the same JSON. Web Bluetooth
  can be backed by it (the SPIKE lane's virtual Web Bluetooth backend is the
  natural place): `requestDevice` = collect `adv`, `connect` = send
  `connect_ind`, GATT = ATT PDUs in `acl` frames.
* **Raw radio (MakeCode radio):** inside one Renode process, machines share a
  Renode wireless medium directly (`emulation CreateBLEMedium`, `connector
  Connect`); across processes/emulators a RADIO model emits/consumes `raw`.
  labwired's `VirtualAirBus` is the in-process equivalent.

## Non-goals

No RF physics (path loss, collisions, timing) — labwired's `RfMedium` and
Renode's range media remain available inside one emulator. No classic BR/EDR
(the SPIKE's Classic/RFCOMM personality would need `lmp`-level messages; bumble
has them, this protocol version does not carry them).
