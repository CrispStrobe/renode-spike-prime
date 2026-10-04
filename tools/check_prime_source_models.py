#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Run the authored Prime model fixtures in an installed Renode, offline.

Transforms only test-framework annotations/assertions for dynamic inclusion;
peripheral implementation sources are staged unchanged apart from type aliases.
No firmware or user program is loaded. Output must be a new directory.
"""
import argparse
from pathlib import Path
import re
import subprocess
from stage_prime_runtime import CORE, stage


def prepare(infrastructure, output):
    stage(infrastructure, output, True)
    source_root = infrastructure / 'src/Emulator/Peripherals/Test/PeripheralsTests'
    imports, bodies = set(), []
    for name in ('STM32TLCClockTests.cs', 'LegoLpf2ElectricalPortTests.cs', 'STM32F4I2CStreamTests.cs', 'STM32ADCTriggerTests.cs', 'STM32SPIDmaReadTests.cs', 'STM32TimerRolloverTests.cs', 'STM32TimerSoftwareEventTests.cs', 'STM32TimerInclusivePeriodTests.cs'):
        source = (source_root / name).read_text().replace('using NUnit.Framework;', '')
        source = re.sub(r'\[(?:TestFixture|NonParallelizable|SetUp|TearDown|Test|(?:TestCase|Values)\([^\]]+\))\]', '', source)
        source = source.replace('Assert.', 'SourceAssert.')
        for original in CORE.values():
            source = re.sub(r'\b' + original + r'\b', 'Brickwright' + original, source)
        imports.update(re.findall(r'^using [^\n]+;', source, re.M))
        bodies.append(re.sub(r'^using [^\n]+;\n', '', source, flags=re.M))
    clock_methods = re.findall(r'public void (Should\w+)\(\)', bodies[0])
    calls = ''.join('clock.SetUp();try { clock.' + method + '(); } finally { clock.TearDown(); }\n' for method in clock_methods)
    helper = '''
public static class SourceAssert {
    private static bool Equal(object a,object b) {
        if(object.Equals(a,b))return true;
        try { return System.Convert.ToDecimal(a)==System.Convert.ToDecimal(b); }
        catch(System.Exception) { return false; }
    }
    public static void AreEqual(object a,object b,string message=null) { if(!Equal(a,b))throw new System.Exception("source fixture equality failed: "+a+" / "+b+" "+message); }
    public static void IsTrue(bool value) { if(!value)throw new System.Exception("source fixture expected true"); }
    public static void IsFalse(bool value) { if(value)throw new System.Exception("source fixture expected false"); }
    public static void AreNotEqual(object a,object b,string message=null) { if(Equal(a,b))throw new System.Exception("source fixture inequality failed: "+message); }
    public static void Greater(int a,int b,string message=null) { if(a<=b)throw new System.Exception("source fixture comparison failed: "+message); }
}
public static class PrimeSourceFixtureRunner {
    public static string RunPrimeSourceFixtures(this Antmicro.Renode.Core.Emulation emulation) {
        var clock=new Antmicro.Renode.PeripheralsTests.STM32TLCClockTests();
''' + calls + '''
        var i2c=new Antmicro.Renode.PeripheralsTests.STM32F4I2CStreamTests();
        foreach(var count in new[]{1,2,3,4,12,32})
            foreach(var halfword in new[]{false,true})
                foreach(var restart in new[]{false,true})
                    i2c.ShouldStreamUntilFinalNack(count,halfword,restart);
        new Antmicro.Renode.PeripheralsTests.STM32ADCTriggerTests().ShouldSelectEdgesAndScanIdleButtonThroughHalfwordDataReads();
        new Antmicro.Renode.PeripheralsTests.STM32SPIDmaReadTests().ShouldReadRepeatedDmaBlocksAfterCpuConsumesCommandBytes();
        var rollover=new Antmicro.Renode.PeripheralsTests.STM32TimerRolloverTests();
        rollover.SetUp();try { rollover.ShouldWakeOnZeroCompareAcrossRepeatedRollover(); } finally { rollover.TearDown(); }
        rollover.SetUp();try { rollover.ShouldWakeOnNonzeroCompareAfterRollover(); } finally { rollover.TearDown(); }
        rollover.SetUp();try { rollover.ShouldExposeOverflowAndZeroCompareTogetherOnInterrupt(); } finally { rollover.TearDown(); }
        var software=new Antmicro.Renode.PeripheralsTests.STM32TimerSoftwareEventTests();
        foreach(var channel in new[]{1,2,3,4}) {
            software.SetUp();try { software.ShouldLatchSoftwareCompareWhileInterruptDisabled(channel); } finally { software.TearDown(); }
        }
        software.SetUp();try { software.ShouldGenerateEnabledCompareWithoutResettingRunningCounter(); } finally { software.TearDown(); }
        software.SetUp();try { software.ShouldKeepIndependentChannelFlagsAndMask(); } finally { software.TearDown(); }
        software.SetUp();try { software.ShouldKeepUpdateGenerationSeparateFromCompareGeneration(); } finally { software.TearDown(); }
        software.SetUp();try { software.ShouldLatchNaturalOutputCompareWhileInterruptMasked(); } finally { software.TearDown(); }
        software.SetUp();try { software.ShouldLatchZeroOutputCompareAtRolloverWhileInterruptMasked(); } finally { software.TearDown(); }
        var inclusive=new Antmicro.Renode.PeripheralsTests.STM32TimerInclusivePeriodTests();
        foreach(var arr in new[]{65535u,uint.MaxValue}) {
            inclusive.SetUp();try { inclusive.ShouldCountThroughArrBeforeWrapping(arr); } finally { inclusive.TearDown(); }
            foreach(var compareZero in new[]{false,true}) {
                foreach(var updateEnabled in new[]{false,true}) {
                    inclusive.SetUp();try { inclusive.ShouldDeliverBoundaryCompare(arr,compareZero,updateEnabled); } finally { inclusive.TearDown(); }
                }
            }
        }
        inclusive.SetUp();try { inclusive.ShouldKeepPreloadedArrUntilRolloverAcrossControlWrites(); } finally { inclusive.TearDown(); }
        inclusive.SetUp();try { inclusive.ShouldRetainLegacyDescendingAndCenterAlignedPeriods(); } finally { inclusive.TearDown(); }
        var electrical=ElectricalTests.RunElectricalTests(emulation);
        return "PASS ''' + str(len(clock_methods)) + ''' display-clock fixtures; 24 I2C stream fixtures; ADC trigger/halfword fixture; repeated SPI DMA read fixture; 3 timer rollover fixtures; 9 timer software-event fixtures; 12 inclusive-period fixtures; "+electrical;
    }
    public static string CheckPrimeWiring(this Antmicro.Renode.Core.Emulation emulation) {
        Antmicro.Renode.Core.IMachine machine;
        if(!emulation.TryGetMachineByName("source-fixture",out machine))throw new System.Exception("fixture machine absent");
        foreach(var name in new[]{"A","B","C","D","E","F"}) {
            Antmicro.Renode.Peripherals.UART.LegoLpf2ElectricalPort port;
            if(!emulation.ExternalsManager.TryGetByName("port"+name,out port) || port.GetMachine()!=machine)
                throw new System.Exception("UART endpoint must belong to the fixture machine");
        }
        // Expected physical bridge pins, independent of the installed definitions.
        var names=new[]{"A","B","C","D","E","F"};
        var banks1=new[]{"E","E","B","B","C","C"};
        var banks2=new[]{"E","E","B","B","C","B"};
        var pins1=new[]{9,13,6,8,6,8};var pins2=new[]{11,14,7,9,7,1};
        var timerNames=new[]{"timer1","timer1","timer4","timer4","timer3","timer3"};
        for(var i=0;i<6;i++) {
            Antmicro.Renode.Peripherals.UART.LegoLpf2ElectricalPort port;
            emulation.ExternalsManager.TryGetByName("port"+names[i],out port);
            port.Attach("motor");
            var g1=(Antmicro.Renode.Peripherals.GPIOPort.STM32_GPIOPort)machine["sysbus.gpioPort"+banks1[i]];
            var g2=(Antmicro.Renode.Peripherals.GPIOPort.STM32_GPIOPort)machine["sysbus.gpioPort"+banks2[i]];
            var timer=(Antmicro.Renode.Peripherals.Timers.BrickwrightSTM32_Timer)machine["sysbus."+timerNames[i]];
            var af=(uint)(i<2 ? 1 : 2);
            SetMode(g1,pins1[i],2);SetMode(g2,pins2[i],1);SetHigh(g2,pins2[i]);SetAf(g1,pins1[i],af);
            timer.WriteDoubleWord(0x2c,999);timer.WriteDoubleWord(0x18,0x6060);timer.WriteDoubleWord(0x1c,0x6060);
            timer.WriteDoubleWord(0x20,0x3333);timer.WriteDoubleWord(0x44,0x8000);timer.WriteDoubleWord(0,1);
            foreach(var register in new long[]{0x34,0x38,0x3c,0x40})timer.WriteDoubleWord(register,500);
            port.Tick();var motor=(Antmicro.Renode.Peripherals.UART.Lpf2ElectricalMotor)port.Device;
            if(motor.Power!=50)throw new System.Exception("forward bridge failed on "+names[i]+": "+motor.Power);
            SetMode(g1,pins1[i],1);SetHigh(g1,pins1[i]);SetMode(g2,pins2[i],2);SetAf(g2,pins2[i],af);
            foreach(var register in new long[]{0x34,0x38,0x3c,0x40})timer.WriteDoubleWord(register,250);
            port.Tick();if(motor.Power!=-25)throw new System.Exception("reverse bridge failed on "+names[i]);
            SetMode(g2,pins2[i],1);SetHigh(g2,pins2[i]);port.Tick();
            if(motor.Power!=0)throw new System.Exception("brake bridge failed on "+names[i]);
        }
        // Exercise a real CPU-facing UART write through the connector.
        var uart=(Antmicro.Renode.Peripherals.Bus.IDoubleWordPeripheral)machine["sysbus.uart7"];
        wiringWrites=0;
        machine.ObtainManagedThread(() => {
            if(wiringWrites!=0)return;
            uart.WriteDoubleWord(0xc,0x2008);uart.WriteDoubleWord(0x4,0);wiringWrites++;
        },1000,name:"Prime source wiring fixture",owner:(Antmicro.Renode.Peripherals.IPeripheral)uart).Start();
        return "Prime UART wiring fixture scheduled";
    }
    public static string ConfirmPrimeWiring(this Antmicro.Renode.Core.Emulation emulation) {
        if(wiringWrites!=1)throw new System.Exception("UART fixture callback did not execute");
        return "PASS 6 Prime UART endpoint registrations, forward/reverse/brake bridges and timed transfer";
    }
    private static void SetMode(Antmicro.Renode.Peripherals.GPIOPort.STM32_GPIOPort gpio,int pin,uint mode) {
        gpio.WriteDoubleWord(0,(gpio.ReadDoubleWord(0)&~(3u<<(pin*2)))|(mode<<(pin*2)));
    }
    private static void SetHigh(Antmicro.Renode.Peripherals.GPIOPort.STM32_GPIOPort gpio,int pin) {
        gpio.WriteDoubleWord(0x14,gpio.ReadDoubleWord(0x14)|(1u<<pin));
    }
    private static void SetAf(Antmicro.Renode.Peripherals.GPIOPort.STM32_GPIOPort gpio,int pin,uint af) {
        var offset=pin<8 ? 0x20 : 0x24;var shift=(pin%8)*4;
        gpio.WriteDoubleWord(offset,(gpio.ReadDoubleWord(offset)&~(15u<<shift))|(af<<shift));
    }
    private static int wiringWrites;
}
'''
    imports.add('using Antmicro.Renode.Peripherals;')
    (output / 'tests.cs').write_text('\n'.join(sorted(imports)) + '\n' + '\n'.join(bodies) + helper)
    (output / 'loop.bin').write_bytes(bytes.fromhex('0000012009000008fee7'))
    (output / 'test.resc').write_text('\n'.join((
        'include @' + str(output / 'models.cs'), 'include @' + str(output / 'tests.cs'),
        'emulation RunPrimeSourceFixtures', 'mach create "source-fixture"',
        'machine LoadPlatformDescription @' + str(output / 'platforms/boards/spike-prime.repl'),
        'sysbus LoadBinary @' + str(output / 'loop.bin') + ' 0x08000000',
        'cpu SP 0x20010000', 'cpu PC 0x08000009',
        'emulation CreatePrimeElectricalPorts "source-fixture"', 'emulation CheckPrimeWiring',
        'emulation RunFor "0.01"', 'emulation ConfirmPrimeWiring', 'quit', '')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infrastructure', type=Path, required=True)
    parser.add_argument('--renode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    prepare(args.infrastructure.resolve(), output)
    with (output / 'test.log').open('wb') as log:
        result = subprocess.run([str(args.renode.resolve()), '--disable-xwt', '--console', '--plain', str(output / 'test.resc')], stdout=log, stderr=subprocess.STDOUT, timeout=180)
    transcript = (output / 'test.log').read_text(errors='replace')
    if result.returncode or 'PASS 9 display-clock fixtures; 24 I2C stream fixtures; ADC trigger/halfword fixture; repeated SPI DMA read fixture; 3 timer rollover fixtures; 9 timer software-event fixtures; 12 inclusive-period fixtures; PASS 35 electrical' not in transcript or 'PASS 6 Prime UART endpoint' not in transcript or 'There was an error' in transcript:
        raise SystemExit('Prime source model checks failed; inspect test.log')
    print('Prime source model and wiring checks passed.')
