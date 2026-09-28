import subprocess, struct, re, json
# read our own object's .rodata/.data and relocations to rebuild the table
sec = {}
out = subprocess.run(['arm-none-eabi-objdump', '-s', '-j', '.rodata', '-j', '.rodata.str1.1', 'layout.o'], capture_output=True, text=True).stdout
cur = None
for l in out.splitlines():
    m = re.match(r'Contents of section (\S+):', l)
    if m: cur = m.group(1); sec[cur] = bytearray(); continue
    m = re.match(r' [0-9a-f]+ ((?:[0-9a-f]{2,8} ){1,4})', l + ' ')
    if m and cur:
        sec[cur] += bytes.fromhex(m.group(1).replace(' ', ''))
relo = subprocess.run(['arm-none-eabi-objdump', '-r', '-j', '.rodata', 'layout.o'], capture_output=True, text=True).stdout
rel = {}
for l in relo.splitlines():
    m = re.match(r'([0-9a-f]+) R_ARM_ABS32\s+(\S+)', l)
    if m: rel[int(m.group(1), 16)] = m.group(2)
ro = sec['.rodata']; strs = sec.get('.rodata.str1.1', b'')
res = {}
for i in sorted(rel):
    ptr, off, size = struct.unpack_from('<IHH', ro, i)
    sym = rel.get(i)
    if not sym: continue
    base = 0
    m = re.match(r'\.LC(\d+)', sym)
    name = strs[ptr:strs.index(b'\0', ptr)].decode() if sym.startswith('.rodata.str1.1') else None
    if name is None: continue
    res[name] = {'offset': None if off == 0xFFFF else off, 'size': size}
json.dump(res, open('s130-layout.json', 'w'), indent=1)
for k, v in res.items(): print(k, v)
