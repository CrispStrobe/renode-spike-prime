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
    def motor(port):return externals['port'+chr(65+port)].Device
    for port in range(6):
        initial=float(motor(port).PositionDegrees)
        upload(200+port,struct.pack('<12i',1,port,300,0,2,150,0,0,0,0,0,0))
        run(60)
        state=observe('native-speed-'+chr(65+port))
        observations[-1]['delta']=float(motor(port).PositionDegrees)-initial
        if state['state']!=2 or observations[-1]['delta']<=0.1:raise Exception('native motor did not move: '+str(port))
        run(400);complete('native speed complete',observe('native-complete-'+chr(65+port)))
        if motor(port).Power!=0:raise Exception('completion did not release port '+str(port))
        initial=float(motor(port).PositionDegrees)
        upload(220+port,struct.pack('<8i',6,port,-30,300,0,0,0,0))
        for attempt in range(40):
            run(50)
            state=observe('native-position-'+chr(65+port))
            if state['state'] in (3,5):break
        complete('native position',state)
        delta=float(motor(port).PositionDegrees)-initial
        observations[-1]['delta']=delta
        if abs(delta+30)>3:raise Exception('position exceeds 3 degree tolerance on '+str(port))
    rows=[(1,p,200 if p%2==0 else -200,0) for p in range(6)]+[(2,1000,0,0),(0,0,0,0)]
    payload=''.join(struct.pack('<4i',*row) for row in rows)
    upload(250,payload);run(100)
    if observe('all-six-concurrent')['state']!=2:raise Exception('six-port program ended early')
    for p in range(6):
        if abs(motor(p).AngularVelocityDegreesPerSecond)<1:raise Exception('concurrent port inactive: '+str(p))
    exchange(header(4,250));run(300)
    if observe('all-six-cancelled')['state']!=4:raise Exception('STOP was not retained')
    for p in range(6):
        if motor(p).Power!=0 or abs(motor(p).AngularVelocityDegreesPerSecond)>1:raise Exception('STOP left motor active: '+str(p))
    source='import brickwright as bw\n'
    # Use existing numeric port API; no generated names or firmware imports.
    source+='for p in range(6):\n bw.motor(p,200)\n'
    source+='while True:\n bw.sleep_ms(10)\n'
    upload(260,source,True);run(100)
    if observe('python-six-running')['state']!=2:raise Exception('Python did not run six ports')
    for p in range(6):
        if motor(p).Power==0:raise Exception('Python left port inactive: '+str(p))
    exchange(header(4,260));run(300)
    if observe('python-six-cancelled')['state']!=4:raise Exception('Python STOP not retained')
    for p in range(6):
        if motor(p).Power!=0 or abs(motor(p).AngularVelocityDegreesPerSecond)>1:raise Exception('Python STOP left motor active: '+str(p))
    result={'passed':True,'observations':observations}
except Exception as error:
    result={'passed':False,'error':str(error),'observations':observations}
f=open(_bw_nuttx_config['result'],'w');json.dump(result,f);f.close()
