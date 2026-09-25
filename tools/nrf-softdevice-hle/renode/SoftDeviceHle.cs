//
// Renode backend of nrf-softdevice-hle (labwired-core crates/nrf-softdevice-hle).
// MIT. Loaded at run time: `include @SoftDeviceHle.cs`.
//
// One peripheral does three jobs:
//   1. It IS the Nordic hole: registered over the MBR + SoftDevice range
//      (0x0..APP_BASE), it answers every read with erased flash (0xFF) and
//      drops writes. Nordic's bytes are never loaded, so there is nothing to
//      execute, show in a debugger or disassemble; every access is logged.
//   2. It forwards exceptions the way the MBR/SoftDevice do: VTOR = app base.
//   3. It services supervisor calls: a hook on the application's SVCall
//      handler reads r0-r3 and the SVC number (byte at stacked PC - 2) from the
//      exception frame, calls the emulator-neutral HLE (Rust, C ABI), writes
//      the result to the stacked r0 and returns from the exception.
//
using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.CPU;
using Antmicro.Renode.Time;
using Antmicro.Renode.Core.Structure;
using Antmicro.Renode.Peripherals.Timers;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class SoftDeviceHle : IDoubleWordPeripheral, IWordPeripheral, IBytePeripheral, IKnownSize, IDisposable
    {
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate int ReadFn(IntPtr ctx, uint addr, IntPtr buf, uint len);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate int WriteFn(IntPtr ctx, uint addr, IntPtr buf, uint len);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate ulong NowFn(IntPtr ctx);

        [StructLayout(LayoutKind.Sequential)]
        private struct HostStruct
        {
            public IntPtr ctx;
            public IntPtr read;
            public IntPtr write;
            public IntPtr nvic;   // NULL: the HLE drives the NVIC registers through read/write
            public IntPtr now;
        }

        private static class Native
        {
            [DllImport("nrf_softdevice_hle", CallingConvention = CallingConvention.Cdecl)]
            public static extern IntPtr sdhle_new(string node, string addr, string air);
            [DllImport("nrf_softdevice_hle", CallingConvention = CallingConvention.Cdecl)]
            public static extern void sdhle_free(IntPtr sd);
            [DllImport("nrf_softdevice_hle", CallingConvention = CallingConvention.Cdecl)]
            public static extern uint sdhle_svc(IntPtr sd, byte num, uint a0, uint a1, uint a2, uint a3, HostStruct host);
            [DllImport("nrf_softdevice_hle", CallingConvention = CallingConvention.Cdecl)]
            public static extern void sdhle_poll(IntPtr sd, HostStruct host);
            [DllImport("nrf_softdevice_hle", CallingConvention = CallingConvention.Cdecl)]
            public static extern IntPtr sdhle_svc_name(byte num);
        }

        public SoftDeviceHle(IMachine machine, long size, string library, string node = "microbit", string address = "C0:EE:AA:BB:CC:DD", string air = "", string tracePath = "")
        {
            this.machine = machine;
            this.size = size;
            NativeLibrary.SetDllImportResolver(typeof(SoftDeviceHle).Assembly, (name, asm, path) =>
                name == "nrf_softdevice_hle" ? NativeLibrary.Load(library) : IntPtr.Zero);
            handle = Native.sdhle_new(node, address, air);
            if(handle == IntPtr.Zero)
            {
                throw new ArgumentException($"bad device address {address}");
            }
            readFn = HostRead;
            writeFn = HostWrite;
            nowFn = HostNow;
            host = new HostStruct
            {
                ctx = IntPtr.Zero,
                read = Marshal.GetFunctionPointerForDelegate(readFn),
                write = Marshal.GetFunctionPointerForDelegate(writeFn),
                nvic = IntPtr.Zero,
                now = Marshal.GetFunctionPointerForDelegate(nowFn),
            };
            if(tracePath != "")
            {
                trace = new StreamWriter(tracePath) { AutoFlush = true };
            }
            // Poll the air and the advertising timer every millisecond of virtual time.
            pollTimer = new LimitTimer(machine.ClockSource, 1000, this, "sdhle-poll", 1, direction: Direction.Ascending, enabled: false, eventEnabled: true, autoUpdate: true);
            pollTimer.LimitReached += () => Native.sdhle_poll(handle, host);
        }

        public long Size => size;
        public void Reset() { }

        public void Dispose()
        {
            if(handle != IntPtr.Zero) { Native.sdhle_free(handle); handle = IntPtr.Zero; }
        }

        // ---- the hole ----
        public uint ReadDoubleWord(long offset) { Hole("r32", offset); return 0xFFFFFFFF; }
        public void WriteDoubleWord(long offset, uint value) { Hole("w32", offset); }
        public ushort ReadWord(long offset) { Hole("r16", offset); return 0xFFFF; }
        public void WriteWord(long offset, ushort value) { Hole("w16", offset); }
        public byte ReadByte(long offset) { Hole("r8", offset); return 0xFF; }
        public void WriteByte(long offset, byte value) { Hole("w8", offset); }

        /// Monitor: `sd Attach cpu 0x18000`
        public void Attach(ICPU cpuArg, ulong appBase)
        {
            cpu = (CortexM)cpuArg;
            cpu.InitVectorTableOffset = (uint)appBase;
            cpu.VectorTableOffset = (uint)appBase;
            svcHandler = machine.SystemBus.ReadDoubleWord(appBase + 0x2C) & ~1UL;
            cpu.AddHook(svcHandler, (c, pc) => OnSvc());
            // Trace entries into the application's SoftDevice event handler (SWI2 = IRQ 22, vector 38).
            var evtHandler = machine.SystemBus.ReadDoubleWord(appBase + 4 * (16 + 22)) & ~1UL;
            cpu.AddHook(evtHandler, (c, pc) => { evtIrqs++; if(trace != null) trace.WriteLine($"{{\"ev\":\"sd_evt_irq\",\"n\":{evtIrqs},\"t_us\":{HostNow(IntPtr.Zero)}}}"); });
            pollTimer.Enabled = true;
            this.Log(LogLevel.Info, "SoftDevice HLE: VTOR=0x{0:X}, SVCall handler 0x{1:X} serviced by the HLE", appBase, svcHandler);
        }

        public ulong SvcCount => count;

        private void OnSvc()
        {
            var ipsr = (uint)cpu.GetRegister(25).RawValue & 0x1FF;
            if(ipsr != 11)
            {
                return;
            }
            var bus = machine.SystemBus;
            var lr = (uint)cpu.LR.RawValue;
            // The frame is on the stack the SVC was issued from: EXC_RETURN bit 2 = PSP.
            ulong frame = ((lr & 4) != 0) ? cpu.GetRegister(22).RawValue : cpu.SP.RawValue;
            uint[] a = new uint[4];
            for(int i = 0; i < 4; i++) a[i] = bus.ReadDoubleWord(frame + (ulong)(4 * i));
            uint retpc = bus.ReadDoubleWord(frame + 24);
            byte num = bus.ReadByte(retpc - 2);
            uint r = Native.sdhle_svc(handle, num, a[0], a[1], a[2], a[3], host);
            bus.WriteDoubleWord(frame, r);
            count++;
            if(trace != null)
            {
                var name = Marshal.PtrToStringAnsi(Native.sdhle_svc_name(num));
                trace.WriteLine($"{{\"ev\":\"svc\",\"n\":{count},\"t_us\":{HostNow(IntPtr.Zero)},\"svc\":{num},\"name\":\"{name}\",\"r0\":{a[0]},\"r1\":{a[1]},\"r2\":{a[2]},\"r3\":{a[3]},\"ret\":{r},\"pc\":{retpc - 2}}}");
            }
            cpu.PC = lr;   // exception return (tlib: PC >= EXC_RETURN_MIN unstacks)
        }

        private int HostRead(IntPtr ctx, uint addr, IntPtr buf, uint len)
        {
            if(!Accessible(addr, len)) return 0;
            var bytes = (addr >= 0xE000E000 && addr < 0xE000F000 && len == 4)
                ? BitConverter.GetBytes(machine.SystemBus.ReadDoubleWord(addr, context: cpu))
                : machine.SystemBus.ReadBytes(addr, (int)len);
            Marshal.Copy(bytes, 0, buf, (int)len);
            return 1;
        }

        private int HostWrite(IntPtr ctx, uint addr, IntPtr buf, uint len)
        {
            if(!Accessible(addr, len)) return 0;
            var bytes = new byte[len];
            Marshal.Copy(buf, bytes, 0, (int)len);
            if(addr >= 0xE000E000 && addr < 0xE000F000 && len == 4)
            {
                machine.SystemBus.WriteDoubleWord(addr, BitConverter.ToUInt32(bytes, 0), context: cpu);
            }
            else
            {
                machine.SystemBus.WriteBytes(bytes, addr);
            }
            return 1;
        }

        private bool Accessible(uint addr, uint len)
        {
            // The HLE never reads the Nordic range (there is nothing there).
            if(addr < (uint)size) return false;
            return machine.SystemBus.FindMemory(addr) != null || machine.SystemBus.WhatIsAt(addr) != null || (addr >= 0xE000E000 && addr < 0xE000F000);
        }

        private ulong HostNow(IntPtr ctx)
        {
            return (ulong)machine.ElapsedVirtualTime.TimeElapsed.TotalMicroseconds;
        }

        private void Hole(string kind, long offset)
        {
            holeAccesses++;
            if(trace != null)
            {
                trace.WriteLine($"{{\"ev\":\"hole\",\"kind\":\"{kind}\",\"addr\":{offset}}}");
            }
        }

        public ulong HoleAccesses => holeAccesses;

        private readonly IMachine machine;
        private readonly long size;
        private readonly StreamWriter trace;
        private readonly LimitTimer pollTimer;
        private readonly ReadFn readFn;
        private readonly WriteFn writeFn;
        private readonly NowFn nowFn;
        private HostStruct host;
        private IntPtr handle;
        private CortexM cpu;
        private ulong svcHandler;
        private ulong count;
        private ulong holeAccesses;
        private ulong evtIrqs;
    }
}
