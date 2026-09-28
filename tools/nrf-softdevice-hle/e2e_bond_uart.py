#!/usr/bin/env python3
"""End to end: bond with an official MakeCode micro:bit V1 image, reset, reconnect
encrypted with the stored bond, and round-trip lines over the Nordic UART service.

Everything runs locally: the bw-air hub (../bw-air/airhub.py), the board on
labwired (crates/core/examples/sd_hle_run.rs of labwired-core, the SoftDevice
emulated by crates/nrf-softdevice-hle), and a Bumble virtual phone
(../bw-air/bumble_air.py central). The phone:

  1. waits for the board in DAL pairing mode (buttons A+B held from reset,
     `--pair-ms`) and pairs, LE legacy Just Works, bonding;
  2. waits for the board to drop the link, show its tick and reset into the
     program: it reconnects only once the advertised name has changed from
     the pairing-mode one, so no connection lands inside pairing mode;
  3. re-encrypts with the bonded LTK (a key the board had to write to flash
     and read back after the reset), subscribes to UART TX and sends lines.

Expectations (--expect):
  echo       every line comes back as "echo <line>" (programs/ble-uart-echo).
  panic:N    the phone reconnects after the bonding reset and the board
             enters the DAL's microbit_panic with code N. For
             programs/ble-uart-echo-icons on V1 this is 20 (out of memory,
             at the bonded reconnection): see programs/README.md for the
             heap numbers.

Exit status 0 = expectation met, 1 = not met, 2 = setup error.

  cargo build --release -p labwired-core --features event-scheduler --example sd_hle_run
  python3 e2e_bond_uart.py --sd-hle-run $CARGO_TARGET_DIR/release/examples/sd_hle_run \\
      --program ble-uart-echo --app /tmp/ble-uart-echo.v1.bin --out /tmp/e2e

--program NAME checks the image's sha256 against programs/manifest.json (so a
pass is a pass for THAT build) and takes --expect from it; programs/README.md
has the recipe that builds the images.

The phone needs Bumble (pip install bumble); pass --phone-python if it lives in
a venv. The emulator runs at about 0.1-0.2x real time on a small host, so a
run takes several minutes of wall time for a minute of emulated time.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AIR = os.path.join(HERE, '..', 'bw-air')
ADDR = 'C0:EE:AA:BB:CC:01'
LINES = ['hello', 'microbit', 'third']

# microbit_panic(int) in the MakeCode V1 DAL (microbit-dal v2.2.0-rc6, MIT):
# push {r4-r7,lr}; sub sp,#84; movs r2,#24; movs r1,#0; movs r0... (the
# memset of its local image). Found once per image; r0 at entry is the code.
PANIC_PROLOGUE = bytes.fromhex('f0b595b01822002106000ea8')
APP_BASE = 0x18000


def find_panic(app):
    b = open(app, 'rb').read()
    hits = []
    i = b.find(PANIC_PROLOGUE)
    while i != -1:
        hits.append(APP_BASE + i)
        i = b.find(PANIC_PROLOGUE, i + 1)
    return hits


def wait_port(port, secs=60):
    t = time.time() + secs
    while time.time() < t:
        try:
            socket.create_connection(('127.0.0.1', port), 1).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sd-hle-run', required=True, help='labwired-core examples/sd_hle_run binary')
    ap.add_argument('--app', required=True, help='application region (.bin at 0x18000)')
    ap.add_argument('--program', help='a name from programs/manifest.json: checks the sha256, supplies --expect')
    ap.add_argument('--expect', help="'echo' or 'panic:N'")
    ap.add_argument('--out', default='/tmp/e2e-bond-uart')
    ap.add_argument('--port', type=int, default=7491, help='air hub TCP port (WebSocket = port+1)')
    ap.add_argument('--emu-ms', type=int, default=60000, help='emulated time to run the board for')
    ap.add_argument('--phone-python', default=sys.executable, help='python with bumble installed')
    ap.add_argument('--reconnect-min-advs', type=int, default=10,
                    help='program advertisements to see before reconnecting (emulated-time wait)')
    ap.add_argument('--dump-ram-at-panic', metavar='PATH',
                    help='write the 16 KB of RAM when microbit_panic is entered (for a heap walk)')
    a = ap.parse_args()

    sha = hashlib.sha256(open(a.app, 'rb').read()).hexdigest()
    print(f'app {a.app} sha256 {sha}')
    if a.program:
        progs = json.load(open(os.path.join(HERE, 'programs', 'manifest.json')))['programs']
        if a.program not in progs:
            ap.error(f'--program: not in programs/manifest.json: {sorted(progs)}')
        if progs[a.program]['app_bin_sha256'] != sha:
            print(f"setup: {a.app} is not the recorded {a.program} build ({progs[a.program]['app_bin_sha256']})")
            return 2
        a.expect = a.expect or progs[a.program]['expect']
    if not a.expect:
        ap.error('--expect or --program is required')
    m = re.fullmatch(r'echo|panic:(\d+)', a.expect)
    if not m:
        ap.error("--expect must be 'echo' or 'panic:N'")
    want_panic = int(m.group(1)) if m.group(1) else None
    panics = find_panic(a.app)
    if len(panics) != 1:
        print(f'setup: expected one microbit_panic prologue in {a.app}, found {[hex(p) for p in panics]}')
        return 2
    panic_pc = panics[0]
    os.makedirs(a.out, exist_ok=True)
    procs = []

    def stop_all():
        for p in reversed(procs):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(20)
            except subprocess.TimeoutExpired:
                p.kill()

    try:
        hub = subprocess.Popen([sys.executable, os.path.join(AIR, 'airhub.py'), '--tcp', f'127.0.0.1:{a.port}',
                                '--ws', f'127.0.0.1:{a.port + 1}', '--log', os.path.join(a.out, 'air.jsonl')],
                               stdout=open(os.path.join(a.out, 'hub.out'), 'w'), stderr=subprocess.STDOUT)
        procs.append(hub)
        if not wait_port(a.port):
            print('setup: the air hub did not come up')
            return 2
        emu_log = os.path.join(a.out, 'board.log')
        emu = subprocess.Popen([a.sd_hle_run, '--app', a.app, '--ms', str(a.emu_ms), '--pair-ms', '3000',
                                '--air', f'127.0.0.1:{a.port}', '--node', 'mb0', '--addr', ADDR,
                                '--trace', os.path.join(a.out, 'svc.jsonl'), '--watch', hex(panic_pc)]
                               + (['--dump-ram-at', f'{panic_pc:#x}:{a.dump_ram_at_panic}'] if a.dump_ram_at_panic else []),
                               stdout=subprocess.DEVNULL, stderr=open(emu_log, 'w'))
        procs.append(emu)
        timeout = a.emu_ms // 1000 * 15
        phone_log = os.path.join(a.out, 'phone.log')
        cmd = [a.phone_python, os.path.join(AIR, 'bumble_air.py'), 'central', '--air', f'127.0.0.1:{a.port}',
               '--target', ADDR, '--pair-then-reconnect', '--reconnect-min-advs', str(a.reconnect_min_advs),
               '--gap', '5', '--timeout', str(timeout), '--log', os.path.join(a.out, 'phone-link.jsonl')]
        for line in LINES:
            cmd += ['--send', line]
        phone = subprocess.Popen(cmd, stdout=open(phone_log, 'w'), stderr=subprocess.STDOUT)
        procs.append(phone)

        panic_re = re.compile(r'\[watch\] 0x%x .*? r0=(0x[0-9a-f]+)' % panic_pc)
        panic_code = None
        deadline = time.time() + timeout + 120
        while time.time() < deadline:
            txt = open(emu_log, errors='replace').read()
            mm = panic_re.search(txt)
            if mm:
                panic_code = int(mm.group(1), 16)
                break
            if phone.poll() is not None or emu.poll() is not None:
                break
            time.sleep(2)
        if panic_code is not None:
            # The board panicked; let the phone's log catch up with what it
            # already did (it runs on wall time, the board on emulated time).
            t = time.time() + 60
            while time.time() < t and phone.poll() is None and \
                    'reconnected' not in open(phone_log, errors='replace').read():
                time.sleep(1)
        if panic_code is None and phone.poll() is None:
            try:
                phone.wait(max(1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                pass
        stop_all()
        phone_txt = open(phone_log, errors='replace').read()
        subscribed = 'subscribed to UART TX' in phone_txt
        rebonded = 'encrypted with the bonded key = True' in phone_txt
        reconnected = 'reconnected' in phone_txt
        print(f'reconnected: {reconnected}; bonded encryption: {rebonded}; subscribed to UART TX: {subscribed}; '
              f'panic: {panic_code if panic_code is not None else "none"} (microbit_panic at {panic_pc:#x})')
        if want_panic is None:
            echoes = [f'echo {line}' for line in LINES]
            got = [e for e in echoes if e in phone_txt.replace('\\r\\n', '\n')]
            print(f'echoes back: {len(got)}/{len(echoes)}')
            ok = rebonded and subscribed and panic_code is None and got == echoes and phone.returncode == 0
        else:
            ok = reconnected and panic_code == want_panic
        print('PASS' if ok else f'FAIL (logs in {a.out})')
        return 0 if ok else 1
    finally:
        stop_all()


if __name__ == '__main__':
    sys.exit(main())
