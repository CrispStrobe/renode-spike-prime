// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Brickwright contributors
using System;
using System.Collections.Generic;
namespace Antmicro.Renode.Core {
public interface IEmulationElement {}
public interface IExternal : IEmulationElement {}
public interface IConnectable<T> { void AttachTo(T obj); void DetachFrom(T obj); }
public interface ISimpleManagedThread : IDisposable { void Start(); void StartDelayed(Antmicro.Renode.Time.TimeInterval delay); void Stop(); }
public interface IManagedThread : ISimpleManagedThread { uint Frequency { get; set; } }
public interface IMachine { IManagedThread ObtainManagedThread(Action action,Antmicro.Renode.Time.TimeInterval period,string name="managed thread",IEmulationElement owner=null,Func<bool> stopCondition=null); IDisposable ObtainPausedState(bool internalPause=false); }
}
namespace Antmicro.Renode.Time { public struct TimeInterval { public ulong Microseconds; public static TimeInterval FromMicroseconds(ulong v) { return new TimeInterval { Microseconds=v }; } } }
namespace Antmicro.Renode.Peripherals {
public interface IPeripheral : Antmicro.Renode.Core.IEmulationElement { void Reset(); }
public static class IPeripheralExtensions { public static Antmicro.Renode.Core.IMachine GetMachine(this IPeripheral p) { return ((FakeUart)p).Machine; } }
}
namespace Antmicro.Renode.Peripherals.UART {
public interface IUART : Antmicro.Renode.Peripherals.IPeripheral { event Action<byte> CharReceived; void WriteChar(byte value); uint BaudRate {get;} Bits StopBits {get;} Parity ParityBit {get;} }
public enum Bits { None,One,Half,OneAndAHalf,Two }
public enum Parity { Odd,Even,None,Forced1,Forced0,Multidrop }
}
public class FakeClock : Antmicro.Renode.Core.IManagedThread {
public Action Action; public bool Started,Stopped,Disposed; public int Delayed; public uint Frequency {get;set;}
public void Start() { Started=true; } public void StartDelayed(Antmicro.Renode.Time.TimeInterval d) { Delayed++; }
public void Stop() { Stopped=true; } public void Dispose() { Disposed=true; }
public void Tick() { if(Started&&!Stopped&&!Disposed) Action(); }
}
public class FakeMachine : Antmicro.Renode.Core.IMachine {
public FakeClock Clock; public ulong Period; public Action PauseHook; public int PauseDepth;
public Antmicro.Renode.Core.IManagedThread ObtainManagedThread(Action a,Antmicro.Renode.Time.TimeInterval p,string name="managed thread",Antmicro.Renode.Core.IEmulationElement owner=null,Func<bool> stopCondition=null) { Period=p.Microseconds; return Clock=new FakeClock { Action=a }; }
public IDisposable ObtainPausedState(bool internalPause=false) { PauseHook?.Invoke(); PauseDepth++; return new Token(this); }
class Token : IDisposable { FakeMachine m; public Token(FakeMachine m) {this.m=m;} public void Dispose() {m.PauseDepth--;} }
}
public class FakeUart : Antmicro.Renode.Peripherals.UART.IUART {
public FakeMachine Machine=new FakeMachine(); public List<byte> Written=new List<byte>(); public Action<byte> OnWrite; public event Action<byte> CharReceived;
public uint BaudRate=>115200; public Antmicro.Renode.Peripherals.UART.Bits StopBits=>Antmicro.Renode.Peripherals.UART.Bits.One; public Antmicro.Renode.Peripherals.UART.Parity ParityBit=>Antmicro.Renode.Peripherals.UART.Parity.None;
public void Reset() {} public void WriteChar(byte v) { OnWrite?.Invoke(v); Written.Add(v); } public void Emit(byte v) {CharReceived?.Invoke(v);} public int Subscribers=>CharReceived?.GetInvocationList().Length??0;
}
