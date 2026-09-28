#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Self-test of the bw-air/1 air with no emulator.

Starts airhub.py and checks, with every station its own hub node:

1. LE: two HCI hosts dial in to hci_node's HCI port (stand-ins for any
   emulated device with an HCI host) and advertise a Nordic UART service; a
   central sees both, connects to one, writes, and receives a notification.
2. BR/EDR: a peer pages another, pairs (Secure Simple Pairing), encrypts, and
   opens an L2CAP channel, all through the hub (lmp, acl_br, enc_br).

  test_air.py [--hub-port 7471]
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hci_node import Air  # noqa: E402

from bumble.core import UUID, PhysicalTransport  # noqa: E402
from bumble.device import Device, Peer  # noqa: E402
from bumble.gatt import Characteristic, CharacteristicValue, Service  # noqa: E402
from bumble.hci import Address  # noqa: E402
from bumble.transport import open_transport  # noqa: E402

SERVICE = UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
RX = UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
TX = UUID("6e400003-b5a3-f393-e0a9-e50e24dcca9e")


async def dial_in_peripheral(port: int, name: str, index: int):
    transport = await open_transport(f"tcp-client:127.0.0.1:{port}")
    device = Device.with_hci(name, Address(f"C1:B1:0E:00:00:{index:02X}"),
                             transport.source, transport.sink)
    tx = Characteristic(TX, Characteristic.Properties.NOTIFY,
                        Characteristic.READABLE, b"")

    def on_write(connection, value):
        asyncio.ensure_future(device.notify_subscribers(tx, b"echo:" + value))

    rx = Characteristic(RX, Characteristic.Properties.WRITE,
                        Characteristic.WRITEABLE, CharacteristicValue(write=on_write))
    device.add_service(Service(SERVICE, [rx, tx]))
    await device.power_on()
    await device.start_advertising(auto_restart=True)
    return device, transport


async def le_check(air: Air, hci_port: int) -> None:
    await air.serve_hci(hci_port, lambda n: f"02:B1:0E:00:00:{n:02X}")
    _, t1 = await dial_in_peripheral(hci_port, "dial-in-1", 1)
    _, t2 = await dial_in_peripheral(hci_port, "dial-in-2", 2)
    central = (await air.add_peer("central", "02:B1:0E:00:00:C0")).device
    loop = asyncio.get_running_loop()
    wanted = {"C1:B1:0E:00:00:01": loop.create_future(),
              "C1:B1:0E:00:00:02": loop.create_future()}

    def on_advertisement(advertisement):
        key = str(advertisement.address).split("/")[0]
        if key in wanted and not wanted[key].done():
            wanted[key].set_result(advertisement)

    central.on("advertisement", on_advertisement)
    await central.start_scanning()
    advertisements = await asyncio.wait_for(asyncio.gather(*wanted.values()), 20)
    await central.stop_scanning()
    print(f"air: LE central saw {len(advertisements)} advertisers via the hub")
    connection = await central.connect(advertisements[0].address,
                                       transport=PhysicalTransport.LE, timeout=20)
    peer = Peer(connection)
    await peer.discover_services([SERVICE])
    service = peer.get_services_by_uuid(SERVICE)[0]
    await service.discover_characteristics()
    rx = service.get_characteristics_by_uuid(RX)[0]
    tx = service.get_characteristics_by_uuid(TX)[0]
    received: asyncio.Queue = asyncio.Queue()
    await peer.subscribe(tx, received.put_nowait)
    await peer.write_value(rx, b"hello", with_response=True)
    value = bytes(await asyncio.wait_for(received.get(), 10))
    assert value == b"echo:hello", value
    print(f"air: LE GATT write/notify via the hub -> {value!r}")
    await connection.disconnect()
    await t1.close()
    await t2.close()


async def classic_check(air: Air) -> None:
    from bumble.l2cap import ClassicChannelSpec
    server = (await air.add_peer("classic-server", "02:B1:0E:00:01:01")).device
    client = (await air.add_peer("classic-client", "02:B1:0E:00:01:02")).device
    await server.set_connectable(True)
    opened: asyncio.Future = asyncio.get_running_loop().create_future()
    server.create_l2cap_server(ClassicChannelSpec(psm=0x1001),
                               handler=lambda channel: opened.done() or opened.set_result(channel))
    connection = await client.connect("02:B1:0E:00:01:01",
                                      transport=PhysicalTransport.BR_EDR, timeout=20)
    await connection.authenticate()
    await connection.encrypt()
    assert connection.is_encrypted
    channel = await connection.create_l2cap_channel(ClassicChannelSpec(psm=0x1001))
    server_channel = await asyncio.wait_for(opened, 10)
    got: asyncio.Queue = asyncio.Queue()
    server_channel.sink = got.put_nowait
    channel.send_pdu(b"over-br-edr")
    value = bytes(await asyncio.wait_for(got.get(), 10))
    assert value == b"over-br-edr", value
    print(f"air: BR/EDR page, SSP, encryption, L2CAP via the hub -> {value!r}")
    await connection.disconnect()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-port", type=int, default=7471)
    parser.add_argument("--hci-port", type=int, default=20129)
    arguments = parser.parse_args()
    hub = subprocess.Popen([sys.executable, str(HERE / "airhub.py"),
                            "--tcp", f"127.0.0.1:{arguments.hub_port}", "--ws", ""])
    try:
        await asyncio.sleep(1)
        air = Air(f"127.0.0.1:{arguments.hub_port}")
        await le_check(air, arguments.hci_port)
        await classic_check(air)
        print("air: PASS")
        return 0
    finally:
        hub.terminate()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
