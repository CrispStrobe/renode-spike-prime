# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded packet mailbox for our full firmware; no instruction execution here.

The base is resolved from our ELF's g_bw_program_debug symbol by the launcher.
Only that verified RAM mailbox is touched; no monitor text or addresses arrive
from the program client. Execution and time remain owned by NuttX/Renode.
"""
import struct
import sys

MAGIC = 0x42574e50
SIZE = 112
try:
    integer_types = (int, long)
except NameError:
    integer_types = (int,)


def validate_base(base):
    if isinstance(base, bool) or not isinstance(base, integer_types) or base % 4 or not 0x20020000 <= base <= 0x20040000 - SIZE:
        raise ValueError('invalid full-firmware mailbox')
    return base


def _header(base, read_word):
    validate_base(base)
    if int(read_word(base)) != MAGIC or int(read_word(base + 4)) != 1:
        raise ValueError('our full firmware has not initialized its packet mailbox')


def validate_packet(packet):
    if not isinstance(packet, (list, tuple, bytearray)) or not 8 <= len(packet) <= 20 or any(isinstance(v, bool) or not isinstance(v, integer_types) or not 0 <= v <= 255 for v in packet):
        raise ValueError('program packet must contain 8-20 bytes')
    packet = bytearray(packet)
    if packet[0] != 0x70 or packet[1] != 1 or packet[3] != 0:
        raise ValueError('unsupported program packet header')
    op = packet[2]
    if op not in range(8) or (op in (0, 7) and len(packet) != 16) or (op == 1 and not 11 <= len(packet) <= 20) or (op in (2, 3, 4, 5, 6) and len(packet) != 8):
        raise ValueError('unsupported program packet operation/length')
    if not any(packet[4:8]) and op != 5:
        raise ValueError('program id must be nonzero')
    return packet


def submit(base, packet, read_word, write_word):
    packet = validate_packet(packet)
    _header(base, read_word)
    if int(read_word(base + 60)) == 0:
        raise ValueError('full-firmware program worker is not ready')
    before = int(read_word(base + 8))
    if before & 1 or before != int(read_word(base + 36)):
        raise ValueError('a program packet is already pending')
    final = (before + 2) & 0xffffffff
    if final == 0:
        final = 2
    padded = packet + bytearray(20 - len(packet))
    write_word(base + 8, final - 1)
    write_word(base + 12, len(packet))
    for i in range(5):
        value = sum(int(padded[i * 4 + j]) << (j * 8) for j in range(4))
        write_word(base + 16 + i * 4, value)
    write_word(base + 8, final)
    return final


def reply(base, sequence, read_word, read_bytes):
    _header(base, read_word)
    if int(read_word(base + 36)) != sequence:
        return None
    packet = [int(v) for v in read_bytes(base + 40, 20)]
    if int(read_word(base + 36)) != sequence:
        return None
    if len(packet) != 20 or packet[0] != 0x71 or packet[1] != 1 or packet[2] > 7 or packet[3] > 5:
        raise ValueError('invalid full-firmware program reply')
    return packet


def status(base, read_word, read_bytes):
    _header(base, read_word)
    for unused in range(3):
        before = int(read_word(base + 60))
        if before == 0 or before & 1:
            continue
        raw = bytearray(read_bytes(base + 60, 52))
        words = struct.unpack('<6I6iI', bytes(raw) if sys.version_info[0] >= 3 else str(raw))
        if before != int(read_word(base + 60)) or before != words[0]:
            continue
        if words[2] > 5 or words[4] > 256 or words[12] not in (0, 1, 2, 3):
            raise ValueError('invalid full-firmware program status')
        return {'clockMs': words[1], 'state': words[2], 'id': words[3], 'pc': words[4],
                'error': words[5] if words[5] < 0x80000000 else words[5] - 0x100000000,
                'positions': list(words[6:8]), 'speeds': list(words[8:10]), 'duties': list(words[10:12]), 'validPorts': words[12]}
    raise ValueError('full-firmware publication is not ready or changed')


def validate_output_base(base):
    if isinstance(base, bool) or not isinstance(base, integer_types) or base % 4 or not 0x20020000 <= base <= 0x20040000 - 1036:
        raise ValueError('invalid full-firmware output buffer')
    return base


def output(base, read_word, read_bytes):
    validate_output_base(base)
    for unused in range(3):
        before = int(read_word(base))
        if before & 1:
            continue
        length, truncated = int(read_word(base + 4)), int(read_word(base + 8))
        if length > 1024 or truncated not in (0, 1):
            raise ValueError('invalid full-firmware output bounds')
        raw = bytearray(read_bytes(base + 12, length))
        if before == int(read_word(base)):
            return {'sequence': before, 'text': raw.decode('utf-8', 'replace'), 'truncated': bool(truncated)}
    raise ValueError('full-firmware publication is not ready or changed')
