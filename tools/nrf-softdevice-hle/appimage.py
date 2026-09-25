#!/usr/bin/env python3
"""Extract ONLY the application region of a micro:bit / Calliope mini .hex.

Official MakeCode images carry Nordic's MBR, SoftDevice and (V2) bootloader.
Their licences restrict use to Nordic ICs and forbid disassembly, so this tool
never keeps a byte outside the application region: records below the app base
or at/after the app end (and UICR records) are counted and discarded unread.

Output: <out>.bin (app bytes, base = app_start, 0xFF gaps) and <out>.json
(the layout, the sha256 of the kept bytes, and per-range discard counts).

Layout facts (see PROVENANCE.md):
  v2       nRF52833 + S113: app 0x1C000 .. 0x77000 (bootloader at 0x77000)
  v1       nRF51822 + S110 v8: app 0x18000 .. 0x3C000 (bootloader at 0x3C000)
  calliope nRF51822 + S110 v8: as v1
Universal hex (micro:bit V1+V2) sections are selected by board id
(0x9900/0x9901 = V1, 0x9903/0x9904/0x9905/0x9906 = V2).
"""
import hashlib, json, sys, argparse

LAYOUTS = {
    'v2': dict(app_start=0x1C000, app_end=0x77000, chip='nrf52833', softdevice='S113'),
    'v1': dict(app_start=0x18000, app_end=0x3C000, chip='nrf51822', softdevice='S110v8'),
    'calliope': dict(app_start=0x18000, app_end=0x3C000, chip='nrf51822', softdevice='S110v8'),
}
V1_IDS = {0x9900, 0x9901}
V2_IDS = {0x9903, 0x9904, 0x9905, 0x9906}


def records(text):
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(':'):
            raise ValueError(f'line {n}: not an Intel hex record')
        raw = bytes.fromhex(line[1:])
        if sum(raw) & 0xFF:
            raise ValueError(f'line {n}: checksum')
        ln, addr, typ = raw[0], (raw[1] << 8) | raw[2], raw[3]
        yield typ, addr, raw[4:4 + ln]


def extract(text, variant):
    lay = LAYOUTS[variant]
    lo, hi = lay['app_start'], lay['app_end']
    app = bytearray(b'\xff' * (hi - lo))
    kept_max = lo
    dropped = {'below_app': 0, 'at_or_above_app_end': 0, 'outside_flash': 0}
    upper = 0
    universal = False
    section_ok = True          # plain hex: every section is ours
    for typ, addr, data in records(text):
        if typ == 0x04:
            upper = (data[0] << 24) | (data[1] << 16)
            continue
        if typ == 0x02:
            upper = ((data[0] << 8) | data[1]) << 4
            continue
        if typ == 0x0A:        # universal hex block start: board id
            universal = True
            bid = (data[0] << 8) | data[1]
            section_ok = (bid in V1_IDS) if variant == 'v1' else (bid in V2_IDS) if variant == 'v2' else False
            continue
        if typ in (0x0B, 0x0C, 0x0E, 0x03, 0x05, 0x01):
            continue
        if typ not in (0x00, 0x0D) or not section_ok:
            continue
        a = upper + addr
        if a >= 0x10000000:
            dropped['outside_flash'] += len(data)
            continue
        for i, b in enumerate(data):   # byte-exact split at the boundaries
            x = a + i
            if x < lo:
                dropped['below_app'] += 1
            elif x >= hi:
                dropped['at_or_above_app_end'] += 1
            else:
                app[x - lo] = b
                kept_max = max(kept_max, x + 1)
    if variant == 'calliope' and universal:
        raise ValueError('calliope images are plain hex; got a universal hex')
    body = bytes(app[:kept_max - lo])
    if len(body) < 8:
        raise ValueError('no application bytes found for this variant')
    sp, reset = int.from_bytes(body[0:4], 'little'), int.from_bytes(body[4:8], 'little')
    meta = dict(variant=variant, **lay, app_bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(), initial_sp=hex(sp), reset=hex(reset),
                universal_hex=universal, discarded_unread=dropped)
    return body, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('hex')
    ap.add_argument('variant', choices=sorted(LAYOUTS))
    ap.add_argument('out')
    a = ap.parse_args()
    body, meta = extract(open(a.hex).read(), a.variant)
    open(a.out + '.bin', 'wb').write(body)
    json.dump(meta, open(a.out + '.json', 'w'), indent=2)
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
