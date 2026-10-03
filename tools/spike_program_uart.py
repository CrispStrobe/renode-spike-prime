# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Closed host commands for one native-owned, paced program UART external.

This adapter never opens a listener, advances time, or evaluates program text.
Generation correlates an attachment; it is not authentication.
"""
import re

try:
    integer_types = (int, long)
    string_types = (basestring,)
except NameError:
    integer_types = (int,)
    string_types = (str,)

COMMANDS = ('micropython.uart.write', 'micropython.uart.read', 'micropython.uart.close')
MAX_GENERATION = 9007199254740991


def _integer(value, minimum, maximum):
    return (isinstance(value, integer_types) and not isinstance(value, bool)
            and minimum <= value <= maximum)


def validate_binding_config(config):
    paths, identity = config['paths'], config['identity']
    present = 'programUart' in paths or 'programUartGeneration' in config
    micro = identity.get('firmware') == 'micropython-prime'
    if not present and not micro:
        return
    path = paths.get('programUart')
    image = identity.get('imageSha256')
    if (not micro or identity.get('board') != 'spike-prime'
            or identity.get('transport') != 'none'
            or not isinstance(image, string_types)
            or re.match(r'\A[0-9a-f]{64}\Z', image) is None
            or not isinstance(path, string_types)
            or re.match(r'\Aexternal:[A-Za-z][A-Za-z0-9_-]{0,63}\Z', path) is None
            or not _integer(config.get('programUartGeneration'), 1, MAX_GENERATION)):
        raise ValueError('invalid program UART binding')


def validate_request(name, args):
    if name not in COMMANDS or not isinstance(args, dict):
        raise ValueError('invalid program UART request')
    keys = {'micropython.uart.write': ('generation', 'bytes'),
            'micropython.uart.read': ('generation', 'maxBytes'),
            'micropython.uart.close': ('generation',)}[name]
    if set(args) != set(keys) or not _integer(args.get('generation'), 1, MAX_GENERATION):
        raise ValueError('invalid program UART request')
    if name == 'micropython.uart.write':
        data = args['bytes']
        if (not isinstance(data, list) or not 1 <= len(data) <= 32
                or any(not _integer(byte, 0, 255) for byte in data)):
            raise ValueError('invalid program UART request')
    elif name == 'micropython.uart.read' and not _integer(args['maxBytes'], 1, 4096):
        raise ValueError('invalid program UART request')
    return args


class ProgramUartBinding(object):
    """Retain the exact configured object, rejecting route replacement.

    Array conversion is injected by the CLR integration. Unit tests use an
    authored terminal stub; actual qualification uses the Renode external.
    """
    def __init__(self, config, resolve, byte_array):
        validate_binding_config(config)
        self.path = config['paths']['programUart']
        self.generation = config['programUartGeneration']
        self.resolve, self.byte_array = resolve, byte_array
        self.uart = resolve(self.path)
        self.closed = False
        self._check()

    def _check(self):
        if (self.resolve(self.path) != self.uart
                or self.uart.GetType().FullName != 'Antmicro.Renode.Tools.BrickwrightProgramUart'
                or int(self.uart.Generation) != self.generation):
            raise ValueError('program UART ownership mismatch')

    def status(self):
        self._check()
        state = ('closed' if self.closed or self.uart.IsDisposed else
                 'faulted' if self.uart.IsFaulted or not self.uart.IsAttached else 'ready')
        return {'generation': self.generation, 'state': state}

    def dispatch(self, name, args):
        validate_request(name, args)
        self._check()
        if args['generation'] != self.generation:
            raise ValueError('program UART generation mismatch')
        if self.status()['state'] != 'ready':
            raise ValueError('program UART unavailable')
        try:
            if name == 'micropython.uart.write':
                self.uart.QueueWrite(self.generation, self.byte_array(args['bytes']))
                return {'generation': self.generation, 'count': len(args['bytes'])}
            if name == 'micropython.uart.read':
                data = [int(byte) for byte in self.uart.Read(self.generation, args['maxBytes'])]
                if len(data) > args['maxBytes'] or any(not _integer(byte, 0, 255) for byte in data):
                    raise ValueError('invalid program UART output')
                return {'generation': self.generation, 'bytes': data}
            self.uart.Dispose()
            self.closed = True
            return {'generation': self.generation, 'closed': True}
        except Exception:
            # Never include paths, firmware diagnostics, or supplied bytes.
            raise ValueError('program UART operation failed')
