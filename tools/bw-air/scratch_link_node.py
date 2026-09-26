# SPDX-License-Identifier: Apache-2.0
"""Scratch Link node on the bw-air/1 air (prototype).

Brickwright lite and Scratch talk to real hardware through Scratch Link: a
local WebSocket server (ws://127.0.0.1:20111/scratch/ble and /scratch/bt)
speaking JSON-RPC 2.0. This gateway serves the same protocol, but every
session is a bumble central on the simulated air, so a browser reaches an
emulated hub (SPIKE in Renode, or any other station on the air) exactly as it
would reach a physical one.

Implemented: getVersion; BLE discover/connect/write/read/startNotifications/
stopNotifications with characteristicDidChange; BT discover/connect/send with
didReceiveMessage. bw-air/1 has no inquiry procedure, so BT discovery scans
LE for two seconds and reports advertisers using a public address: a
dual-mode device such as the SPIKE hub advertises its BR/EDR address.

  scratch_link_node.py --air 127.0.0.1:7461 --port 20111
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import logging

import websockets

from bumble.core import UUID, PhysicalTransport
from bumble.device import Peer

logger = logging.getLogger("bw-air.scratch-link")
_addresses = itertools.count(0xC1)


def _uuid(value) -> UUID:
    if isinstance(value, int):
        return UUID.from_16_bits(value)
    text = str(value)
    if len(text) == 4:
        return UUID.from_16_bits(int(text, 16))
    return UUID(text)


def _b64(data: bytes) -> str:
    return base64.b64encode(bytes(data)).decode("ascii")


class Session:
    def __init__(self, air, websocket, kind: str) -> None:
        self.air = air
        self.websocket = websocket
        self.kind = kind
        self.station = None
        self.connection = None
        self.peer = None
        self.dlc = None
        self.discovered: dict[str, object] = {}

    async def notify(self, method: str, params: dict) -> None:
        await self.websocket.send(json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params}))

    async def central(self):
        if self.station is None:
            address = f"02:B1:0E:5A:18:{next(_addresses) & 0xFF:02X}"
            self.station = await self.air.add_peer(f"scratch-{self.kind}-{address}",
                                                   address)
        return self.station.device

    # ---- JSON-RPC methods -------------------------------------------------
    async def getVersion(self, params):
        return {"protocol": "1.3"}

    async def discover(self, params):
        device = await self.central()
        if self.kind == "bt":
            def on_classic_candidate(advertisement):
                key = str(advertisement.address)
                if not key.endswith("/P") or key in self.discovered:
                    return
                self.discovered[key] = key.split("/")[0]
                asyncio.ensure_future(self.notify("didDiscoverPeripheral", {
                    "peripheralId": key, "name": key, "rssi": advertisement.rssi}))

            device.on("advertisement", on_classic_candidate)
            await device.start_scanning(filter_duplicates=True)
            await asyncio.sleep(2)
            await device.stop_scanning()
            return None
        wanted = [_uuid(service) for f in params.get("filters", [])
                  for service in f.get("services", [])]

        def on_advertisement(advertisement):
            data = advertisement.data
            uuids = []
            for ad_type in (0x02, 0x03, 0x06, 0x07):
                uuids += data.get(ad_type, raw=False) or []
            key = str(advertisement.address)
            if wanted and uuids and not any(u in wanted for u in uuids):
                return
            if key in self.discovered:
                return
            self.discovered[key] = advertisement.address
            name = data.get(0x09, raw=False) or data.get(0x08, raw=False) or key
            asyncio.ensure_future(self.notify("didDiscoverPeripheral", {
                "peripheralId": key, "name": str(name), "rssi": advertisement.rssi}))

        device.on("advertisement", on_advertisement)
        await device.start_scanning(filter_duplicates=True)
        return None

    async def connect(self, params):
        device = await self.central()
        target = self.discovered.get(params["peripheralId"], params["peripheralId"])
        if self.kind == "bt":
            from bumble.rfcomm import Client, find_rfcomm_channel_with_uuid
            self.connection = await device.connect(
                target, transport=PhysicalTransport.BR_EDR, timeout=30)
            channel = await find_rfcomm_channel_with_uuid(
                self.connection, "00001101-0000-1000-8000-00805F9B34FB")
            multiplexer = await Client(self.connection).start()
            self.dlc = await multiplexer.open_dlc(channel)
            self.dlc.sink = lambda data: asyncio.ensure_future(self.notify(
                "didReceiveMessage", {"message": _b64(data), "encoding": "base64"}))
            return None
        if device.is_scanning:
            await device.stop_scanning()
        self.connection = await device.connect(
            target, transport=PhysicalTransport.LE, timeout=30)
        self.peer = Peer(self.connection)
        await self.peer.discover_all()
        return None

    def _characteristic(self, params):
        service = self.peer.get_services_by_uuid(_uuid(params["serviceId"]))[0]
        return service.get_characteristics_by_uuid(
            _uuid(params["characteristicId"]))[0]

    async def write(self, params):
        data = base64.b64decode(params["message"]) \
            if params.get("encoding") == "base64" else params["message"].encode()
        await self.peer.write_value(self._characteristic(params), data,
                                    with_response=bool(params.get("withResponse")))
        return len(data)

    async def read(self, params):
        characteristic = self._characteristic(params)
        if params.get("startNotifications"):
            await self.startNotifications(params)
        value = await self.peer.read_value(characteristic)
        return {"message": _b64(value), "encoding": "base64"}

    async def startNotifications(self, params):
        characteristic = self._characteristic(params)

        def on_value(value):
            asyncio.ensure_future(self.notify("characteristicDidChange", {
                "serviceId": params["serviceId"],
                "characteristicId": params["characteristicId"],
                "message": _b64(value), "encoding": "base64"}))

        await self.peer.subscribe(characteristic, on_value)
        return None

    async def stopNotifications(self, params):
        await self.peer.unsubscribe(self._characteristic(params))
        return None

    async def send(self, params):
        data = base64.b64decode(params["message"]) \
            if params.get("encoding") == "base64" else params["message"].encode()
        self.dlc.write(data)
        return len(data)

    async def close(self):
        if self.connection is not None:
            try:
                await self.connection.disconnect()
            except Exception:  # already gone
                pass
        if self.station is not None:
            await self.air.remove(self.station.name)


async def serve(air, host: str = "127.0.0.1", port: int = 20111):
    async def handler(websocket):
        path = websocket.request.path
        kind = "bt" if path.rstrip("/").endswith("/bt") else "ble"
        session = Session(air, websocket, kind)
        try:
            async for text in websocket:
                message = json.loads(text)
                if "method" not in message:
                    continue
                method = getattr(session, message["method"], None)
                reply = {"jsonrpc": "2.0", "id": message.get("id")}
                try:
                    if method is None:
                        raise NotImplementedError(message["method"])
                    reply["result"] = await method(message.get("params") or {})
                except Exception as error:  # reported to the client
                    logger.warning("%s failed: %r", message["method"], error)
                    reply["error"] = {"code": -32603, "message": str(error)}
                if "id" in message:
                    await websocket.send(json.dumps(reply))
        finally:
            await session.close()

    return await websockets.serve(handler, host, port)


async def main() -> None:
    import argparse
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hci_node import Air
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--air", default="127.0.0.1:7461", help="bw-air/1 hub")
    parser.add_argument("--port", type=int, default=20111)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    await serve(Air(arguments.air), port=arguments.port)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
