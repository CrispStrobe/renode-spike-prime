#!/usr/bin/env python3
"""A stand-in for the micro:bit application, driving the SoftDevice HLE's C
ABI the way the DAL does (UART service: TX indicate, RX write), with no
emulator. Used to test the air hub + bumble central + SMP path on their own:

  airhub.py &  fake_app.py --air 127.0.0.1:7461 &  bumble_air.py central --target C0:EE:AA:BB:CC:01 --send hi
"""
import argparse, ctypes, sys, time
sys.path.insert(0, __file__.rsplit('/', 2)[0] + '/conformance')
from run_capi import HostStruct, Mem, READ, WRITE, NOW, DEF_LIB  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--air', default='127.0.0.1:7461')
    ap.add_argument('--addr', default='C0:EE:AA:BB:CC:01')
    ap.add_argument('--secs', type=float, default=60)
    a = ap.parse_args()
    lib = ctypes.CDLL(DEF_LIB)
    lib.sdhle_new.restype = ctypes.c_void_p
    lib.sdhle_new.argtypes = [ctypes.c_char_p] * 3
    lib.sdhle_svc.restype = ctypes.c_uint32
    lib.sdhle_svc.argtypes = [ctypes.c_void_p, ctypes.c_uint8] + [ctypes.c_uint32] * 4 + [HostStruct]
    lib.sdhle_poll.argtypes = [ctypes.c_void_p, HostStruct]
    mem = Mem()
    rd = READ(lambda c, ad, b, n: (ctypes.memmove(b, mem.read(ad, n), n), 1)[1] if mem.read(ad, n) is not None else 0)
    wr = WRITE(lambda c, ad, b, n: 1 if mem.write(ad, ctypes.string_at(b, n)) else 0)
    nw = NOW(lambda c: mem.now)
    host = HostStruct(None, rd, wr, None, nw)
    sd = lib.sdhle_new(b'fake-microbit', a.addr.encode(), a.air.encode())
    svc = lambda n, *args: lib.sdhle_svc(sd, n, *(list(args) + [0] * (4 - len(args))), host)
    R = 0x20002000
    W = lambda ad, hx: mem.write(ad, bytes.fromhex(hx))
    le = lambda v, n=4: v.to_bytes(n, 'little').hex()
    assert svc(0x10) == 0 and svc(0x60, R) == 0
    W(R + 0x10, '9ECADC240EE5A9E093F3A3B50000406E')
    assert svc(0x63, R + 0x10, R + 0x30) == 0
    W(R + 0x40, '0100' + '0200')
    svc(0xA0, 1, R + 0x40, R + 0x44)
    shandle = int.from_bytes(mem.read(R + 0x44, 2), 'little')
    # attr md: encryption required (sm1 lv2 = 0x21) like the micro:bit's default
    W(R + 0x50, '2121' + '03')          # vlen, vloc stack
    W(R + 0x54, '2121' + '02')          # cccd md
    def char(uuid16, props, out):
        W(R + 0x60, le(uuid16, 2) + '0200')
        W(R + 0x70, le(props, 1) + '00' * 19 + le(R + 0x54) + '00' * 4)
        W(R + 0x90, le(R + 0x60) + le(R + 0x50) + '0000' + '0000' + '1400' + '0000' + le(R + 0xB0))
        assert svc(0xA2, shandle, R + 0x70, R + 0x90, out) == 0
        return int.from_bytes(mem.read(out, 2), 'little')
    tx = char(0x0002, 0x20, R + 0xC0)   # indicate
    rx = char(0x0003, 0x0C, R + 0xC8)   # write, write without response
    W(R + 0x100, '020106' + '0d09' + b'BBC micro:bit'.hex()[:24])
    svc(0x72, R + 0x100, 17, 0, 0)
    W(R + 0x140, '00' * 16 + 'a000' + '0000' + '00' * 4)
    assert svc(0x73, R + 0x140) == 0
    print(f'fake micro:bit {a.addr}: UART service {shandle}, TX {tx}, RX {rx}; advertising', flush=True)
    end = time.time() + a.secs
    pending = b''
    while time.time() < end:
        mem.now += 1000
        lib.sdhle_poll(sd, host)
        while True:
            W(R + 0x200, '0001')
            if svc(0x61, R + 0x210, R + 0x200) != 0:
                break
            ev = mem.read(R + 0x210, int.from_bytes(mem.read(R + 0x200, 2), 'little'))
            eid = int.from_bytes(ev[0:2], 'little')
            print(f'  event {eid:#x} {ev.hex()}', flush=True)
            if eid == 0x13:     # sec params request: reply Just Works, bond, keyset
                W(R + 0x300, '01' + '07' + '10' + '01' + '00')
                W(R + 0x320, '00' * 24)
                svc(0x7F, 0, 0, R + 0x300, R + 0x320)
            if eid == 0x50:     # write
                h = int.from_bytes(ev[6:8], 'little')
                n = int.from_bytes(ev[4 + 2 + 24:4 + 2 + 26], 'little')
                data = ev[4 + 2 + 26:4 + 2 + 26 + n]
                if h == rx:
                    pending += data
                    if pending.endswith(b'\n'):
                        reply = b'echo ' + pending
                        pending = b''
                        W(R + 0x400, reply.hex())
                        W(R + 0x3F0, le(len(reply), 2))
                        W(R + 0x3E0, le(tx, 2) + '02' + '00' + '0000' + '0000' + le(R + 0x3F0) + le(R + 0x400))
                        print('  hvx ->', reply, hex(svc(0xA6, 0, R + 0x3E0)), flush=True)
        time.sleep(0.001)


if __name__ == '__main__':
    main()
