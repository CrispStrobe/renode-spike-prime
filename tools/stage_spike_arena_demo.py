#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Stage source-authored demo and state adapter for build-pinned desktop use."""
import argparse
import hashlib
import json
import pathlib
import shutil

def stage(root, firmware, executable, destination):
    # No download or arbitrary monitor command. Inputs are local build artifacts.
    firmware, executable, destination = [pathlib.Path(p).resolve() for p in (firmware, executable, destination)]
    if any(char in str(destination) for char in '\n\r\t;"@'):
        raise ValueError('output path is not a supported monitor path')
    if destination.exists():
        raise ValueError('choose a new output directory; existing packages are never overwritten')
    data = firmware.read_bytes()
    if len(data) < 52 or len(data) > 1024 * 1024 or data[:6] != b'\x7fELF\x01\x01' or data[18:20] != b'\x28\x00':
        raise ValueError('expected bounded little-endian ARM ELF32 from our arena demo')
    destination.mkdir(parents=True)
    (destination/'scripts').mkdir(); (destination/'tools').mkdir()
    (destination/'licenses').mkdir()
    shutil.copy2(root/'LICENSE', destination/'licenses/renode-MIT.txt')
    shutil.copy2(root/'licenses/arena-BSD-3-Clause.txt', destination/'licenses/arena-BSD-3-Clause.txt')
    files = ['scripts/spike-state-server.py', 'tools/spike_state_monitor_protocol.py',
             'tools/ev3_state_observer.py', 'tools/spike_arena_inputs.py', 'tools/spike_arena_mailbox.py']
    for name in files: shutil.copy2(root/name, destination/name)
    shutil.copy2(firmware, destination/'arena-demo.elf')
    (destination/'arena-demo.repl').write_text('using "platforms/cpus/stm32f4.repl"\nsramUpper: Memory.MappedMemory @ sysbus 0x20040000\n    size: 0x10000\n')
    if any(char in str(destination) for char in '\n\r\t;"@'):
        raise ValueError('output path is not a supported monitor path')
    (destination/'arena-demo.resc').write_text('mach create\nmachine LoadPlatformDescription @'+str(destination/'arena-demo.repl').replace(' ', '\\ ')+'\n')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (destination/'state-config.json').write_text(json.dumps({'identity': {'board':'spike-prime',
        'firmware':'brickwright-arena-demo','transport':'none','imageSha256':digest(destination/'arena-demo.elf')}, 'paths':{}}, indent=2)+'\n')
    pins = {'BW_RENODE_EXECUTABLE':str(executable),'BW_RENODE_SHA256':digest(executable), 'BW_RENODE_SPIKE_ROOT':str(destination)}
    for name, file in [('SCENARIO','arena-demo.resc'),('FIRMWARE','arena-demo.elf'),('STATE_SCRIPT','scripts/spike-state-server.py'),('STATE_CONFIG','state-config.json')]:
        p=destination/file; pins['BW_RENODE_SPIKE_'+name]=str(p);pins['BW_RENODE_SPIKE_'+name+'_SHA256']=digest(p)
    (destination/'manifest.json').write_text(json.dumps({str(p.relative_to(destination)):digest(p)
        for p in sorted(destination.rglob('*')) if p.is_file()},indent=2)+'\n')
    pins['BW_RENODE_SPIKE_MANIFEST'] = str(destination/'manifest.json')
    pins['BW_RENODE_SPIKE_MANIFEST_SHA256'] = digest(destination/'manifest.json')
    (destination/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    return pins

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',required=True);parser.add_argument('--executable',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    stage(pathlib.Path(__file__).resolve().parents[1],args.firmware,args.executable,args.output)
