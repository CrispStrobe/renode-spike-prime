#!/usr/bin/env python3
"""bumble <-> bw-air/1: a bumble LocalLink whose far side is the air hub.

Any bumble Controller on an `AirLink` shares the virtual air with every other
hub node: an emulated micro:bit (nrf-softdevice-hle), another bumble device, a
SPIKE hub whose HCI stream is fed to a bumble Controller, a browser tab.

Mapping (bumble 0.0.235 link API -> AIR.md messages):
  send_advertising_pdu(AdvInd/AdvNonConnInd) -> {"t":"adv"}
  send_advertising_pdu(ConnectInd)            -> {"t":"connect_ind"}
  send_acl_data(dst, LE, l2cap_frame)         -> {"t":"acl"}
  send_ll_control_pdu(EncReq/StartEncRsp/TerminateInd/RejectExtInd/FeatureReq/Rsp) -> {"t":"ll"}
  send_lmp_packet(dst, lmp.Packet)            -> {"t":"lmp"}      (BR/EDR)
  send_acl_data(dst, BR_EDR, l2cap_frame)     -> {"t":"acl_br"}   (BR/EDR)
  encrypt_br(dst, state)                      -> {"t":"enc_br"}   (BR/EDR)
and the reverse for messages from the hub. Controllers on the same AirLink
talk directly (bumble's LocalLink); anything else goes through the hub.

  python bumble_air.py central --air 127.0.0.1:7461 --target C0:EE:AA:BB:CC:01 --send "hello"
      A virtual phone: scans, connects, pairs (Just Works), discovers the
      micro:bit UART service, subscribes to TX and writes lines to RX.
Requires: pip install bumble (Apache-2.0).
"""
import argparse, asyncio, json, logging, sys, time

from bumble import hci, ll, lmp
from bumble.core import PhysicalTransport
from bumble.controller import Controller
from bumble.device import Device, Peer
from bumble.host import Host
from bumble.link import LocalLink
from bumble.transport.common import AsyncPipeSink
from bumble.pairing import PairingConfig, PairingDelegate

UART_SERVICE = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E'
UART_TX = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'   # micro:bit -> central (indicate)
UART_RX = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'   # central -> micro:bit (write)


def addr(s):
    return hci.Address(s) if '/' in s else hci.Address(s, hci.Address.RANDOM_DEVICE_ADDRESS)


def lmp_bytes(packet):
    # bumble's lmp.Packet.__bytes__ uses a cached payload that is empty for a
    # packet built from fields, so serialize the fields explicitly.
    if packet.fields:
        return bytes(packet.opcode) + hci.HCI_Object.dict_to_bytes(packet.__dict__, packet.fields)
    return bytes(packet)


def lmp_from_bytes(data):
    # bumble's Opcode.parse_from unpacks the whole buffer for an escaped
    # (two-byte) opcode, which fails whenever parameters follow.
    if data[0] in (124, 127):
        opcode, offset = lmp.Opcode(int.from_bytes(data[0:2], 'big')), 2
    else:
        opcode, offset = lmp.Opcode(data[0]), 1
    subclass = lmp.Packet.subclasses.get(opcode)
    if subclass is None:
        packet = lmp.Packet()
        packet.opcode = opcode
    else:
        packet = subclass(**hci.HCI_Object.dict_from_bytes(data, offset, subclass.fields))
    packet.payload = data[offset:]
    return packet


