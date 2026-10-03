#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Qualify a caller-supplied MicroPython Prime application offline in Renode.

Direct application entry and UART qualification; no USB/bootloader claim.
All image bytes, flash seeds, monitor scripts and results remain private.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from spike_local_image import read_image, vectors, stage_platform
from spike_micropython_filesystem import build_seed

BOOT = (b"# SPDX-License-Identifier: BSD-3-Clause\n"
        b"# Copyright (c) 2026 Brickwright contributors\n"
        b"import os, machine\n"
        b"os.dupterm(machine.UART(2, 115200), 0)\n"
        b"print('BW_MICRO_READY')\n")


def monitor_path(path):
    value = str(path.resolve())
    if any(c.isspace() or c in "\"';" for c in value):
        raise ValueError("unsupported monitor path characters")
    return "@" + value


def send_uart(data):
    lines = []
    for offset in range(0, len(data), 32):
        chunk = list(data[offset:offset + 32])
        lines += ["python \"from System import Byte; u=self.Machine['sysbus.usart2']; "
                  "[u.WriteChar(Byte(v)) for v in " + str(chunk) + "]\"",
                  'emulation RunFor "0.001"']
    return lines


def observe_motor(directory, name, seconds):
    target = directory / (name + '.json')
    return ['emulation RunFor "' + str(seconds) + '"',
            "python \"import json; m=externals['portA'].Device; f=open('" + str(target) +
            "','w'); json.dump({'power':int(m.Power),'position':float(m.PositionDegrees),"
            "'speed':float(m.AngularVelocityDegreesPerSecond),'stalled':bool(m.Stalled)},f);f.close()\""]


