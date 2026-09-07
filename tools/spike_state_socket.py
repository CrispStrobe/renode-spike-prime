#!/usr/bin/env python3
"""Bounded loopback TCP service for a live Renode SPIKE machine.

The service is deliberately dependency-injected: production passes Renode's
``monitor.Machine`` and master virtual-time source, while tests can use a
synthetic object surface without claiming that dictionaries are Renode models.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from contextlib import suppress

from spike_state_bridge import (MAX_LINE_BYTES, LiveStateSession, ProtocolError,
                                RenodeModelObserver, canonical_bytes, parse_line)

MAX_CLIENTS = 4
MAX_READ_BYTES = 16 * 1024


class RenodePathSurface:
    """Resolve explicit machine/external paths against live Renode registries."""

    def __init__(self, machine, externals=None):
        self.machine, self.externals = machine, externals

    def __getitem__(self, path):
        if path.startswith("machine:"):
            return self.machine[path[8:]]
        if path.startswith("external:"):
            if self.externals is None:
                raise KeyError(path)
            return self.externals[path[9:]]
        return self.machine[path]


def validate_endpoint(host: str, port: int, allow_remote: bool = False) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError("host must be a numeric IP address") from error
    if not allow_remote and not address.is_loopback:
        raise ValueError("non-loopback binding requires allow_remote=True")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")


class BoundedStateServer:
    """Serve one NDJSON stream per client with explicit resource limits."""

    def __init__(self, machine, identity, paths, clock_ns, *, host="127.0.0.1",
                 port=0, allow_remote=False, max_clients=1, line_limit=MAX_LINE_BYTES,
                 socket_timeout=5.0, execute=lambda callback: callback()):
        validate_endpoint(host, port, allow_remote)
        if not 1 <= max_clients <= MAX_CLIENTS:
            raise ValueError("max_clients must be between 1 and MAX_CLIENTS")
        if not 256 <= line_limit <= MAX_LINE_BYTES:
            raise ValueError("line_limit is outside the supported range")
        if not 0.05 <= socket_timeout <= 60:
            raise ValueError("socket_timeout is outside the supported range")
        if not callable(clock_ns):
            raise TypeError("clock_ns must be callable")
        if not callable(execute):
            raise TypeError("execute must be callable")
        self.machine, self.identity, self.paths = machine, dict(identity), dict(paths)
        self.clock_ns = clock_ns
        self.execute = execute
        self.host, self.port, self.max_clients = host, port, max_clients
        self.line_limit, self.socket_timeout = line_limit, socket_timeout
        self._listener = None
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(max_clients)
        self._threads = set()

    @property
    def endpoint(self):
        return self._listener.getsockname() if self._listener else None

    def start(self):
        if self._listener:
            raise RuntimeError("server is already started")
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(self.max_clients)
        listener.settimeout(0.1)
        self._listener = listener
        thread = threading.Thread(target=self._accept_loop, name="spike-state-accept", daemon=True)
        thread.start()
        self._threads.add(thread)
        return self.endpoint

    def close(self):
        self._stop.set()
        if self._listener:
            with suppress(OSError):
                self._listener.close()
            self._listener = None
        for thread in tuple(self._threads):
            if thread is not threading.current_thread():
                thread.join(timeout=1)
        self._threads.clear()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                client, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self._slots.acquire(blocking=False):
                client.close()
                continue
            thread = threading.Thread(target=self._serve_client, args=(client,), daemon=True)
            self._threads.add(thread)
            thread.start()

    def _serve_client(self, client):
        session = LiveStateSession(RenodeModelObserver(self.machine, self.identity, self.paths))
        session.connect()
        client.settimeout(self.socket_timeout)
        pending = bytearray()
        try:
            self._sample_and_send(client, session)
            while not self._stop.is_set():
                chunk = client.recv(MAX_READ_BYTES)
                if not chunk:
                    break
                pending.extend(chunk)
                while b"\n" in pending:
                    raw, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if not raw or len(raw) > self.line_limit:
                        raise ProtocolError("line exceeds configured limit")
                    message = parse_line(bytes(raw))
                    if message["type"] != "command":
                        raise ProtocolError("client messages must be commands")
                    self._send(client, self.execute(lambda: session.command(message)))
                    self._sample_and_send(client, session)
                if len(pending) > self.line_limit:
                    raise ProtocolError("line exceeds configured limit")
        except (OSError, ProtocolError, ValueError, TypeError):
            pass
        finally:
            session.disconnect()
            with suppress(OSError):
                client.close()
            self._slots.release()
            self._threads.discard(threading.current_thread())

    def _sample_and_send(self, client, session):
        clock = self.clock_ns()
        if not isinstance(clock, int) or isinstance(clock, bool) or clock < 0:
            raise ProtocolError("virtual clock must be a non-negative integer")
        self.execute(lambda: session.sample(clock))
        for item in session.queue.drain():
            self._send(client, item)

    @staticmethod
    def _send(client, message):
        client.sendall(canonical_bytes(message) + b"\n")


def start_from_renode(monitor, emulation_manager, identity, paths, *, externals=None, **options):
    """Create a server from Renode monitor globals, not stand-in objects."""
    machine = RenodePathSurface(monitor.Machine, externals)
    time_source = emulation_manager.CurrentEmulation.MasterTimeSource

    def clock_ns():
        # Renode TimeInterval ticks are 100 ns and advance only with virtual time.
        return int(time_source.ElapsedVirtualTime.Ticks) * 100

    server = BoundedStateServer(machine, identity, paths, clock_ns, **options)
    server.start()
    return server
