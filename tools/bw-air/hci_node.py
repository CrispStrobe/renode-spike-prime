# SPDX-License-Identifier: Apache-2.0
"""HCI nodes on the bw-air/1 air: a bumble Controller per attached host.

Attaches, each as its own node on the air hub (airhub.py, AIR.md):

* an emulated firmware whose HCI UART is exported as a TCP socket
  (``attach_hci_client``: the SPIKE Prime hub's USART2 under Renode);
* any HCI host that dials in over TCP with H4 framing (``serve_hci``);
* an in-process bumble ``Device`` acting as a peer (``add_peer``), used by
  tests and by the Scratch Link node.

Every node has its own AirLink connection to the hub, exactly like separate
radios, so traffic between any two of them crosses the one shared air.
Requires bumble (Apache-2.0).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from bumble import hci
from bumble.controller import Controller
from bumble.device import Device, DeviceConfiguration
from bumble.host import Host
from bumble.transport.common import AsyncPipeSink, StreamPacketSink, StreamPacketSource

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bumble_air import AirLink  # noqa: E402

logger = logging.getLogger("bw-air.hci")

# Configuration writes a host may issue during initialization that have no
# observable effect on the simulated link. The controller acknowledges them
# with success instead of UNKNOWN_HCI_COMMAND so an unmodified host stack
# (Zephyr's, in the SPIKE firmware) completes its bring-up.
BENIGN_CONFIGURATION_OPCODES = {
    0x080D: b"",  # Write_Link_Policy_Settings
    0x080E: b"\x00\x00",  # Read_Default_Link_Policy_Settings: none enabled
    0x080F: b"",  # Write_Default_Link_Policy_Settings
    0x0C18: b"",  # Write_Page_Timeout
    0x0C1C: b"",  # Write_Page_Scan_Activity
    0x0C1E: b"",  # Write_Inquiry_Scan_Activity
    0x0C33: b"",  # Host_Buffer_Size
    0x0C3A: b"",  # Write_Current_IAC_LAP (general or limited discoverable)
    0x0C43: b"",  # Write_Inquiry_Scan_Type
    0x0C45: b"",  # Write_Inquiry_Mode
    0x0C47: b"",  # Write_Page_Scan_Type
    0x0C7A: b"",  # Write_Secure_Connections_Host_Support
}


class AirController(Controller):
    """A bumble controller that answers every command a host sends.

    bumble drops commands it has no handler for when they are not declared
    synchronous; a real controller always answers. Unknown commands get
    Command Complete with UNKNOWN_HCI_COMMAND, except the benign configuration
    writes above, which succeed. Vendor commands (OGF 0x3F) are always refused:
    nothing on this air executes vendor firmware.
    """

    # Dual-mode, like the CC2564C the SPIKE firmware expects: bumble's default
    # declares BR_EDR_NOT_SUPPORTED, which a Classic-enabled host rejects.
    lmp_features = (
        hci.LmpFeatureMask.LE_SUPPORTED_CONTROLLER
        | hci.LmpFeatureMask.SIMULTANEOUS_LE_AND_BR_EDR_TO_SAME_DEVICE_CAPABLE_CONTROLLER
        | hci.LmpFeatureMask.SECURE_SIMPLE_PAIRING_CONTROLLER_SUPPORT
        | hci.LmpFeatureMask.EXTENDED_INQUIRY_RESPONSE
        | hci.LmpFeatureMask.ENCRYPTION
        | hci.LmpFeatureMask.ROLE_SWITCH
        | hci.LmpFeatureMask.EXTENDED_FEATURES
    )

    # bw-air/1 carries legacy advertising only (adv, connect_ind), as the
    # SPIKE firmware and the SoftDevice use; without extended advertising a
    # bumble host falls back to the legacy commands too.
    le_features = Controller.le_features & ~(
        hci.LeFeatureMask.LE_EXTENDED_ADVERTISING
        | hci.LeFeatureMask.LE_PERIODIC_ADVERTISING)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.unknown_commands: list[int] = []
        self.vendor_commands: list[int] = []
        self.commands: list[int] = []

    # ---- Classic link encryption (bumble's controller has no handler) ----
    def _raw_event(self, code: int, parameters: bytes) -> None:
        if self.host:
            event = bytes([hci.HCI_EVENT_PACKET, code, len(parameters)]) + parameters
            asyncio.get_running_loop().call_soon(self.host.on_packet, event)

    def _classic_encryption(self, command: hci.HCI_Command) -> None:
        """Set_Connection_Encryption: after SSP both ends hold the link key, so
        the simulated link reports encryption on to both hosts. No cipher runs
        on the simulated air."""
        handle = int.from_bytes(command.parameters[0:2], "little")
        enable = command.parameters[2]
        local = self.find_classic_connection_by_handle(handle)
        status = 0 if local is not None else 0x02  # unknown connection id
        self._raw_event(0x0F, bytes([status, 1]) +
                        command.op_code.to_bytes(2, "little"))
        if local is None:
            return
        # Secure Simple Pairing on this air always yields a P-256 (Secure
        # Connections) key, which a host requires to be used with AES-CCM.
        state = 0x02 if enable else 0x00
        self._raw_event(0x08, bytes([0]) + handle.to_bytes(2, "little") +
                        bytes([state]))
        logger.info("%s: BR/EDR encryption %s on 0x%04x", self.name,
                    "on" if enable else "off", handle)
        self.link.encrypt_br(self, local.peer_address, state)

    def on_air_encryption_br(self, peer_address, state: int) -> None:
        mine = str(peer_address).split("/")[0]
        remote = next((c for c in self.classic_connections.values()
                       if str(c.peer_address).split("/")[0] == mine), None)
        if remote is not None:
            self._raw_event(0x08, bytes([0]) + remote.handle.to_bytes(2, "little") +
                            bytes([state]))

    def _read_encryption_key_size(self, command: hci.HCI_Command) -> None:
        handle = command.parameters[0:2]
        parameters = bytes([1]) + command.op_code.to_bytes(2, "little") + \
            bytes([0]) + handle + bytes([16])
        self._raw_event(0x0E, parameters)

    def on_hci_command_packet(self, command: hci.HCI_Command) -> None:
        self.commands.append(command.op_code)
        if command.op_code == 0x0413:
            self._classic_encryption(command)
            return
        if command.op_code == 0x1408:
            self._read_encryption_key_size(command)
            return
        logger.debug("%s: command 0x%04x %s", self.name, command.op_code, command.name)
        handler = getattr(self, f"on_{command.name.lower()}", None)
        if handler is not None and (command.op_code >> 10) != 0x3F:
            super().on_hci_command_packet(command)
            return
        extra = b""
        if (command.op_code >> 10) == 0x3F:
            self.vendor_commands.append(command.op_code)
            status = hci.HCI_ErrorCode.UNKNOWN_HCI_COMMAND_ERROR
        elif command.op_code in BENIGN_CONFIGURATION_OPCODES:
            status = hci.HCI_ErrorCode.SUCCESS
            extra = BENIGN_CONFIGURATION_OPCODES[command.op_code]
        else:
            self.unknown_commands.append(command.op_code)
            status = hci.HCI_ErrorCode.UNKNOWN_HCI_COMMAND_ERROR
            logger.info("%s: unsupported command 0x%04x", self.name, command.op_code)
        parameters = bytes([1, command.op_code & 0xFF, command.op_code >> 8,
                            int(status)]) + extra
        event = bytes([hci.HCI_EVENT_PACKET, hci.HCI_COMMAND_COMPLETE_EVENT,
                       len(parameters)]) + parameters
        if self.host:
            asyncio.get_running_loop().call_soon(self.host.on_packet, event)


class PacedSink:
    """Writes H4 packets to an emulated UART one at a time, with a gap.

    An emulated MCU consumes its UART through DMA and an idle-line interrupt;
    packets that arrive back to back in one TCP segment can be delivered
    faster than the modelled line lets the firmware see a frame boundary.
    Pacing keeps each packet a separate burst, as a real 115200-baud line
    would.
    """

    def __init__(self, writer, gap_s: float) -> None:
        self.writer = writer
        self.gap_s = gap_s
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task = asyncio.get_running_loop().create_task(self._drain())

    def on_packet(self, packet: bytes) -> None:
        self.queue.put_nowait(bytes(packet))

    async def _drain(self) -> None:
        while True:
            packet = await self.queue.get()
            self.writer.write(packet)
            await self.writer.drain()
            await asyncio.sleep(self.gap_s)


@dataclass
class Station:
    """Something attached to the air."""

    name: str
    address: str
    controller: AirController
    device: Device | None = None
    kind: str = "hci"
    extra: dict = field(default_factory=dict)


class Air:
    """Stations on one bw-air/1 hub; each station is its own hub node."""

    def __init__(self, hub: str = "127.0.0.1:7461") -> None:
        self.hub_host, port = hub.rsplit(":", 1)
        self.hub_port = int(port)
        self.stations: dict[str, Station] = {}

    async def _link(self, name: str) -> AirLink:
        link = AirLink(self.hub_host, self.hub_port, name)
        await link.connect()
        return link

    # -- emulated firmware whose UART is a TCP socket (Renode) --------------
    async def attach_hci_client(self, name: str, host: str, port: int,
                                address: str, retries: int = 1200,
                                gap_s: float = 0.02) -> Station:
        for attempt in range(retries):
            try:
                reader, writer = await asyncio.open_connection(host, port)
                break
            except OSError:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(0.05)
        return await self._attach_stream(name, reader, writer, address, "hci-client",
                                         PacedSink(writer, gap_s) if gap_s else None)

    # -- any HCI host that dials in -----------------------------------------
    async def serve_hci(self, port: int, address_for, host: str = "127.0.0.1"):
        counter = {"n": 0}

        async def accept(reader, writer):
            counter["n"] += 1
            name = f"hci-{port}-{counter['n']}"
            await self._attach_stream(name, reader, writer,
                                      address_for(counter["n"]), "hci-server")

        return await asyncio.start_server(accept, host, port)

    async def _attach_stream(self, name, reader, writer, address, kind,
                             sink=None) -> Station:
        link = await self._link(name)
        source = StreamPacketSource()
        sink = sink or StreamPacketSink(writer)
        controller = AirController(name, host_source=source, host_sink=sink,
                                   link=link, public_address=address)

        async def pump():
            try:
                while data := await reader.read(4096):
                    source.data_received(data)
            finally:
                logger.info("%s: HCI stream closed", name)
                link.remove_controller(controller)
                self.stations.pop(name, None)
                if link.writer is not None:
                    link.writer.close()

        station = Station(name, address, controller, kind=kind)
        station.extra["pump"] = asyncio.get_running_loop().create_task(pump())
        station.extra["link"] = link
        self.stations[name] = station
        logger.info("%s: attached %s at %s", name, kind, address)
        return station

    # -- in-process peer (tests, Scratch Link node) --------------------------
    async def add_peer(self, name: str, address: str,
                       classic: bool = True) -> Station:
        link = await self._link(name)
        controller = AirController(name, link=link, public_address=address)
        config = DeviceConfiguration(name=name, address=hci.Address(address),
                                     classic_enabled=classic)
        device = Device(config=config,
                        host=Host(controller, AsyncPipeSink(controller)))
        device.classic_enabled = classic
        await device.power_on()
        station = Station(name, address, controller, device, kind="peer")
        station.extra["link"] = link
        self.stations[name] = station
        return station

    async def remove(self, name: str) -> None:
        station = self.stations.pop(name, None)
        if station is not None and station.extra.get("link") is not None:
            link = station.extra["link"]
            link.remove_controller(station.controller)
            if link.writer is not None:
                link.writer.close()


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--air", default="127.0.0.1:7461", help="bw-air/1 hub")
    parser.add_argument("--renode-hci", action="append", default=[],
                        metavar="NAME=HOST:PORT@BDADDR",
                        help="attach an emulated UART exported as a TCP server")
    parser.add_argument("--hci-listen", type=int, action="append", default=[],
                        metavar="PORT",
                        help="accept HCI hosts (H4 over TCP); one controller each")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    air = Air(arguments.air)
    for spec in arguments.renode_hci:
        name, rest = spec.split("=", 1)
        endpoint, address = rest.split("@", 1)
        host, port = endpoint.rsplit(":", 1)
        await air.attach_hci_client(name, host, int(port), address)
    for port in arguments.hci_listen:
        await air.serve_hci(port, lambda n, p=port: f"02:B1:0E:{p >> 8:02X}:{p & 0xFF:02X}:{n:02X}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
