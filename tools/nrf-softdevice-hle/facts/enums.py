import re, sys, json
H = sys.argv[1]
defs = {}
out = {}
files = ['ble_ranges.h','nrf_sdm.h','nrf_mbr.h','nrf_soc.h','nrf_svc.h','ble.h','ble_gap.h','ble_gattc.h','ble_gatts.h','ble_l2cap.h','ble_types.h','nrf_error.h','ble_err.h','nrf_error_sdm.h','nrf_error_soc.h','ble_hci.h','ble_gatt.h']
def ev(expr):
    e = re.sub(r'/\*.*?\*/', '', expr).strip()
    e = re.sub(r'\b(0x[0-9A-Fa-f]+|\d+)[uUlL]+\b', r'\1', e)
    for k in sorted(defs, key=len, reverse=True):
        e = re.sub(r'\b%s\b' % re.escape(k), '(%d)' % defs[k], e)
    return int(eval(e, {}, {}))
for f in files:
    src = open(f'{H}/{f}').read().replace('\r', '')
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    for m in re.finditer(r'#define[ \t]+(\w+)[ \t]+([^\n]+)', src):
        try: defs[m.group(1)] = ev(m.group(2))
        except Exception: pass
    for m in re.finditer(r'enum\s+(\w*)\s*\{(.*?)\}', src, re.S):
        val = -1
        for item in m.group(2).split(','):
            item = item.strip()
            if not item: continue
            if '=' in item:
                n, e = item.split('=', 1); n = n.strip()
                try: val = ev(e)
                except Exception as x: print('skip', n, e, x, file=sys.stderr); continue
            else:
                n = item; val += 1
            defs[n] = val
            out[n] = {'value': val, 'enum': m.group(1), 'file': f}
json.dump({'enums': out, 'defines': {k: v for k, v in defs.items() if k not in out}}, open('s130-facts.json', 'w'), indent=1, sort_keys=True)
print(len(out), 'enum members')
