#!/usr/bin/env python3
"""bw-air/1 hub: the one virtual 2.4 GHz air every simulated node shares.

A node (an emulated micro:bit's SoftDevice HLE, a Renode RADIO bridge, a
bumble controller for the SPIKE hub or a virtual phone, a browser tab of lite)
connects and exchanges newline-delimited JSON objects (AIR.md). The hub is a
broadcast medium: every message a node sends is delivered to every other node;
receivers filter by destination address, frequency and access address, as
radios do. Nothing is interpreted here except `hello` (the node's name, for
the log).

  airhub.py [--tcp 127.0.0.1:7461] [--ws 127.0.0.1:7462] [--log air.jsonl]

TCP carries newline-delimited JSON; the WebSocket port carries one JSON object
per text frame (for browsers). Standard library only.
"""
import argparse, asyncio, base64, hashlib, json, struct, sys, time

nodes = {}          # writer-like -> name
log_file = None
t0 = time.monotonic()


class TcpPort:
    def __init__(self, w):
        self.w = w

    def send(self, line):
        try:
            self.w.write(line.encode() + b'\n')
        except Exception:
            pass


class WsPort:
    def __init__(self, w):
        self.w = w

    def send(self, line):
        data = line.encode()
        n = len(data)
        hdr = bytes([0x81, n]) if n < 126 else (bytes([0x81, 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x81, 127]) + struct.pack('>Q', n))
        try:
            self.w.write(hdr + data)
        except Exception:
            pass


def deliver(src, line):
    try:
        msg = json.loads(line)
    except ValueError:
        return
    if msg.get('t') == 'hello':
        nodes[src] = msg.get('node', '?')
    if log_file:
        log_file.write(json.dumps({'t_ms': round((time.monotonic() - t0) * 1000, 1), 'from': nodes.get(src, '?'), 'msg': msg}) + '\n')
        log_file.flush()
    for port in list(nodes):
        if port is not src:
            port.send(line)


async def tcp_client(r, w):
    port = TcpPort(w)
    nodes[port] = '?'
    try:
        while True:
            line = await r.readline()
            if not line:
                break
            line = line.decode(errors='replace').strip()
            if line:
                deliver(port, line)
    except ConnectionError:
        pass  # a node that vanished is the same as one that left
    finally:
        nodes.pop(port, None)
        w.close()


async def ws_client(r, w):
    req = b''
    while b'\r\n\r\n' not in req:
        chunk = await r.read(1024)
        if not chunk:
            return
        req += chunk
    key = None
    for l in req.decode(errors='replace').split('\r\n'):
        if l.lower().startswith('sec-websocket-key:'):
            key = l.split(':', 1)[1].strip()
    if not key:
        w.close()
        return
    acc = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    w.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
             f'Sec-WebSocket-Accept: {acc}\r\n\r\n').encode())
    port = WsPort(w)
    nodes[port] = '?'
    try:
        while True:
            h = await r.readexactly(2)
            op, n = h[0] & 0x0F, h[1] & 0x7F
            if n == 126:
                n = struct.unpack('>H', await r.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', await r.readexactly(8))[0]
            mask = await r.readexactly(4) if h[1] & 0x80 else b'\0\0\0\0'
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(await r.readexactly(n)))
            if op == 8:
                break
            if op == 1:
                deliver(port, data.decode(errors='replace'))
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        nodes.pop(port, None)
        w.close()


async def main():
    global log_file
    ap = argparse.ArgumentParser()
    ap.add_argument('--tcp', default='127.0.0.1:7461')
    ap.add_argument('--ws', default='127.0.0.1:7462')
    ap.add_argument('--log', default='')
    a = ap.parse_args()
    if a.log:
        log_file = open(a.log, 'w')
    h, p = a.tcp.rsplit(':', 1)
    s1 = await asyncio.start_server(tcp_client, h, int(p))
    servers = [s1]
    if a.ws:
        h2, p2 = a.ws.rsplit(':', 1)
        servers.append(await asyncio.start_server(ws_client, h2, int(p2)))
    print(f'bw-air/1 hub: tcp {a.tcp}' + (f', ws {a.ws}' if a.ws else ''), flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
