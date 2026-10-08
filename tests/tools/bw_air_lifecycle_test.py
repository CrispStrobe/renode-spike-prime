#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Actual lifecycle classes with synthetic I/O, without Bumble or an emulator.

Compile the unmodified class ASTs from hci_node.py. Only Bumble/air boundaries
are substituted; this does not qualify Bumble, TCP or firmware delivery.
"""
import ast
import asyncio
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import sys
import types
import unittest

SOURCE = Path(os.environ.get('BW_AIR_LIFECYCLE_SOURCE',
    Path(__file__).resolve().parents[2] / 'tools/bw-air/hci_node.py'))

def load_classes():
    tree = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
    names = {'PacedSink', 'Station', 'Air'}
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in names]
    assert len(nodes) == 3
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    code = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    module = types.ModuleType('bw_air_lifecycle_under_test')
    sys.modules[module.__name__] = module
    class Controller:
        def __init__(self, name, **kwargs): self.name = name
    class Source:
        def __init__(self): self.frames = []
        def data_received(self, data): self.frames.append(data)
    module.__dict__.update(asyncio=asyncio, dataclass=dataclass, field=field,
        logger=logging.getLogger('bw-air.lifecycle-test'), AirController=Controller,
        StreamPacketSource=Source, StreamPacketSink=lambda writer: writer)
    exec(compile(code, str(SOURCE), 'exec'), module.__dict__)
    return module

class Writer:
    def __init__(self):
        self.closed = False; self.frames = []; self.error = None
        self.entered = asyncio.Event(); self.release = asyncio.Event(); self.release.set()
    def write(self, data): self.frames.append(bytes(data))
    async def drain(self):
        self.entered.set(); await self.release.wait()
        if self.error is not None: raise self.error
    def close(self): self.closed = True
    async def wait_closed(self): pass

class Link:
    def __init__(self): self.writer = Writer(); self.removed = []
    def remove_controller(self, controller): self.removed.append(controller)

class Lifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.m = load_classes(); self.air = self.m.Air(); self.link = Link()
        async def link(name): return self.link
        self.air._link = link
        self.reader = asyncio.StreamReader(); self.writer = Writer()
        self.sink = self.m.PacedSink(self.writer, 0)
    async def asyncTearDown(self):
        tasks = [self.sink.task]
        tasks += [s.extra['pump'] for s in self.air.stations.values() if 'pump' in s.extra]
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    async def attach(self):
        return await self.air._attach_stream('hub', self.reader, self.writer,
            '02:00:00:00:00:01', 'hci-client', self.sink)
    async def until(self, predicate):
        async def poll():
            while not predicate(): await asyncio.sleep(0)
        await asyncio.wait_for(poll(), 1)
    async def test_eof_joins_sink_and_closes_owned_writers(self):
        station = await self.attach(); self.reader.feed_eof()
        await asyncio.wait_for(station.extra['pump'], 1)
        self.assertTrue(self.sink.task.done(), 'EOF left packet drain task running')
        self.assertTrue(self.writer.closed)
        self.assertTrue(self.link.writer.closed)
        self.assertNotIn('hub', self.air.stations)
    async def test_fifo_and_packet_copy(self):
        packet = bytearray(b'first'); self.sink.on_packet(packet); packet[:] = b'wrong'
        self.sink.on_packet(b'second')
        await self.until(lambda: len(self.writer.frames) == 2 and not self.sink.pending)
        self.assertEqual(self.writer.frames, [b'first', b'second'])
        await self.sink.close()
    async def test_immediate_remove_joins_tasks(self):
        station = await self.attach()
        await asyncio.wait_for(self.air.remove('hub'), 1)
        self.assertTrue(station.extra['pump'].done())
        self.assertTrue(self.sink.task.done())
        self.assertTrue(self.writer.closed)
        await self.air.remove('hub')
    async def test_remove_aborts_blocked_write_explicitly(self):
        self.writer.release.clear(); self.sink.on_packet(b'in-flight')
        station = await self.attach(); await asyncio.wait_for(self.writer.entered.wait(), 1)
        with self.assertLogs('bw-air.lifecycle-test', level='WARNING'):
            await asyncio.wait_for(self.air.remove('hub'), 1)
        self.assertTrue(self.sink.task.done())
        self.assertEqual(station.extra['abandoned_packets'], 1)
        self.assertTrue(self.writer.closed)
    async def test_write_failure_is_observed_and_propagated(self):
        error = ConnectionResetError('synthetic drain reset'); self.writer.error = error
        station = await self.attach(); self.sink.on_packet(b'payload')
        with self.assertLogs('bw-air.lifecycle-test', level='ERROR'):
            result, = await asyncio.gather(asyncio.wait_for(station.wait_closed(), 1),
                                          return_exceptions=True)
        self.assertIs(result, error)
        self.assertIs(station.extra['failure'], error)
        self.assertIs(self.sink.failure, error)
        self.assertTrue(self.writer.closed)
        self.assertTrue(self.sink.task.done())
    async def test_eof_does_not_hide_already_failed_write(self):
        self.writer.error = ConnectionResetError('simultaneous reset')
        self.sink.on_packet(b'payload')
        await self.until(self.sink.task.done)
        station = await self.attach(); self.reader.feed_eof()
        with self.assertLogs('bw-air.lifecycle-test', level='ERROR'):
            with self.assertRaises(ConnectionResetError):
                await asyncio.wait_for(station.wait_closed(), 1)
        self.assertTrue(self.writer.closed)
    async def test_read_failure_is_observed_and_propagated(self):
        station = await self.attach(); error = ConnectionResetError('synthetic read reset')
        self.reader.set_exception(error)
        with self.assertLogs('bw-air.lifecycle-test', level='ERROR'):
            with self.assertRaises(ConnectionResetError) as caught:
                await asyncio.wait_for(station.wait_closed(), 1)
        self.assertIs(caught.exception, error)
        self.assertIs(station.extra['failure'], error)
        self.assertTrue(self.sink.task.done())
    async def test_failed_air_attach_joins_precreated_sink(self):
        async def fail(name): raise OSError('synthetic air refusal')
        self.air._link = fail
        with self.assertRaisesRegex(OSError, 'synthetic air refusal'): await self.attach()
        self.assertTrue(self.sink.task.done())
        self.assertTrue(self.writer.closed)
    async def test_close_rejects_new_packets_and_is_idempotent(self):
        self.sink.on_packet(b'queued'); await self.sink.close(); await self.sink.close()
        self.assertEqual(self.sink.abandoned_packets, 1)
        self.assertTrue(self.sink.queue.empty())
        with self.assertRaises(RuntimeError): self.sink.on_packet(b'late')
    async def test_failed_sink_rejects_new_packets_with_original_cause(self):
        error = ConnectionResetError('synthetic reset'); self.writer.error = error
        self.sink.on_packet(b'payload'); await asyncio.gather(self.sink.task, return_exceptions=True)
        with self.assertRaises(RuntimeError) as caught: self.sink.on_packet(b'late')
        self.assertIs(caught.exception.__cause__, error)
    async def test_writer_close_error_is_diagnostic_not_successful_flush(self):
        async def failed_close(): raise ConnectionResetError('synthetic close reset')
        self.writer.wait_closed = failed_close
        station = await self.attach(); self.reader.feed_eof()
        with self.assertLogs('bw-air.lifecycle-test', level='WARNING'):
            await asyncio.wait_for(station.wait_closed(), 1)
        self.assertEqual(len(station.extra['close_errors']), 1)
        self.assertTrue(self.sink.task.done())
    async def test_cancelled_waiter_does_not_cancel_stream(self):
        station = await self.attach()
        waiter = asyncio.create_task(station.wait_closed()); await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError): await waiter
        self.assertFalse(station.extra['pump'].done())
        self.reader.feed_eof(); await asyncio.wait_for(station.wait_closed(), 1)
        self.assertTrue(self.writer.closed)
    async def test_remove_during_eof_cleanup_joins_without_recancelling(self):
        release = asyncio.Event()
        async def held_close(): await release.wait()
        self.writer.wait_closed = held_close
        station = await self.attach(); self.reader.feed_eof()
        await self.until(lambda: self.writer.closed)
        self.assertIs(self.air.stations.get('hub'), station)
        remover = asyncio.create_task(self.air.remove('hub')); await asyncio.sleep(0)
        self.assertFalse(remover.done())
        release.set(); await asyncio.wait_for(remover, 1)
        self.assertTrue(self.link.writer.closed)
        self.assertNotIn('hub', self.air.stations)
    async def test_late_write_failure_during_eof_cleanup_propagates(self):
        error = ConnectionResetError('late write reset')
        self.writer.release.clear(); self.sink.on_packet(b'in-flight')
        station = await self.attach(); await asyncio.wait_for(self.writer.entered.wait(), 1)
        original_close = self.sink.close
        async def late_failure():
            self.writer.error = error; self.writer.release.set()
            await self.until(self.sink.task.done)
            await original_close()
        self.sink.close = late_failure; self.reader.feed_eof()
        with self.assertLogs('bw-air.lifecycle-test', level='WARNING'):
            result, = await asyncio.gather(asyncio.wait_for(station.wait_closed(), 1),
                                          return_exceptions=True)
        self.assertIs(result, error)
        self.assertIs(station.extra['failure'], error)
        self.assertTrue(self.link.writer.closed)
    async def test_synchronous_close_failure_preserves_delivery_error(self):
        error = ConnectionResetError('original delivery failure'); self.writer.error = error
        def bad_close(): raise RuntimeError('secondary close failure')
        self.writer.close = bad_close
        station = await self.attach(); self.sink.on_packet(b'payload')
        with self.assertLogs('bw-air.lifecycle-test', level='WARNING'):
            result, = await asyncio.gather(asyncio.wait_for(station.wait_closed(), 1),
                                          return_exceptions=True)
        self.assertIs(result, error)
        self.assertEqual(str(station.extra['close_errors'][0]), 'secondary close failure')
        self.assertTrue(self.link.writer.closed)
    async def test_primary_read_error_survives_late_write_error(self):
        read_error = ConnectionResetError('primary read failure')
        write_error = ConnectionResetError('secondary write failure')
        self.writer.release.clear(); self.sink.on_packet(b'in-flight')
        station = await self.attach(); await asyncio.wait_for(self.writer.entered.wait(), 1)
        original_close = self.sink.close
        async def late_failure():
            self.writer.error = write_error; self.writer.release.set()
            await self.until(self.sink.task.done); await original_close()
        self.sink.close = late_failure; self.reader.set_exception(read_error)
        with self.assertLogs('bw-air.lifecycle-test', level='WARNING'):
            result, = await asyncio.gather(asyncio.wait_for(station.wait_closed(), 1),
                                          return_exceptions=True)
        self.assertIs(result, read_error)
        self.assertIs(station.extra['sink_failure'], write_error)
    async def test_ready_read_failure_survives_explicit_removal(self):
        station = await self.attach(); error = ConnectionResetError('read before remove')
        self.reader.set_exception(error)
        with self.assertLogs('bw-air.lifecycle-test', level='ERROR'):
            result, = await asyncio.gather(self.air.remove('hub'), return_exceptions=True)
        self.assertIs(result, error)
        self.assertIs(station.extra['read_failure'], error)
        self.assertIs(station.extra['failure'], error)
        self.assertTrue(self.writer.closed)
        self.assertTrue(self.sink.task.done())

if __name__ == '__main__': unittest.main()
