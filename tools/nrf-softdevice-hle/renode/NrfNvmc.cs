// Minimal nRF5 NVMC. MIT.
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    // Minimal nRF5 NVMC (register offsets: nRF51/nRF52 product specifications, nrfx MDK, BSD-3):
    // READY is always 1; ERASEPAGE fills the page with 0xFF; writes to flash go straight to memory.
    public class NrfNvmc : IDoubleWordPeripheral, IKnownSize
    {
        public NrfNvmc(IMachine machine, uint pageSize = 0x1000) { this.machine = machine; this.pageSize = pageSize; }
        public long Size => 0x1000;
        public void Reset() { config = 0; }
        public uint ReadDoubleWord(long offset)
        {
            switch(offset) { case 0x400: case 0x408: return 1; case 0x504: return config; default: return 0; }
        }
        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
            case 0x504: config = value; break;
            case 0x508: case 0x518:
                var page = value & ~(pageSize - 1);
                var ff = new byte[pageSize]; for(int i = 0; i < ff.Length; i++) ff[i] = 0xFF;
                machine.SystemBus.WriteBytes(ff, page);
                this.Log(LogLevel.Info, "erase page 0x{0:X}", page);
                break;
            }
        }
        private readonly IMachine machine; private readonly uint pageSize; private uint config;
    }
}