class AirLink(LocalLink):
    def __init__(self, host, port, node):
        super().__init__()
        self.host, self.port, self.node = host, port, node
        self.writer = None
        self.log = []

    async def connect(self):
        r, self.writer = await asyncio.open_connection(self.host, self.port)
        self._send({'t': 'hello', 'node': self.node, 'kind': 'bumble', 'proto': 'bw-air/1'})
        asyncio.get_running_loop().create_task(self._reader(r))

    def _send(self, m):
        self.log.append(('tx', m))
        self.writer.write((json.dumps(m) + '\n').encode())

    async def _reader(self, r):
        while True:
            line = await r.readline()
            if not line:
                return
            try:
                m = json.loads(line)
            except ValueError:
                continue
            self.log.append(('rx', m))
            self._from_air(m)

    # ---- bumble -> air ----
    def send_advertising_pdu(self, sender, packet):
        super().send_advertising_pdu(sender, packet)
        if isinstance(packet, ll.ConnectInd):
            self._send({'t': 'connect_ind', 'initiator': str(packet.initiator_address), 'advertiser': str(packet.advertiser_address),
                        'interval': packet.interval, 'latency': packet.latency, 'timeout': packet.timeout})
        elif isinstance(packet, (ll.AdvInd, ll.AdvNonConnInd)):
            self._send({'t': 'adv', 'addr': str(packet.advertiser_address), 'pdu': 'adv_ind' if isinstance(packet, ll.AdvInd) else 'adv_nonconn_ind',
                        'data': bytes(packet.data).hex(), 'scan_rsp': ''})

    def send_acl_data(self, sender, destination_address, transport, data):
        if transport == PhysicalTransport.BR_EDR:
            if self.find_classic_controller(destination_address):
                return super().send_acl_data(sender, destination_address, transport, data)
            self._send({'t': 'acl_br', 'src': str(sender.public_address), 'dst': str(destination_address),
                        'data': bytes(data).hex()})
            return
        # The source is the address the sender uses on this connection. bumble
        # uses the controller's random address, which a host advertising with
        # its public identity (the SPIKE firmware) never sets.
        connection = sender.le_connections.get(destination_address)
        source = connection.self_address if connection is not None else sender.random_address
        local = self.find_le_controller(destination_address)
        if local is not None:
            asyncio.get_running_loop().call_soon(
                lambda: local.on_link_acl_data(source, transport, data))
            return
        self._send({'t': 'acl', 'src': str(source), 'dst': str(destination_address), 'data': bytes(data).hex()})

    def send_lmp_packet(self, sender, receiver_address, packet):
        if self.find_classic_controller(receiver_address):
            return super().send_lmp_packet(sender, receiver_address, packet)
        self._send({'t': 'lmp', 'src': str(sender.public_address), 'dst': str(receiver_address),
                    'data': lmp_bytes(packet).hex()})

    def encrypt_br(self, sender, receiver_address, state):
        """BR/EDR link encryption changed (0 off, 1 E0, 2 AES-CCM). The air
        carries no cipher; the peer's controller reports the same state."""
        local = self.find_classic_controller(receiver_address)
        if local is not None:
            local.on_air_encryption_br(sender.public_address, state)
            return
        self._send({'t': 'enc_br', 'src': str(sender.public_address), 'dst': str(receiver_address),
                    'state': state})

    def send_ll_control_pdu(self, sender_address, receiver_address, packet):
        if self.find_le_controller(receiver_address):
            return super().send_ll_control_pdu(sender_address, receiver_address, packet)
        m = {'t': 'll', 'src': str(sender_address), 'dst': str(receiver_address), 'error_code': 0, 'rand': '', 'ediv': 0, 'ltk': ''}
        if isinstance(packet, ll.EncReq):
            m.update(op='enc_req', rand=bytes(packet.rand).hex(), ediv=packet.ediv, ltk=bytes(packet.ltk).hex())
        elif isinstance(packet, ll.StartEncRsp):
            m.update(op='start_enc_rsp')
        elif isinstance(packet, ll.TerminateInd):
            m.update(op='terminate_ind', error_code=int(packet.error_code))
        elif isinstance(packet, ll.RejectExtInd):
            m.update(op='reject_ext_ind', error_code=int(packet.error_code))
        elif isinstance(packet, ll.FeatureReq):
            m.update(op='feature_req')
        elif isinstance(packet, ll.FeatureRsp):
            m.update(op='feature_rsp')
        else:
            return
        self._send(m)

    # ---- air -> bumble ----
    def _from_air(self, m):
        t = m.get('t')
        loop = asyncio.get_running_loop()
        if t == 'adv':
            cls = ll.AdvInd if m.get('pdu') == 'adv_ind' else ll.AdvNonConnInd
            pdu = cls(advertiser_address=addr(m['addr']), data=bytes.fromhex(m.get('data', '')))
            for c in self.controllers:
                loop.call_soon(c.on_ll_advertising_pdu, pdu)
        elif t == 'connect_ind':
            pdu = ll.ConnectInd(initiator_address=addr(m['initiator']), advertiser_address=addr(m['advertiser']),
                                interval=m.get('interval', 24), latency=m.get('latency', 0), timeout=m.get('timeout', 400))
            for c in self.controllers:
                loop.call_soon(c.on_ll_advertising_pdu, pdu)
        elif t == 'acl':
            c = self.find_le_controller(addr(m['dst']))
            if c:
                loop.call_soon(c.on_link_acl_data, addr(m['src']), PhysicalTransport.LE, bytes.fromhex(m['data']))
        elif t == 'acl_br':
            c = self.find_classic_controller(addr(m['dst']))
            if c:
                loop.call_soon(c.on_link_acl_data, addr(m['src']), PhysicalTransport.BR_EDR, bytes.fromhex(m['data']))
        elif t == 'lmp':
            c = self.find_classic_controller(addr(m['dst']))
            if c:
                pdu = lmp_from_bytes(bytes.fromhex(m['data']))
                loop.call_soon(c.on_lmp_packet, addr(m['src']), pdu)
        elif t == 'enc_br':
            c = self.find_classic_controller(addr(m['dst']))
            if c and hasattr(c, 'on_air_encryption_br'):
                loop.call_soon(c.on_air_encryption_br, addr(m['src']), m.get('state', 0))
        elif t == 'll':
            c = self.find_le_controller(addr(m['dst']))
            if not c:
                return
            op = m.get('op')
            pdu = {'start_enc_rsp': lambda: ll.StartEncRsp(),
                   'terminate_ind': lambda: ll.TerminateInd(m.get('error_code', 0x13)),
                   'reject_ext_ind': lambda: ll.RejectExtInd(ll.ControlPdu.Opcode.LL_ENC_REQ, m.get('error_code', 6)),
                   'enc_req': lambda: ll.EncReq(rand=bytes.fromhex(m.get('rand', '')), ediv=m.get('ediv', 0), ltk=bytes.fromhex(m.get('ltk', ''))),
                   'feature_req': lambda: ll.FeatureReq(feature_set=bytes(8)),
                   'feature_rsp': lambda: ll.FeatureRsp(feature_set=bytes(8))}.get(op)
            if pdu:
                loop.call_soon(c.on_ll_control_pdu, addr(m['src']), pdu())