def run_phase(args, directory, memory, seed, reboot=False):
    directory.mkdir(mode=0o700)
    platform = stage_platform(args.platform_root.resolve(), directory, 50000000, 1)
    clock = directory / "platforms/cpus/stm32f413vg.repl"
    source, matches = re.subn(r"(?m)^(    systickFrequency:) [0-9]+$",
                             r"\1 100000000", clock.read_text())
    if matches != 1:
        raise ValueError("MicroPython profile requires one Prime SysTick override")
    # This explicit application profile uses the board's 100 MHz HCLK and
    # timer inputs, rather than the retained NuttX profile's 96 MHz clocks.
    source = source.replace('PerformanceInMips: 96', 'PerformanceInMips: 100')
    source = source.replace('frequency: 96000000', 'frequency: 100000000')
    clock.write_text(source)
    start, end = min(memory), max(memory) + 1
    image = directory / "image.bin"
    image.write_bytes(bytes(memory.get(address, 255) for address in range(start, end)))
    flash = directory / "seed.bin"
    flash.write_bytes(seed)
    sp, pc = vectors(memory, 0x08010000)
    uart = directory / "uart.txt"
    saved = directory / "saved.bin"
    lines = ["include " + monitor_path(p) for p in args.model_source]
    lines += ['mach create', 'machine LoadPlatformDescription ' + monitor_path(platform)]
    if args.motor_test:
        lines += ['emulation CreatePrimeElectricalPorts "machine-0"']
    lines += ['sysbus LoadBinary ' + monitor_path(image) + ' ' + hex(start),
              "python \"from System import Array, Byte; b=bytearray(open('" + str(flash) +
              "','rb').read()); self.Machine['sysbus.spi2.primeStorageMux.primeStorage']."
              "UnderlyingMemory.WriteBytes(0x100000,Array[Byte](b),len(b))\"",
              'usart2 CreateFileBackend ' + monitor_path(uart),
              'cpu VectorTableOffset 0x08010000', 'cpu SP ' + hex(sp), 'cpu PC ' + hex(pc),
              "python \"from Antmicro.Renode.Peripherals.CPU import RegisterValue; "
              "self.Machine['sysbus.cpu'].SetRegister(0,RegisterValue.Create(1,32))\"",
              'emulation RunFor "1"']
    commands = [b'import trial\r'] if reboot else [
        b"print('BW_ARITH',6*7)\r", b"exec('while True: pass')\r", b'\x03',
        b"print('BW_AFTER',sum(range(10)))\r", b'f=open("trial.py","w")\r',
        b'f.write("print(81)\\n");f.close()\r', b'import os;os.sync()\r', b'import trial\r']
    for command in commands:
        lines += send_uart(command) + ['emulation RunFor "0.01"']
    if args.motor_test and not reboot:
        lines += observe_motor(directory, 'motor-initial', 0.01)
        for command in [b'from machine import Pin\r', b'from pyb import Timer\r',
                        b'b=Pin("PORTA_M2",Pin.OUT,value=1)\r', b't=Timer(1,freq=1000)\r',
                        b'c=t.channel(1,Timer.PWM_INVERTED,pin=Pin("PORTA_M1"),pulse_width_percent=50)\r']:
            lines += send_uart(command)
        lines += observe_motor(directory, 'motor-drive', 0.1)
        lines += ["python \"from System import Byte; externals['portA'].Device.SetLoad(Byte(100))\""]
        lines += observe_motor(directory, 'motor-stall', 0.1)
        lines += ["python \"from System import Byte; externals['portA'].Device.SetLoad(Byte(0))\""]
        lines += observe_motor(directory, 'motor-recover', 0.1)
        lines += send_uart(b'exec("try:\\n while True: pass\\nfinally:\\n t.deinit();Pin(\'PORTA_M1\',Pin.OUT,value=1)")\r')
        lines += observe_motor(directory, 'motor-loop', 0.01)
        lines += send_uart(b'\x03') + observe_motor(directory, 'motor-stop', 0.2)
        lines += send_uart(b'print("BW_MOTOR_DONE")\r') + ['emulation RunFor "0.01"']
    observation = directory / "cpu.json"
    lines += ["python \"import json; f=open('" + str(observation) + "','w'); "
              "json.dump({'pc':int(self.Machine['sysbus.cpu'].PC.RawValue),"
              "'sp':int(self.Machine['sysbus.cpu'].SP.RawValue),"
              "'instructions':int(self.Machine['sysbus.cpu'].ExecutedInstructions),"
              "'icsr':int(self.Machine['sysbus'].ReadDoubleWord(0xe000ed04))},f);f.close()\"",
              "python \"f=open('" + str(saved) + "','wb'); "
              "f.write(bytearray(self.Machine['sysbus.spi2.primeStorageMux.primeStorage']."
              "UnderlyingMemory.ReadBytes(0x100000,65536)));f.close()\"", 'quit', '']
    script = directory / "qualification.resc"
    script.write_text("\n".join(lines))
    command = [str(args.renode.resolve()), '--disable-xwt', '--console', '--plain', str(script)]
    (directory / "command.json").write_text(json.dumps(command))
    with (directory / "renode.log").open('wb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    log = (directory / "renode.log").read_text(errors='replace')
    if result.returncode or 'There was an error' in log or not observation.is_file():
        raise ValueError("Renode qualification failed; inspect private diagnostics")
    state = json.loads(observation.read_text())
    if (state['instructions'] <= 0 or not 0x20000000 < state['sp'] <= 0x20050000
            or state['sp'] % 8 or state['pc'] % 2 or state['pc'] not in memory
            or state['pc'] + 1 not in memory or 3 <= state['icsr'] & 0x1ff <= 6):
        raise ValueError("invalid final CPU observations")
    output = uart.read_bytes()
    expected = ([b'BW_MICRO_READY', b'>>> import trial\r\n81\r\n>>> '] if reboot else
                [b'BW_MICRO_READY', b'BW_ARITH 42', b'KeyboardInterrupt:', b'BW_AFTER 45',
                 b'>>> import trial\r\n81\r\n>>> '])
    cursor = 0
    for marker in expected:
        found = output.find(marker, cursor)
        if found < 0:
            raise ValueError("missing ordered console observation")
        cursor = found + len(marker)
    if not output.endswith(b'>>> ') or saved.stat().st_size != 65536:
        raise ValueError("console/flash qualification incomplete")
    if args.motor_test and not reboot:
        states = {name: json.loads((directory / ('motor-' + name + '.json')).read_text())
                  for name in ('initial', 'drive', 'stall', 'recover', 'loop', 'stop')}
        a, b, c, d = (states[name] for name in ('drive', 'stall', 'recover', 'stop'))
        if not (states['initial']['power'] == 0 and a['power'] == 50
                and a['speed'] > 0 and a['position'] > 0
                and b['stalled'] and b['speed'] == 0 and b['position'] == a['position']
                and c['speed'] > 0 and c['position'] > b['position']
                and states['loop']['power'] == 50 and d['power'] == 0 and d['speed'] == 0
                and b'BW_MOTOR_DONE\r\n>>> ' in output):
            raise ValueError("electrical motor observations failed")
    return saved.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--format', choices=('hex', 'raw'), required=True)
    parser.add_argument('--renode', type=Path, required=True)
    parser.add_argument('--model-source', type=Path, action='append', default=[])
    parser.add_argument('--platform-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--motor-test', action='store_true',
                        help='also qualify port A PWM, load/stall and authored finally cleanup using electrical port models')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        output = args.private_output.resolve()
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.chmod(0o700)
        if any(output.iterdir()):
            raise ValueError("private output must be empty; prior evidence is preserved")
        # Validate monitor strings before they can enter embedded Python commands.
        monitor_path(output)
        memory = read_image(args.image, args.format, 0x08010000)
        vectors(memory, 0x08010000)
        saved = run_phase(args, output / 'write', memory, build_seed({'boot.py': BOOT}))
        restored = run_phase(args, output / 'restore', memory, saved, reboot=True)
        if restored != saved:
            raise ValueError("restored filesystem changed unexpectedly")
        (output / 'result.json').write_text(json.dumps({'console': True, 'cancellation': True,
                                                      'writeFlushRestoreExecute': True,
                                                      'portAElectricalMotor': bool(args.motor_test)}))
        print('PASS: UART Python execution, cancellation, file write/flush and fresh-process restore.')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, 'Local MicroPython qualification failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
