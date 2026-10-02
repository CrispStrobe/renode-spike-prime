# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
# External robot-program scenarios against our source-built protected firmware.
import sys, struct, json
from Antmicro.Renode.Time import TimeInterval
sys.path.insert(0,_bw_nuttx_config['tools'])
import spike_nuttx_mailbox as mb
bus=self.Machine['sysbus']
base=mb.validate_base(_bw_nuttx_config['programMailbox'])
emu=emulationManager.CurrentEmulation
observations=[]
def run(ms):
    emu.RunFor(TimeInterval.FromMilliseconds(ms))
def observe(label):
    for attempt in range(10):
        try:
            state=mb.status(base,bus.ReadDoubleWord,bus.ReadBytes)
            break
        except ValueError as error:
            if str(error)!='full-firmware publication is not ready or changed' or attempt==9:raise
            run(1)
    observations.append({'scenario':label,'status':state})
    return state
def exchange(packet):
    sequence=mb.submit(base,list(bytearray(packet)),bus.ReadDoubleWord,bus.WriteDoubleWord)
    for attempt in range(10):
        run(10)
        result=mb.reply(base,sequence,bus.ReadDoubleWord,bus.ReadBytes)
        if result is not None:
            result=bytearray(result)
            rc=struct.unpack('<i',str(result[8:12]))[0]
            if rc!=0:raise Exception('firmware rejected packet: '+str(rc))
            return result
    raise Exception('firmware did not acknowledge packet')
def crc(data):
    value=0xffffffff
    for byte in bytearray(data):
        value^=byte
        for unused in range(8):value=(value>>1)^(0xedb88320 if value&1 else 0)
    return value^0xffffffff
def header(op,ident):return struct.pack('<4BI',0x70,1,op,0,ident)
def upload(ident,payload,python=False):
    exchange(header(7 if python else 0,ident)+struct.pack('<II',len(payload) if python else len(payload)//16,crc(payload)))
    for offset in range(0,len(payload),10):exchange(header(1,ident)+struct.pack('<H',offset)+payload[offset:offset+10])
    exchange(header(2,ident));exchange(header(3,ident))
def complete(label,state):
    if state['state']!=3 or state['error']!=0:raise Exception(label+' did not complete: '+str(state))
try:
    bootlog=''.join(chr(int(byte)) for byte in bus.ReadBytes(_bw_nuttx_config['ramlogBase'],_bw_nuttx_config['ramlogSize']))
    if 'W25Q256: LittleFS mounted at /mnt/flash' not in bootlog:
        raise Exception('source-built firmware did not format and mount LittleFS')
    observations.append({'scenario':'littlefs-blank-flash-mounted','passed':True})
    start=observe('boot-ready')
    payload=struct.pack('<8i',2,50,0,0,0,0,0,0)
    upload(101,payload)
    run(100)
    complete('bytecode wait/end',observe('bytecode-wait-end'))
    upload(102,'assert sum(range(11)) == 55\n',True)
    run(30)
    complete('embedded Python arithmetic',observe('python-arithmetic'))
    upload(103,'raise ValueError("synthetic")\n',True)
    run(30)
    state=observe('python-exception')
    if state['state']!=5 or state['error']==0:raise Exception('Python failure was not surfaced')
    upload(104,'while True:\n pass\n',True)
    run(30)
    if observe('python-running')['state']!=2:raise Exception('Python loop did not run')
    exchange(header(4,104));run(30)
    if observe('python-cancelled')['state']!=4:raise Exception('Python cancellation was not retained')
    upload(105,struct.pack('<12i',1,0,300,0,2,200,0,0,0,0,0,0))
    run(100)
    state=observe('motor-A-moving')
    motor=externals['portA'].Device
    observations[-1]['modelPosition']=float(motor.PositionDegrees)
    observations[-1]['modelSpeed']=float(motor.AngularVelocityDegreesPerSecond)
    if state['state']!=2 or state['positions'][0]<=0 or motor.PositionDegrees<=0:raise Exception('motor PWM/encoder path did not move')
    run(400)
    complete('motor speed/wait/brake',observe('motor-A-ended'))
    initial=float(motor.PositionDegrees)
    upload(106,struct.pack('<8i',6,0,30,300,0,0,0,0))
    run(2000)
    state=observe('motor-A-position')
    observations[-1]['modelPosition']=float(motor.PositionDegrees)
    observations[-1]['relativeDegrees']=float(motor.PositionDegrees)-initial
    complete('position control',state)
    if abs(float(motor.PositionDegrees)-initial-30)>3:raise Exception('position was outside 3 degree tolerance')
    from spike_arena_inputs import apply_arena_inputs
    def device(port):return externals['port'+port].Device
    apply_arena_inputs({'sensors':[{'port':'E','kind':'force','values':{'forcePercent':0,'pressed':False}}],'loads':[]},device)
    upload(107,struct.pack('<12i',1,1,-200,0,3,3,1,0,0,0,0,0))
    run(100)
    state=observe('motor-B-concurrent-with-sensor-wait')
    if state['state']!=2 or state['pc']!=1 or device('B').PositionDegrees>=0:raise Exception('concurrent sensor wait/motor path failed')
    apply_arena_inputs({'sensors':[{'port':'E','kind':'force','values':{'forcePercent':75,'pressed':True}}],'loads':[]},device)
    run(200)
    complete('arena force input',observe('force-released-wait'))
    apply_arena_inputs({'sensors':[],'loads':[{'port':'A','percent':100}]},device)
    initial=float(motor.PositionDegrees)
    upload(108,struct.pack('<8i',6,0,90,500,0,0,0,0))
    run(200)
    state=observe('loaded-motor-stall')
    if state['state']!=2 or abs(float(motor.PositionDegrees)-initial)>0.1 or not motor.Stalled:raise Exception('stalled position completed or moved')
    exchange(header(4,108));run(50)
    state=observe('stalled-position-cancelled')
    if state['state']!=4 or abs(motor.AngularVelocityDegreesPerSecond)>1:raise Exception('stalled program did not cancel')
    apply_arena_inputs({'sensors':[],'loads':[{'port':'A','percent':0}]},device)
    result={'passed':True,'observations':observations}
except Exception as error:
    result={'passed':False,'error':str(error),'observations':observations, 'ports':{name:{'state':str(externals['port'+name].State),'time':int(externals['port'+name].EmulatedTimeMicroseconds),'frames':int(externals['port'+name].TransmittedFrames),'received':int(externals['port'+name].ReceivedFrames),'invalid':int(externals['port'+name].InvalidFrames)} for name in 'ABCDE'}}
f=open(_bw_nuttx_config['result'],'w');json.dump(result,f);f.close()