async def central(a):
    link = AirLink(*a.air.rsplit(':', 1), node=a.node)
    link.port = int(link.port)
    await link.connect()
    ctrl = Controller('phone', link=link, public_address='F0:F1:F2:F3:F4:F5')
    dev = Device(name='virtual-phone', address=hci.Address('F0:F1:F2:F3:F4:F5'), host=Host(ctrl, AsyncPipeSink(ctrl)))
    dev.pairing_config_factory = lambda conn: PairingConfig(sc=False, mitm=False, bonding=True,
                                                             delegate=PairingDelegate(io_capability=PairingDelegate.NO_OUTPUT_NO_INPUT))
    from bumble.keys import MemoryKeyStore
    dev.keystore = MemoryKeyStore()
    await dev.power_on()
    t0 = time.monotonic()
    ev = lambda *x: print(f'[{time.monotonic() - t0:7.2f}s]', *x, flush=True)
    seen = asyncio.get_running_loop().create_future()
    # --min-advs N: let the board advertise N times before the first connect.
    # Advertising runs on the board's emulated clock, so this waits in
    # EMULATED time whatever the emulator's speed (a wall-clock sleep does
    # not): e.g. 200 ms advertising in micro:bit pairing mode, 20 = 4 s.
    advs, need = 0, a.min_advs
    # Local name to ignore (the pairing-mode one, after bonding).
    skip_name = None
    first_name = None

    def local_name(data):
        # AD structures: len, type, payload; 0x08 shortened / 0x09 complete name.
        i = 0
        while i < len(data) and data[i]:
            n, t = data[i], data[i + 1] if i + 1 < len(data) else 0
            if t in (0x08, 0x09):
                return bytes(data[i + 2:i + 1 + n])
            i += 1 + n
        return None

    def on_adv(adv):
        nonlocal seen, advs, first_name
        if str(adv.address).split('/')[0] == a.target.upper() and not seen.done():
            data = bytes(adv.data) if hasattr(adv, 'data') else b''
            name = local_name(data)
            if skip_name is not None and name == skip_name:
                return
            advs += 1
            if advs < need:
                return
            if first_name is None:
                first_name = name
            ev('advertisement from', adv.address, 'name', name, 'data', data.hex(), f'(#{advs})')
            seen.set_result(adv)
    dev.on('advertisement', on_adv)
    await dev.start_scanning(filter_duplicates=a.min_advs <= 1)
    await asyncio.wait_for(seen, a.timeout)
    await dev.stop_scanning()
    conn = await asyncio.wait_for(dev.connect(addr(a.target), timeout=a.timeout), a.timeout)
    ev('connected', conn)
    if not a.no_pair:
        await asyncio.wait_for(conn.pair(), a.timeout)
        ev('paired; encrypted =', conn.is_encrypted)
    if a.pair_then_reconnect:
        # micro:bit DAL pairing mode: after bonding the board shows a tick and
        # resets; it then advertises (whitelisted) as the MakeCode program.
        gone = asyncio.get_running_loop().create_future()
        conn.on('disconnection', lambda *_: gone.done() or gone.set_result(True))
        await asyncio.wait_for(gone, a.timeout)
        ev('disconnected (board resets after bonding)')
        # Stay away while the board shows its tick (15 s virtual): a new
        # connection attempt restarts its pairing-mode timer.
        await asyncio.sleep(a.reconnect_delay)
        # The DAL shows a tick for 15 s (virtual) and then resets into the
        # program, now advertising to bonded peers only. Until then it may
        # still accept a connection in pairing mode without the key loaded:
        # retry until the bonded key encrypts the link.
        deadline = time.monotonic() + a.timeout
        # Do not connect while the board is still in pairing mode: every
        # connection there re-enters the DAL's pairing flow (and a connection
        # that lands during its 15 s tick delays the reset into the program).
        # The program advertises under a DIFFERENT local name (pairing mode
        # appends the friendly name, "BBC micro:bit [tezut]"), so wait, in
        # emulated time, until the name changes; then --reconnect-min-advs
        # more advertisements under the new name, so the program has added its
        # own services before discovery.
        skip_name = first_name
        advs, need = 0, a.reconnect_min_advs
        while True:
            seen = asyncio.get_running_loop().create_future()
            await dev.start_scanning(filter_duplicates=False)
            await asyncio.wait_for(seen, max(1, deadline - time.monotonic()))
            await dev.stop_scanning()
            conn = await asyncio.wait_for(dev.connect(addr(a.target), timeout=a.timeout), a.timeout)
            ev('reconnected', conn)
            try:
                await asyncio.wait_for(conn.encrypt(), 30)
                ev('encrypted with the bonded key =', conn.is_encrypted)
                # Still the pairing-mode GATT (the board has not reset into
                # the program yet)? Its table has no UART service: retry.
                probe = Peer(conn)
                await asyncio.wait_for(probe.discover_services(), a.timeout)
                if any(str(s.uuid).upper() == UART_SERVICE for s in probe.services):
                    break
                raise RuntimeError('no UART service yet')
            except Exception as e:
                # Reached when encryption fails or the table is still the
                # pairing-mode one; with the name gate above that should not
                # happen on the DAL, and polling is the fallback.
                ev('not ready (', type(e).__name__, e, ') - board not reset into the program yet, retrying')
                try:
                    await conn.disconnect()
                except Exception:
                    pass
                if time.monotonic() > deadline:
                    raise
                await asyncio.sleep(5)
    peer = Peer(conn)
    await asyncio.wait_for(peer.discover_services(), a.timeout)
    for s in peer.services:
        ev('service', s.uuid)
    svc = [s for s in peer.services if str(s.uuid).upper() == UART_SERVICE]
    if not svc:
        ev('no UART service')
        return 2
    await asyncio.wait_for(peer.discover_characteristics(service=svc[0]), a.timeout)
    tx = [c for c in svc[0].characteristics if str(c.uuid).upper() == UART_TX][0]
    rx = [c for c in svc[0].characteristics if str(c.uuid).upper() == UART_RX][0]
    got = []
    await asyncio.wait_for(peer.discover_descriptors(tx), a.timeout)
    await peer.subscribe(tx, lambda v: (got.append(bytes(v)), ev('UART TX <-', bytes(v))), prefer_notify=False)
    ev('subscribed to UART TX')
    for line in a.send:
        await rx.write_value((line + '\n').encode(), with_response=True)
        ev('UART RX ->', (line + '\n').encode())
        await asyncio.sleep(a.gap)
    await asyncio.sleep(a.gap)
    ev('received', b''.join(got))
    await conn.disconnect()
    if a.log:
        with open(a.log, 'w') as f:
            for d, m in link.log:
                f.write(json.dumps({'dir': d, 'msg': m}) + '\n')
    return 0 if got else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['central'])
    ap.add_argument('--air', default='127.0.0.1:7461')
    ap.add_argument('--node', default='virtual-phone')
    ap.add_argument('--target', required=True)
    ap.add_argument('--send', action='append', default=[])
    ap.add_argument('--gap', type=float, default=3.0)
    ap.add_argument('--timeout', type=float, default=120.0)
    ap.add_argument('--no-pair', action='store_true')
    ap.add_argument('--min-advs', type=int, default=1,
                    help='advertisements to see before the first connect (emulated-time wait)')
    ap.add_argument('--reconnect-delay', type=float, default=0.0, help='wall seconds to wait after the post-bonding disconnect')
    ap.add_argument('--reconnect-min-advs', type=int, default=1,
                    help='advertisements to see before reconnecting after the bonding reset (emulated-time wait)')
    ap.add_argument('--pair-then-reconnect', action='store_true',
                    help='pair (board in pairing mode), wait for its reset, reconnect encrypted with the bond')
    ap.add_argument('--log', default='')
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    if a.v:
        logging.basicConfig(level=logging.DEBUG)
    sys.exit(asyncio.run(central(a)))


if __name__ == '__main__':
    main()
