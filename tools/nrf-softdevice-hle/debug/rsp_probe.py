#!/usr/bin/env python3
"""Minimal GDB Remote Serial Protocol client (no ARM gdb needed on the box):
set a breakpoint in MakeCode user code, continue, read registers and a PXT
global, and probe the Nordic ranges.

  rsp_probe.py --port 3333 --bp 0x35xxx [--hits 3] [--global-index 3] [--probe 0x0 0x1000 0x3c000]

Works against Renode's `machine StartGdbServer` and labwired's gdbstub.
A PXT number is stored tagged: (v << 1) | 1.
"""
import argparse, socket, struct, sys, time


def rle(p):
    # GDB run-length encoding: X*n repeats X (ord(n) - 29) more times.
    out, i = [], 0
    while i < len(p):
        if p[i] == '*' and out:
            out.append(out[-1] * (ord(p[i + 1]) - 29))
            i += 2
        else:
            out.append(p[i])
            i += 1
    return ''.join(out)


def word(h):
    return 0 if 'x' in h else struct.unpack('<I', bytes.fromhex(h))[0]


class Rsp:
    def __init__(self, port, host='127.0.0.1', timeout=600):
        for _ in range(300):
            try:
                self.s = socket.create_connection((host, port), timeout=timeout)
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit(f'no GDB server on {host}:{port}')
        self.buf = b''
        self.s.sendall(b'+')

    def _read_packet(self):
        while True:
            while b'#' not in self.buf or len(self.buf) < self.buf.index(b'#') + 3:
                d = self.s.recv(65536)
                if not d:
                    raise EOFError
                self.buf += d
            i = self.buf.find(b'$')
            j = self.buf.index(b'#', i)
            pkt = self.buf[i + 1:j]
            self.buf = self.buf[j + 3:]
            self.s.sendall(b'+')
            return rle(pkt.decode(errors='replace'))

    def cmd(self, c):
        body = c.encode()
        self.s.sendall(b'$' + body + b'#' + b'%02x' % (sum(body) & 0xFF))
        while True:
            p = self._read_packet()
            if p.startswith('O') and len(p) > 1 and all(ch in '0123456789abcdef' for ch in p[1:]):
                continue   # console output
            return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=3333)
    ap.add_argument('--bp', required=True)
    ap.add_argument('--hits', type=int, default=3)
    ap.add_argument('--global-index', type=int, default=3, help='PXT global slot (word) of the variable')
    ap.add_argument('--probe', nargs='*', default=['0x0', '0x1000', '0x3000', '0x17ffc'])
    a = ap.parse_args()
    r = Rsp(a.port)
    print('stop reason on attach:', r.cmd('?'))
    bp = int(a.bp, 16)
    print(f'Z0 {bp:#x}:', r.cmd(f'Z0,{bp:x},2'))
    for hit in range(a.hits):
        stop = r.cmd('c')
        g = r.cmd('g')
        regs = [word(g[8 * i:8 * i + 8]) for i in range(16)]
        r6 = regs[6]
        ctx = r.cmd(f'm{r6:x},4')
        globals_ptr = struct.unpack('<I', bytes.fromhex(ctx))[0] if len(ctx) == 8 else None
        val = None
        if globals_ptr:
            w = r.cmd(f'm{globals_ptr + 4 * a.global_index:x},4')
            raw = struct.unpack('<I', bytes.fromhex(w))[0]
            val = (raw >> 1) if raw & 1 else f'boxed {raw:#x}'
        print(f'hit {hit + 1}: stop {stop}  pc={regs[15]:#x} sp={regs[13]:#x} lr={regs[14]:#x} r6(ctx)={r6:#x} '
              f'globals={globals_ptr:#x} -> n = {val}')
    print(f'z0 {bp:#x}:', r.cmd(f'z0,{bp:x},2'))
    for p in a.probe:
        addr = int(p, 16)
        m = r.cmd(f'm{addr:x},16')
        print(f'read 16 bytes at {addr:#x} (Nordic range): {m!r}')
    app = r.cmd('m18000,8')
    print(f'read 8 bytes at 0x18000 (application vector table): {app!r}')
    try:
        r.cmd('D')
    except Exception:
        pass


if __name__ == '__main__':
    main()
