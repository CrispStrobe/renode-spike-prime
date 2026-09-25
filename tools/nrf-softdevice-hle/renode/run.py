#!/usr/bin/env python3
"""Run nRF51 S110 application regions in Renode with the SoftDevice emulated
at API level (SoftDeviceHle.cs -> libnrf_softdevice_hle.so).

  run.py --app A.bin [--app B.bin ...] --out /tmp/run [--secs 3] [--air 127.0.0.1:7461]
         [--gdb 3333] [--exectrace] [--press-a 1.5] [--radio-medium]

Each --app becomes one machine (mb0, mb1, ...). --radio-medium joins their
RADIO peripherals on one Renode wireless medium (MakeCode radio between them).
Heavy: serialised with flock on /tmp/claude-1000/renode.lock.
"""
import argparse, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RENODE = os.environ.get('RENODE', '/mnt/volume1/code/lego/wt-generic-current-upstream/renode')
LIB = os.environ.get('SDHLE_LIB', '/mnt/volume1/lw-sd-hle-target/release/libnrf_softdevice_hle.so')
LOCK = '/tmp/claude-1000/renode.lock'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app', action='append', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--secs', default='3')
    ap.add_argument('--air', default='')
    ap.add_argument('--gdb', type=int, default=0)
    ap.add_argument('--gdb-wait', action='store_true', help='start paused, run from GDB')
    ap.add_argument('--exectrace', action='store_true')
    ap.add_argument('--press-a', type=float, default=None, help='virtual seconds at which button A is pressed on mb0')
    ap.add_argument('--radio-medium', action='store_true')
    ap.add_argument('--extra', default='', help='monitor lines appended before running')
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = [f'include @{HERE}/SoftDeviceHle.cs', f'include @{HERE}/NrfNvmc.cs', f'include @{HERE}/NrfTimer.cs']
    if a.radio_medium:
        L.append('emulation CreateBLEMedium "air"')
    for i, app in enumerate(a.app):
        app = os.path.abspath(app)
        body = open(app, 'rb').read(8)
        sp, pc = struct.unpack('<II', body)
        name = f'mb{i}'
        addr = f'C0:EE:AA:BB:CC:{i + 1:02X}'
        L += [
            f'mach create "{name}"',
            f'machine LoadPlatformDescription @{HERE}/nrf51822-app.repl',
            f'machine LoadPlatformDescriptionFromString "sd: Miscellaneous.SoftDeviceHle @ sysbus <0x0, +0x18000> {{ size: 0x18000; library: \\"{LIB}\\"; node: \\"{name}\\"; address: \\"{addr}\\"; air: \\"{a.air}\\"; tracePath: \\"{out}.{name}.svc.jsonl\\" }}"',
            f'sysbus LoadBinary @{app} 0x18000',
            'sd Attach cpu 0x18000',
            f'cpu SP 0x{sp:x}',
            f'cpu PC 0x{pc & ~1:x}',
            f'uart0 CreateFileBackend @{out}.{name}.uart true',
        ]
        if a.radio_medium:
            L.append(f'connector Connect sysbus.radio air')
        if a.exectrace:
            L.append(f'cpu CreateExecutionTracing "tr" @{out}.{name}.exectrace PC')
        if a.gdb and i == 0:
            L.append(f'machine StartGdbServer {a.gdb}')
    L.append(f'logFile @{out}.log')
    if a.press_a is not None:
        L += ['mach set "mb0"', f'emulation RunFor "{a.press_a}"', 'sysbus.gpio0 OnGPIO 17 false',
              'emulation RunFor "0.3"', 'sysbus.gpio0 OnGPIO 17 true']
    if a.extra:
        L += a.extra.split(';')
    if a.gdb_wait:
        L.append('start')
    else:
        n = max(1, int(float(a.secs) / 0.5))
        for _ in range(n):
            L += [f'emulation RunFor "{float(a.secs) / n}"'] + [f'mach set "mb{i}"\nsysbus.cpu PC' for i in range(len(a.app))]
        L += ['quit']
    resc = out + '.resc'
    open(resc, 'w').write('\n'.join(L) + '\n')
    for i in range(len(a.app)):
        for ext in ('svc.jsonl', 'uart', 'exectrace'):
            p = f'{out}.mb{i}.{ext}'
            if os.path.exists(p):
                os.remove(p)
    cmd = ['flock', LOCK, '/usr/bin/time', '-f', 'wall=%e maxrss_kb=%M', 'timeout', '1800', RENODE,
           '--disable-gui', '--console', '--plain', resc]
    with open(out + '.console', 'w') as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    print(open(out + '.console').read().strip().splitlines()[-1])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
