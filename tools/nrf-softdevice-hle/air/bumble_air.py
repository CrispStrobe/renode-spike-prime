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
and the reverse for messages from the hub.

  python bumble_air.py central --air 127.0.0.1:7461 --target C0:EE:AA:BB:CC:01 --send "hello"
      A virtual phone: scans, connects, pairs (Just Works), discovers the
      micro:bit UART service, subscribes to TX and writes lines to RX.
Requires: pip install bumble (Apache-2.0).
"""
import argparse, asyncio, json, logging, sys, time

from bumble import hci, ll
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
        if self.find_le_controller(destination_address) or transport != PhysicalTransport.LE:
            return super().send_acl_data(sender, destination_address, transport, data)
        self._send({'t': 'acl', 'src': str(sender.random_address), 'dst': str(destination_address), 'data': bytes(data).hex()})

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
    await dev.power_on()
    t0 = time.monotonic()
    ev = lambda *x: print(f'[{time.monotonic() - t0:7.2f}s]', *x, flush=True)
    seen = asyncio.get_running_loop().create_future()

    def on_adv(adv):
        if str(adv.address).split('/')[0] == a.target.upper() and not seen.done():
            ev('advertisement from', adv.address, 'data', bytes(adv.data).hex() if hasattr(adv, 'data') else '')
            seen.set_result(adv)
    dev.on('advertisement', on_adv)
    await dev.start_scanning(filter_duplicates=True)
    await asyncio.wait_for(seen, a.timeout)
    await dev.stop_scanning()
    conn = await asyncio.wait_for(dev.connect(addr(a.target), timeout=a.timeout), a.timeout)
    ev('connected', conn)
    if not a.no_pair:
        await asyncio.wait_for(conn.pair(), a.timeout)
        ev('paired; encrypted =', conn.is_encrypted)
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
    ap.add_argument('--log', default='')
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    if a.v:
        logging.basicConfig(level=logging.DEBUG)
    sys.exit(asyncio.run(central(a)))


if __name__ == '__main__':
    main()
