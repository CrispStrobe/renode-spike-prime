// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Brickwright contributors
// All rights reserved.
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are met:
// 1. Redistributions of source code must retain the above copyright notice,
//    this list of conditions and the following disclaimer.
// 2. Redistributions in binary form must reproduce the above copyright notice,
//    this list of conditions and the following disclaimer in the documentation
//    and/or other materials provided with the distribution.
// 3. Neither the name of the copyright holder nor the names of its contributors
//    may be used to endorse or promote products derived from this software
//    without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
// AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
// ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
// LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
// CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
// SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
// INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
// CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
// ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.

using System;
using System.Collections.Generic;
using System.Threading;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.UART;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Tools
{
    /// <summary>
    /// Bounded byte transport, with no protocol or firmware compatibility claim.
    /// Attach and tear down only from host control code, outside all emulation
    /// callbacks. The caller must ensure this for CPU callbacks; this class rejects
    /// calls from its own callbacks. QueueWrite and Read may run on host threads.
    /// Acceptance only copies bytes; even ReleasedInputBytes is not guest consumption.
    /// </summary>
    public sealed class BrickwrightProgramUart : IExternal, IConnectable<IUART>, IDisposable
    {
        public BrickwrightProgramUart(long generation)
        {
            if(generation <= 0 || generation > MaximumGeneration)
            {
                throw new ArgumentOutOfRangeException(nameof(generation));
            }
            Generation = generation;
        }

        public long Generation { get; private set; }
        public bool IsFaulted { get { return Volatile.Read(ref faultReason) != null; } }
        public string FaultReason { get { return Volatile.Read(ref faultReason); } }
        public bool IsAttached { get { lock(sync) { return available; } } }
        public bool IsDisposed { get { lock(sync) { return disposed; } } }
        public int PendingInputCount { get { lock(sync) { return inputCount; } } }
        public int BufferedOutputCount { get { lock(outputSync) { return outputCount; } } }
        public long AcceptedInputBytes { get { lock(sync) { return acceptedInputBytes; } } }
        public long ReleasedInputBytes { get { lock(sync) { return releasedInputBytes; } } }

        public void AttachTo(IUART obj)
        {
            EnsureHostContext();
            lock(lifecycleSync) { AttachCore(obj); }
        }

        private void AttachCore(IUART obj)
        {
            if(obj == null) { throw new ArgumentNullException(nameof(obj)); }
            lock(sync)
            {
                if(disposed) { throw new ObjectDisposedException(nameof(BrickwrightProgramUart)); }
                if(attachmentAttempted) { throw new InvalidOperationException("Only one attachment attempt is allowed."); }
                attachmentAttempted = true;
            }
            try
            {
                var attachedMachine = obj.GetMachine();
                // Never pause while holding sync: the machine can be finishing a callback.
                using(attachedMachine.ObtainPausedState())
                {
                    lock(sync) { machine = attachedMachine; uart = obj; }
                    obj.CharReceived += CaptureOutput;
                    lock(sync) { subscribed = true; }
                    var managedClock = attachedMachine.ObtainManagedThread(
                        ReleaseInput, TimeInterval.FromMicroseconds(100),
                        "Brickwright program UART", this);
                    if(managedClock == null) { throw new InvalidOperationException("Managed clock unavailable."); }
                    lock(sync) { clock = managedClock; available = true; }
                    managedClock.Start();
                }
            }
            catch
            {
                lock(sync) { Fault("Attachment failed."); }
                // Preserve the original exception; cleanup failure remains explicit in fault state.
                try { TearDown(false); }
                catch { Interlocked.Exchange(ref faultReason, "Attachment and cleanup failed."); }
                throw;
            }
        }

        public void DetachFrom(IUART obj)
        {
            EnsureHostContext();
            lock(lifecycleSync) { DetachCore(obj); }
        }

        private void DetachCore(IUART obj)
        {
            lock(sync)
            {
                if(disposed) { throw new ObjectDisposedException(nameof(BrickwrightProgramUart)); }
                if(uart == null || !ReferenceEquals(uart, obj))
                {
                    throw new InvalidOperationException("UART is not attached to this external.");
                }
            }
            TearDown(false);
        }

        public void QueueWrite(long generation, byte[] bytes)
        {
            if(bytes == null) { throw new ArgumentNullException(nameof(bytes)); }
            if(bytes.Length < 1 || bytes.Length > MaximumWriteBytes)
            {
                throw new ArgumentOutOfRangeException(nameof(bytes), "Write length must be 1..32.");
            }
            lock(sync)
            {
                EnsureAvailable(generation);
                if(bytes.Length > InputCapacity - inputCount)
                {
                    throw new InvalidOperationException("Pending input capacity exceeded.");
                }
                if(bytes.Length > LifetimeInputBudget - acceptedInputBytes)
                {
                    throw new InvalidOperationException("Lifetime input budget exceeded.");
                }
                for(var i = 0; i < bytes.Length; i++)
                {
                    input[(inputHead + inputCount) % InputCapacity] = bytes[i];
                    inputCount++;
                }
                acceptedInputBytes += bytes.Length;
            }
        }

        public byte[] Read(long generation, int maximum)
        {
            if(maximum < 1 || maximum > MaximumReadBytes)
            {
                throw new ArgumentOutOfRangeException(nameof(maximum));
            }
            lock(sync)
            {
                EnsureAvailable(generation);
                lock(outputSync)
                {
                    // CaptureOutput can fault independently of sync. Recheck after
                    // obtaining the output lock, before draining any buffered bytes.
                    EnsureAvailable(generation);
                    var result = new byte[Math.Min(maximum, outputCount)];
                    for(var i = 0; i < result.Length; i++)
                    {
                        result[i] = output[outputHead];
                        outputHead = (outputHead + 1) % OutputCapacity;
                        outputCount--;
                    }
                    return result;
                }
            }
        }

        public void Dispose()
        {
            EnsureHostContext();
            lock(lifecycleSync) { DisposeCore(); }
        }

        private void DisposeCore()
        {
            lock(sync) { if(disposed) { return; } }
            TearDown(true);
        }

        private void ReleaseInput()
        {
            callbackDepth++;
            try
            {
                lock(sync)
                {
                    if(!available || disposed || Volatile.Read(ref faultReason) != null || inputCount == 0) { return; }
                    var value = input[inputHead];
                    inputHead = (inputHead + 1) % InputCapacity;
                    inputCount--;
                    // Keep sync through WriteChar so teardown cannot overtake a release.
                    // Output capture uses only outputSync, including when WriteChar
                    // waits for CharReceived on another thread.
                    try { uart.WriteChar(value); releasedInputBytes++; }
                    catch { Fault("UART WriteChar failed; delivery is indeterminate."); }
                }
            }
            finally { callbackDepth--; }
        }

        private void CaptureOutput(byte value)
        {
            callbackDepth++;
            try
            {
                // Never take sync here: WriteChar may hold it while waiting for
                // this callback on a different thread. Fault publication is atomic.
                lock(outputSync)
                {
                    if(!available || disposed || Volatile.Read(ref faultReason) != null) { return; }
                    if(outputCount == OutputCapacity)
                    {
                        Fault("Guest output capacity exceeded.");
                        return;
                    }
                    output[(outputHead + outputCount) % OutputCapacity] = value;
                    outputCount++;
                }
            }
            finally { callbackDepth--; }
        }

        private void TearDown(bool dispose)
        {
            IMachine attachedMachine;
            IManagedThread managedClock;
            IUART attachedUart;
            bool removeHandler;
            lock(sync)
            {
                available = false;
                if(dispose) { disposed = true; }
                attachedMachine = machine;
                managedClock = clock;
                attachedUart = uart;
                removeHandler = subscribed;
                // Clear immediately, including when pausing or stopping subsequently fails.
                Array.Clear(input, 0, input.Length);
                inputHead = inputCount = 0;
                lock(outputSync)
                {
                    Array.Clear(output, 0, output.Length);
                    outputHead = outputCount = 0;
                }
            }
            var errors = new List<Exception>();
            IDisposable paused = null;
            try
            {
                if(attachedMachine != null)
                {
                    try { paused = attachedMachine.ObtainPausedState(); }
                    catch(Exception e) { errors.Add(e); }
                }
                if(managedClock != null)
                {
                    try { managedClock.Stop(); } catch(Exception e) { errors.Add(e); }
                    try { managedClock.Dispose(); } catch(Exception e) { errors.Add(e); }
                }
                if(removeHandler && attachedUart != null)
                {
                    try { attachedUart.CharReceived -= CaptureOutput; } catch(Exception e) { errors.Add(e); }
                }
            }
            finally
            {
                if(paused != null)
                {
                    try { paused.Dispose(); } catch(Exception e) { errors.Add(e); }
                }
                lock(sync)
                {
                    clock = null; uart = null; machine = null; subscribed = false;
                    if(errors.Count != 0) { Fault("Teardown failed."); }
                }
            }
            if(errors.Count != 0) { throw new AggregateException("UART teardown failed.", errors); }
        }

        private void EnsureAvailable(long generation)
        {
            if(generation != Generation) { throw new ArgumentException("Generation mismatch.", nameof(generation)); }
            if(disposed) { throw new ObjectDisposedException(nameof(BrickwrightProgramUart)); }
            var fault = Volatile.Read(ref faultReason);
            if(fault != null) { throw new InvalidOperationException(fault); }
            if(!available) { throw new InvalidOperationException("UART attachment unavailable."); }
        }

        private void EnsureHostContext()
        {
            if(callbackDepth != 0)
            {
                throw new InvalidOperationException("Lifecycle operations require host control code outside callbacks.");
            }
        }

        private void Fault(string reason)
        {
            Interlocked.CompareExchange(ref faultReason, reason, null);
        }

        public const long MaximumGeneration = 9007199254740991L;
        public const int MaximumWriteBytes = 32;
        public const int MaximumReadBytes = 4096;
        public const int InputCapacity = 256;
        public const int OutputCapacity = 65536;
        public const long LifetimeInputBudget = 65536;

        [ThreadStatic] private static int callbackDepth;
        private readonly object lifecycleSync = new object();
        private readonly object sync = new object();
        // Lock order for host operations: sync, then outputSync. CaptureOutput
        // acquires outputSync only, and never calls the machine or UART.
        private readonly object outputSync = new object();
        private readonly byte[] input = new byte[InputCapacity];
        private readonly byte[] output = new byte[OutputCapacity];
        private int inputHead, inputCount, outputHead, outputCount;
        private long acceptedInputBytes, releasedInputBytes;
        private bool attachmentAttempted, subscribed;
        private volatile bool available, disposed;
        private string faultReason;
        private IMachine machine;
        private IUART uart;
        private IManagedThread clock;
    }
}
