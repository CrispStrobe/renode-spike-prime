// nRF51/nRF52 TIMER with BITMODE (8/16/24/32-bit counter wrap), PRESCALER,
// CC[0..5], CAPTURE/START/STOP/CLEAR tasks, COMPARE events, SHORTS, INTEN.
// MIT. Register map: nRF51 Series Reference Manual v3.0 ch. 18 / nRF52840 PS
// 6.30 (public). Needed because the stock NRF52840_Timer ignores BITMODE, and
// mbed's nRF51 us_ticker runs TIMER1 as a 16-bit counter that must wrap.
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.Timers
{
    public class NrfTimer : IDoubleWordPeripheral, IKnownSize, Antmicro.Renode.Peripherals.Miscellaneous.INRFEventProvider
    {
        public NrfTimer(IMachine machine, int channels = 4)
        {
            this.machine = machine;
            this.channels = channels;
            cc = new uint[channels];
            events = new bool[channels];
            IRQ = new GPIO();
            alarm = new LimitTimer(machine.ClockSource, 1000000, this, "alarm", ulong.MaxValue, direction: Direction.Ascending, enabled: false, eventEnabled: true, workMode: WorkMode.OneShot);
            alarm.LimitReached += OnAlarm;
            Reset();
        }

        public GPIO IRQ { get; }
        public event Action<uint> EventTriggered;
        public long Size => 0x1000;
        public ulong Fired => fired;
        public ulong Irqs => irqs;
        public uint Counter => Count();

        public void Reset()
        {
            running = false; mode = 0; bitmode = 0; prescaler = 4; shorts = 0; inten = 0;
            baseCount = 0; baseTime = Now();
            for(int i = 0; i < channels; i++) { cc[i] = 0; events[i] = false; }
            alarm.Enabled = false;
            IRQ.Unset();
        }

        private ulong Now() => (ulong)machine.ElapsedVirtualTime.TimeElapsed.TotalMicroseconds * 1000UL; // ns
        private ulong TickNs => (ulong)(1000.0 * (1 << (int)prescaler) / 16.0);   // 16 MHz / 2^prescaler
        private uint Mask => bitmode == 0 ? 0xFFFFu : bitmode == 1 ? 0xFFu : bitmode == 2 ? 0xFFFFFFu : 0xFFFFFFFFu;

        private ulong RawCount() => running ? baseCount + (Now() - baseTime) / TickNs : baseCount;
        private uint Count() => (uint)(RawCount() & Mask);

        private void Rebase()
        {
            baseCount = RawCount();
            baseTime = Now();
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset >= 0x140 && offset < 0x140 + 4 * channels) return events[(offset - 0x140) / 4] ? 1u : 0u;
            if(offset >= 0x540 && offset < 0x540 + 4 * channels) return cc[(offset - 0x540) / 4];
            switch(offset)
            {
            case 0x200: return shorts;
            case 0x300: case 0x304: case 0x308: return inten;
            case 0x504: return mode;
            case 0x508: return bitmode;
            case 0x510: return prescaler;
            }
            return 0;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset >= 0x40 && offset < 0x40 + 4 * channels)          // TASKS_CAPTURE[n]
            {
                if(value != 0) cc[(offset - 0x40) / 4] = Count();
                return;
            }
            if(offset >= 0x140 && offset < 0x140 + 4 * channels)        // EVENTS_COMPARE[n]
            {
                events[(offset - 0x140) / 4] = value != 0;
                UpdateIrq();
                return;
            }
            if(offset >= 0x540 && offset < 0x540 + 4 * channels)        // CC[n]
            {
                cc[(offset - 0x540) / 4] = value & Mask;
                Arm();
                return;
            }
            switch(offset)
            {
            case 0x000: if(value != 0 && !running) { baseTime = Now(); running = true; Arm(); } break;   // START
            case 0x004: if(value != 0 && running) { Rebase(); running = false; alarm.Enabled = false; } break; // STOP
            case 0x00C: if(value != 0) { baseCount = 0; baseTime = Now(); Arm(); } break;                   // CLEAR
            case 0x010: if(value != 0 && running) { Rebase(); running = false; alarm.Enabled = false; } break; // SHUTDOWN
            case 0x200: shorts = value; break;
            case 0x300: inten = value; UpdateIrq(); break;
            case 0x304: inten |= value; UpdateIrq(); break;
            case 0x308: inten &= ~value; UpdateIrq(); break;
            case 0x504: mode = value & 3; break;
            case 0x508: Rebase(); bitmode = value & 3; Arm(); break;
            case 0x510: Rebase(); prescaler = Math.Min(value & 0xF, 9u); Arm(); break;
            }
        }

        // Arm the one-shot alarm for the nearest compare match.
        private void Arm()
        {
            alarm.Enabled = false;
            if(!running || mode != 0) return;
            ulong now = Count();
            ulong period = (ulong)Mask + 1;
            ulong best = ulong.MaxValue;
            for(int i = 0; i < channels; i++)
            {
                ulong delta = ((ulong)cc[i] + period - now) % period;
                if(delta == 0) delta = period;
                best = Math.Min(best, delta);
            }
            ulong ns = best * TickNs;
            ulong us = Math.Max(1UL, ns / 1000UL);
            alarm.Value = 0;
            alarm.Limit = us;
            alarm.Enabled = true;
        }

        private void OnAlarm()
        {
            uint now = Count();
            for(int i = 0; i < channels; i++)
            {
                // Tolerate the microsecond rounding of the alarm.
                uint diff = (now - cc[i]) & Mask;
                if(diff <= (uint)Math.Max(1UL, 2000UL / TickNs))
                {
                    events[i] = true;
                    fired++;
                    EventTriggered?.Invoke(0x140u + 4u * (uint)i);
                    if((shorts & (1u << i)) != 0) { baseCount = 0; baseTime = Now(); }          // COMPARE_CLEAR
                    if((shorts & (1u << (i + 8))) != 0) { Rebase(); running = false; }          // COMPARE_STOP
                }
            }
            UpdateIrq();
            Arm();
        }

        private void UpdateIrq()
        {
            bool on = false;
            for(int i = 0; i < channels; i++) on |= events[i] && (inten & (1u << (16 + i))) != 0;
            if(on && !IRQ.IsSet) irqs++;
            IRQ.Set(on);
        }

        private readonly IMachine machine;
        private readonly int channels;
        private readonly uint[] cc;
        private readonly bool[] events;
        private readonly LimitTimer alarm;
        private bool running;
        private uint mode, bitmode, prescaler, shorts, inten;
        private ulong baseCount, baseTime, fired, irqs;
    }
}
