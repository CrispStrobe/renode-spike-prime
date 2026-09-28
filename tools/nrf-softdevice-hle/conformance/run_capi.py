#!/usr/bin/env python3
"""Run the nrf-softdevice-hle conformance vectors through the C ABI — the
exact library and entry points Renode's SoftDeviceHle.cs P/Invokes.

  run_capi.py [--lib libnrf_softdevice_hle.so] [--vectors DIR]

The vectors live with the core (labwired-core crates/nrf-softdevice-hle/
conformance/*.json); the Rust test runs the same files through the Host trait.
"""
import argparse, ctypes, glob, json, os, sys

DEF_LIB = os.environ.get('SDHLE_LIB') or os.path.join(os.environ.get('CARGO_TARGET_DIR', 'target'), 'release', 'libnrf_softdevice_hle.so')
DEF_VEC = '/mnt/volume1/code/wt/lw-sd-hle/crates/nrf-softdevice-hle/conformance'

READ = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)
WRITE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)
NOW = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_void_p)


class HostStruct(ctypes.Structure):
    _fields_ = [('ctx', ctypes.c_void_p), ('read', READ), ('write', WRITE), ('nvic', ctypes.c_void_p), ('now', NOW)]


class Mem:
    """Guest memory as Renode presents it: app flash + 16 KB RAM + NVIC set/clear registers."""
    def __init__(self):
        self.m = {}
        self.iser = self.ispr = 0
        self.ipr = bytearray(32)
        self.now = 0

    @staticmethod
    def mapped(a):
        return 0x18000 <= a < 0x3C000 or 0x20000000 <= a < 0x20004000

    def read(self, a, n):
        if a in (0xE000E100, 0xE000E180):
            return self.iser.to_bytes(4, 'little')[:n]
        if a in (0xE000E200, 0xE000E280):
            return self.ispr.to_bytes(4, 'little')[:n]
        if 0xE000E400 <= a < 0xE000E420:
            return bytes(self.ipr[a - 0xE000E400:a - 0xE000E400 + n])
        if not all(self.mapped(a + i) for i in range(n)):
            return None
        return bytes(self.m.get(a + i, 0) for i in range(n))

    def write(self, a, data):
        if 0xE000E000 <= a < 0xE000F000:
            v = int.from_bytes(data, 'little')
            if a == 0xE000E100: self.iser |= v
            elif a == 0xE000E180: self.iser &= ~v
            elif a == 0xE000E200: self.ispr |= v
            elif a == 0xE000E280: self.ispr &= ~v
            elif 0xE000E400 <= a < 0xE000E420: self.ipr[a - 0xE000E400:a - 0xE000E400 + 4] = data
            return True
        if not all(self.mapped(a + i) for i in range(len(data))):
            return False
        for i, b in enumerate(data):
            self.m[a + i] = b
        return True


def num(v):
    return v if isinstance(v, int) else int(v, 16)


def subset(want, got):
    return all(got.get(k) == v for k, v in want.items())


def run(lib, path):
    v = json.load(open(path))
    mem = Mem()
    for m in v['memory']:
        mem.write(num(m['addr']), bytes.fromhex(m['hex']))

    @READ
    def rd(ctx, a, buf, n):
        b = mem.read(a, n)
        if b is None:
            return 0
        ctypes.memmove(buf, b, n)
        return 1

    @WRITE
    def wr(ctx, a, buf, n):
        return 1 if mem.write(a, ctypes.string_at(buf, n)) else 0

    @NOW
    def now(ctx):
        return mem.now

    host = HostStruct(None, rd, wr, None, now)
    sd = lib.sdhle_new(b'dut', b'C0:EE:AA:BB:CC:DD', b'mem')
    out = []
    buf = ctypes.create_string_buffer(8192)
    try:
        for i, s in enumerate(v['steps']):
            at = f"{v['name']} step {i}"
            for m in s.get('mem_write', []):
                mem.write(num(m['addr']), bytes.fromhex(m['hex']))
            if 'air_in' in s:
                assert lib.sdhle_air_inject(sd, json.dumps(s['air_in']).encode()) == 1, at + ': inject'
            if 'svc' in s:
                a = [num(x) for x in s['args']]
                r = lib.sdhle_svc(sd, num(s['svc']), a[0], a[1], a[2], a[3], host)
                if r != num(s['ret']):
                    return f"{at}: svc {s['svc']} returned {r:#x}, want {num(s['ret']):#x}"
            for _ in range(s.get('poll_ms', 0)):
                mem.now += 1000
                lib.sdhle_poll(sd, host)
            while lib.sdhle_air_take(sd, buf, len(buf)) > 0:
                out.append(json.loads(buf.value))
            for w in s.get('air_out', []):
                idx = next((j for j, g in enumerate(out) if subset(w, g)), None)
                if idx is None:
                    return f'{at}: no air message matching {w}; got {out}'
                del out[:idx + 1]
            for m in s.get('mem', []):
                want = bytes.fromhex(m['hex'])
                got = mem.read(num(m['addr']), len(want))
                if got != want:
                    return f"{at}: memory at {m['addr']}: {got.hex() if got else None}, want {want.hex()}"
            if 'expect_irq_pending' in s and not (mem.ispr >> num(s['expect_irq_pending'])) & 1:
                return f"{at}: IRQ {s['expect_irq_pending']} not pending"
    finally:
        lib.sdhle_free(sd)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lib', default=DEF_LIB)
    ap.add_argument('--vectors', default=DEF_VEC)
    a = ap.parse_args()
    lib = ctypes.CDLL(a.lib)
    lib.sdhle_new.restype = ctypes.c_void_p
    lib.sdhle_new.argtypes = [ctypes.c_char_p] * 3
    lib.sdhle_free.argtypes = [ctypes.c_void_p]
    lib.sdhle_svc.restype = ctypes.c_uint32
    lib.sdhle_svc.argtypes = [ctypes.c_void_p, ctypes.c_uint8] + [ctypes.c_uint32] * 4 + [HostStruct]
    lib.sdhle_poll.argtypes = [ctypes.c_void_p, HostStruct]
    lib.sdhle_air_inject.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.sdhle_air_take.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    files = sorted(glob.glob(os.path.join(a.vectors, '*.json')))
    if len(files) < 5:
        print(f'expected the conformance vectors in {a.vectors}, found {len(files)}')
        return 2
    fails = [e for e in (run(lib, f) for f in files) if e]
    for e in fails:
        print('FAIL', e)
    print(f'{len(files) - len(fails)} of {len(files)} vectors pass through the C ABI ({a.lib})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
