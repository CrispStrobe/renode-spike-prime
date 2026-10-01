# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Fixed-address ABI for our simulation-only Cortex-M arena demonstration."""
import struct
import sys
from spike_arena_inputs import validate_arena_inputs

BASE = 0x20040000
SIZE = 84
SIGNATURE = 0x42574152

def read_state(read_bytes, read_word):
    for unused in range(3):
        inputs_before = int(read_word(BASE + 12))
        before = int(read_word(BASE + 72))
        raw = bytearray(read_bytes(BASE, SIZE))
        data = struct.unpack('<21i', bytes(raw) if sys.version_info[0] >= 3 else str(raw))
        after = int(read_word(BASE + 72))
        inputs_after = int(read_word(BASE + 12))
        if not ((before | inputs_before) & 1) and before == after == data[18] and inputs_before == inputs_after == data[3]:
            if data[0] != SIGNATURE or data[1] != 1:
                raise ValueError('arena guest has not initialized its mailbox')
            if not 0 <= data[2] <= 3601000:
                raise ValueError('arena guest time exceeds its supported demonstration interval')
            return data
    raise ValueError('arena guest frame changed during observation')

def write_inputs(arguments, read_word, write_word):
    inputs = validate_arena_inputs(arguments)
    writes = []
    roles = {'C': 'color', 'D': 'distance', 'E': 'force'}
    for sensor in inputs['sensors']:
        if roles.get(sensor['port']) != sensor['kind']:
            raise ValueError('arena demo mounts color C, distance D and force E')
        values = sensor['values']
        if sensor['kind'] == 'distance': writes.append((16, values['distanceMillimeters']))
        elif sensor['kind'] == 'color':
            writes.extend([(20, values['colorId']), (24, values['reflectionPercent']), (28, values['ambientPercent'])])
        else: writes.extend([(32, values['forcePercent']), (36, int(values['pressed']))])
    for motor in inputs['loads']:
        if motor['port'] not in ('A', 'B'): raise ValueError('arena demo drives motor A and B')
        writes.append((40 if motor['port'] == 'A' else 44, motor['percent']))
    # Reject unavailable or uninitialized guests before making any write.
    if int(read_word(BASE)) != SIGNATURE or int(read_word(BASE + 4)) != 1:
        raise ValueError('arena guest has not initialized its mailbox')
    seq = int(read_word(BASE + 12))
    if seq & 1: raise ValueError('arena input frame is already being written')
    write_word(BASE + 12, (seq + 1) & 0xffffffff)
    for offset, value in writes: write_word(BASE + offset, value & 0xffffffff)
    write_word(BASE + 12, (seq + 2) & 0xffffffff)


def snapshot(data, identity, seq, generation):
    target = dict(identity)
    target['capabilities'] = ['arena-inputs/v1', 'arena-clock/v1', 'guest-motor-output/v1', 'state-sample/v1']
    target['limitations'] = ['bounded ARM arena demonstration, not full NuttX or SPIKE API compatibility',
                             'synthetic motor and sensor units, not physical calibration']
    return {'schemaVersion': 1, 'type': 'snapshot', 'seq': seq, 'clockNs': data[2] * 1000000,
            'target': target, 'lifecycle': {'phase': 'ready', 'generation': 0, 'connectionGeneration': generation},
            'ports': [{'id': p, 'attached': True, 'kind': k} for p, k in
                      [('A', 'motor'), ('B', 'motor'), ('C', 'color'), ('D', 'distance'), ('E', 'force')]],
            'motors': [{'port': 'A', 'position': data[12] / 1000.0, 'speed': data[14] / 3.0,
                        'speedDps': data[14], 'demandDirection': -1 if data[19] < 0 else int(data[19] > 0), 'stalled': bool(data[16])},
                       {'port': 'B', 'position': data[13] / 1000.0, 'speed': data[15] / 3.0,
                        'speedDps': data[15], 'demandDirection': -1 if data[20] < 0 else int(data[20] > 0), 'stalled': bool(data[17])}],
            'sensors': [{'port': 'C', 'kind': 'color', 'values': {'colorId': data[5], 'reflectionPercent': data[6], 'ambientPercent': data[7]}},
                        {'port': 'D', 'kind': 'distance', 'values': {'distanceMillimeters': data[4]}},
                        {'port': 'E', 'kind': 'force', 'values': {'forcePercent': data[8], 'pressed': bool(data[9])}}],
            'display': {'width': 0, 'height': 0, 'pixels': []}, 'buttons': {}, 'battery': {'percent': 100, 'millivolts': 8400},
            'power': {'state': 'on', 'chargerConnected': False}, 'imu': {'acceleration': {}, 'angularVelocity': {}},
            'audio': {'active': False, 'bufferedBytes': 0}, 'storage': {'ready': False},
            'bluetooth': {'state': 'unavailable', 'transport': 'none'}}
