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
    for name in ('STM32TLCClockTests.cs', 'LegoLpf2ElectricalPortTests.cs', 'STM32F4I2CStreamTests.cs', 'STM32ADCTriggerTests.cs'):
        source = (source_root / name).read_text().replace('using NUnit.Framework;', '')
        source = re.sub(r'\[(?:TestFixture|NonParallelizable|SetUp|TearDown|Test|TestCase\(\d+\))\]', '', source)
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
    public static void AreEqual(object a,object b) { if(!Equal(a,b))throw new System.Exception("source fixture equality failed: "+a+" / "+b); }
    public static void AreNotEqual(object a,object b) { if(Equal(a,b))throw new System.Exception("source fixture inequality failed"); }
}
public static class PrimeSourceFixtureRunner {
    public static string RunPrimeSourceFixtures(this Antmicro.Renode.Core.Emulation emulation) {
        var clock=new Antmicro.Renode.PeripheralsTests.STM32TLCClockTests();
''' + calls + '''
        var i2c=new Antmicro.Renode.PeripheralsTests.STM32F4I2CStreamTests();
        foreach(var count in new[]{1,2,6,32})i2c.ShouldStreamUntilFinalNack(count);
        new Antmicro.Renode.PeripheralsTests.STM32ADCTriggerTests().ShouldSelectEdgesAndScanIdleButtonThroughHalfwordDataReads();
        var electrical=ElectricalTests.RunElectricalTests(emulation);
        return "PASS ''' + str(len(clock_methods)) + ''' display-clock fixtures; 4 I2C stream fixtures; ADC trigger/halfword fixture; "+electrical;
    }
    public static string CheckPrimeWiring(this Antmicro.Renode.Core.Emulation emulation) {
        Antmicro.Renode.Core.IMachine machine;
        if(!emulation.TryGetMachineByName("source-fixture",out machine))throw new System.Exception("fixture machine absent");
        foreach(var name in new[]{"A","B","C","D","E"}) {
            Antmicro.Renode.Peripherals.UART.LegoLpf2ElectricalPort port;
            if(!emulation.ExternalsManager.TryGetByName("port"+name,out port) || port.GetMachine()!=machine)
                throw new System.Exception("UART endpoint must belong to the fixture machine");
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
        return "PASS 5 Prime UART endpoint registrations and timed transfer";
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
    if result.returncode or 'PASS 9 display-clock fixtures; 4 I2C stream fixtures; ADC trigger/halfword fixture; PASS 29 electrical' not in transcript or 'PASS 5 Prime UART endpoint' not in transcript or 'There was an error' in transcript:
        raise SystemExit('Prime source model checks failed; inspect test.log')
    print('Prime source model and wiring checks passed.')
