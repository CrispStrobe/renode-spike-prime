// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Brickwright contributors
using System;
using System.Linq;
using System.Threading.Tasks;
using System.Threading;
using Antmicro.Renode.Tools;
class Tests {
static int checks;
static void Check(bool b,string label) {if(!b) throw new Exception(label);checks++;}
static void Throws<T>(Action a) where T:Exception { try {a();} catch(T) {checks++;return;} throw new Exception("Expected "+typeof(T)); }
static BrickwrightProgramUart Attached(out FakeUart u) { u=new FakeUart();var b=new BrickwrightProgramUart(7);b.AttachTo(u);return b; }
static void Main() {
Throws<ArgumentOutOfRangeException>(()=>new BrickwrightProgramUart(0));
Throws<ArgumentOutOfRangeException>(()=>new BrickwrightProgramUart(-1));
Throws<ArgumentOutOfRangeException>(()=>new BrickwrightProgramUart(9007199254740992L));
using(var b=new BrickwrightProgramUart(9007199254740991L)) {Check(b.Generation==9007199254740991L,"generation upper bound");Throws<InvalidOperationException>(()=>b.Read(b.Generation,1));}
var t=Attached(out var u);Check(u.Machine.Period==100&&u.Machine.Clock.Started&&u.Machine.Clock.Delayed==0,"immediate managed 100us start");
Throws<ArgumentException>(()=>t.QueueWrite(8,new byte[]{1}));Throws<ArgumentException>(()=>t.Read(8,1));
Throws<ArgumentOutOfRangeException>(()=>t.QueueWrite(7,new byte[0]));Throws<ArgumentOutOfRangeException>(()=>t.QueueWrite(7,new byte[33]));Throws<ArgumentNullException>(()=>t.QueueWrite(7,null));
Throws<ArgumentOutOfRangeException>(()=>t.Read(7,0));Throws<ArgumentOutOfRangeException>(()=>t.Read(7,4097));
var original=Enumerable.Range(0,32).Select(i=>(byte)i).ToArray();t.QueueWrite(7,original);original[0]=99;
Check(u.Written.Count==0&&t.AcceptedInputBytes==32&&t.ReleasedInputBytes==0,"acceptance is only queueing");
u.Machine.Clock.Tick();Check(u.Written.SequenceEqual(new byte[]{0})&&t.PendingInputCount==31,"one release each tick plus caller copy");
for(int i=0;i<31;i++)u.Machine.Clock.Tick();Check(u.Written.SequenceEqual(Enumerable.Range(0,32).Select(i=>(byte)i)),"FIFO input");
u.Machine.Clock.Tick();Check(u.Written.Count==32,"empty tick no write");
for(int i=0;i<8;i++)t.QueueWrite(7,new byte[32]);Throws<InvalidOperationException>(()=>t.QueueWrite(7,new byte[]{1}));Check(t.PendingInputCount==256&&t.AcceptedInputBytes==288,"atomic input overflow rejection");
u.Machine.Clock.Tick();Throws<InvalidOperationException>(()=>t.QueueWrite(7,new byte[]{1,2}));Check(t.PendingInputCount==255&&t.AcceptedInputBytes==288,"atomic partial capacity rejection");
for(int i=0;i<5000;i++)u.Emit((byte)i);var part=t.Read(7,4096);Check(part.Length==4096&&part.Select((v,i)=>v==(byte)i).All(x=>x),"FIFO read maximum");Check(t.Read(7,4096).Length==904&&t.Read(7,1).Length==0,"read drains");
int unrelated=0;u.CharReceived+=v=>unrelated++;
// During detach Read fails as unavailable; task completes with an expected exception.
u.Machine.PauseHook=()=> {var work=Task.Run(()=> {try {t.Read(7,1);}catch(InvalidOperationException){}});Check(work.Wait(2000),"pause does not hold queue lock");};
t.DetachFrom(u);Check(u.Subscribers==1&&u.Machine.Clock.Stopped&&u.Machine.Clock.Disposed&&t.PendingInputCount==0&&t.BufferedOutputCount==0,"detach owns handler and clears queues");u.Emit(1);Check(unrelated==1,"other handler retained");u.Machine.Clock.Action();Check(u.Written.Count==33,"stale tick after detach inert");Throws<InvalidOperationException>(()=>t.AttachTo(u));Throws<InvalidOperationException>(()=>t.QueueWrite(7,new byte[]{1}));t.Dispose();t.Dispose();Check(t.IsDisposed,"idempotent dispose");
var budget=Attached(out var bu);for(int i=0;i<2048;i++){budget.QueueWrite(7,new byte[32]);for(int j=0;j<32;j++)bu.Machine.Clock.Tick();}Check(budget.AcceptedInputBytes==65536&&budget.ReleasedInputBytes==65536,"lifetime budget exact");Throws<InvalidOperationException>(()=>budget.QueueWrite(7,new byte[]{1}));Check(budget.PendingInputCount==0,"budget rejection no enqueue");budget.Dispose();
var overflow=Attached(out var ou);overflow.QueueWrite(7,new byte[]{42});for(int i=0;i<65536;i++)ou.Emit((byte)i);Check(!overflow.IsFaulted&&overflow.BufferedOutputCount==65536,"output accepts exact capacity");ou.Emit(1);Check(overflow.IsFaulted&&overflow.FaultReason!=null&&overflow.BufferedOutputCount==65536,"output overflow explicit fault");Throws<InvalidOperationException>(()=>overflow.Read(7,1));Throws<InvalidOperationException>(()=>overflow.QueueWrite(7,new byte[]{1}));ou.Machine.Clock.Tick();Check(ou.Written.Count==0,"fault blocks releases");overflow.Dispose();Check(overflow.BufferedOutputCount==0,"fault disposal clears output");
var callback=Attached(out var cu);cu.OnWrite=v=>Throws<InvalidOperationException>(()=>callback.Dispose());callback.QueueWrite(7,new byte[]{1});cu.Machine.Clock.Tick();Check(!callback.IsDisposed&&!callback.IsFaulted,"own callback rejects lifecycle teardown");Task.Run(()=>callback.Dispose()).GetAwaiter().GetResult();Check(callback.IsDisposed,"another host thread may teardown");cu.Machine.Clock.Action();Check(cu.Written.Count==1,"no write after disposed");Throws<ObjectDisposedException>(()=>callback.QueueWrite(7,new byte[]{1}));Throws<ObjectDisposedException>(()=>callback.Read(7,1));
var broken=Attached(out var xu);xu.OnWrite=v=>throw new Exception("synthetic");broken.QueueWrite(7,new byte[]{1,2});xu.Machine.Clock.Tick();Check(broken.IsFaulted&&broken.ReleasedInputBytes==0,"write exception faults indeterminate delivery");xu.Machine.Clock.Tick();Check(broken.PendingInputCount==1,"fault no additional release");broken.Dispose();
var wrap=Attached(out var wu);for(int i=0;i<60000;i++)wu.Emit((byte)i);for(int i=0;i<14;i++)wrap.Read(7,4096);var tail=wrap.Read(7,4096);Check(tail.Length==2656,"output initial drain");for(int i=0;i<12000;i++)wu.Emit((byte)i);int offset=0;while(wrap.BufferedOutputCount>0){var data=wrap.Read(7,4096);Check(data.Select((v,i)=>v==(byte)(offset+i)).All(x=>x),"output FIFO across ring wrap");offset+=data.Length;}wrap.Dispose();
var race=Attached(out var ru);var entered=new ManualResetEventSlim();var release=new ManualResetEventSlim();ru.OnWrite=v=>{entered.Set();if(!release.Wait(2000))throw new Exception("release timeout");};race.QueueWrite(7,new byte[]{1,2});var tick=Task.Run(()=>ru.Machine.Clock.Tick());Check(entered.Wait(2000),"release started");var disposing=Task.Run(()=>race.Dispose());release.Set();Task.WaitAll(tick,disposing);ru.Machine.Clock.Action();Check(race.IsDisposed&&ru.Written.Count==1,"teardown waits in-flight release and blocks subsequent tick");entered.Dispose();release.Dispose();
var threaded=Attached(out var tu);tu.OnWrite=v=>{var emitted=Task.Run(()=>tu.Emit(v));if(!emitted.Wait(2000))throw new Exception("cross-thread CharReceived blocked");};threaded.QueueWrite(7,new byte[]{61,62});tu.Machine.Clock.Tick();Check(!threaded.IsFaulted&&tu.Written.SequenceEqual(new byte[]{61}),"WriteChar can wait for cross-thread output callback");Check(threaded.Read(7,2).SequenceEqual(new byte[]{61}),"cross-thread output captured");tu.Machine.Clock.Tick();Check(threaded.Read(7,1).SequenceEqual(new byte[]{62}),"cross-thread output FIFO");threaded.Dispose();
var threadedOverflow=Attached(out var tou);for(int i=0;i<65536;i++)tou.Emit(0);tou.OnWrite=v=>{var emitted=Task.Run(()=>tou.Emit(v));if(!emitted.Wait(2000))throw new Exception("cross-thread overflow callback blocked");};threadedOverflow.QueueWrite(7,new byte[]{11,12});tou.Machine.Clock.Tick();Check(threadedOverflow.IsFaulted&&threadedOverflow.FaultReason=="Guest output capacity exceeded.","cross-thread capture can atomically fault without input lock");tou.Machine.Clock.Tick();Check(tou.Written.Count==1&&threadedOverflow.PendingInputCount==1,"cross-thread fault suppresses next release");Throws<InvalidOperationException>(()=>threadedOverflow.Read(7,1));threadedOverflow.Dispose();
Console.WriteLine("PASS: "+checks+" synthetic checks; stubs only, not actual Renode integration.");
}
}
