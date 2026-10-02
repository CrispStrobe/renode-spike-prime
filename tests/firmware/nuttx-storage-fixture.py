# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
# Source-built firmware only: independent processes share raw simulated flash.
import sys, struct, json
from System.IO import File
from Antmicro.Renode.Time import TimeInterval
sys.path.insert(0,_bw_nuttx_config['tools'])
import spike_nuttx_mailbox as mb
bus=self.Machine['sysbus']
base=mb.validate_base(_bw_nuttx_config['programMailbox'])
emu=emulationManager.CurrentEmulation
observations=[]
def run(ms):emu.RunFor(TimeInterval.FromMilliseconds(ms))
def header(op,ident):return struct.pack('<4BI',0x70,1,op,0,ident)
def exchange(packet,expected=0):
    seq=mb.submit(base,list(bytearray(packet)),bus.ReadDoubleWord,bus.WriteDoubleWord)
    for attempt in range(100):
        run(10)
        reply=mb.reply(base,seq,bus.ReadDoubleWord,bus.ReadBytes)
        if reply is not None:
            reply=bytearray(reply);rc=struct.unpack('<i',str(reply[8:12]))[0]
            if rc!=expected:raise Exception('unexpected result '+str(rc)+' expected '+str(expected))
            return reply
    raise Exception('packet timeout')
def crc(data):
    value=0xffffffff
    for byte in bytearray(data):
        value^=byte
        for unused in range(8):value=(value>>1)^(0xedb88320 if value&1 else 0)
    return value^0xffffffff
def upload(ident,payload,python=False):
    exchange(header(7 if python else 0,ident)+struct.pack('<II',len(payload) if python else len(payload)//16,crc(payload)))
    exchange(header(8,ident),-16) # SAVE during staging cannot replace the slot.
    for offset in range(0,len(payload),10):exchange(header(1,ident)+struct.pack('<H',offset)+payload[offset:offset+10])
    exchange(header(2,ident))
def check(label,state):
    observations.append({'scenario':label,'status':state})
    return state
def status(label):return check(label,mb.status(base,bus.ReadDoubleWord,bus.ReadBytes))
def snapshot(name):
    memory=self.Machine['sysbus.spi2.primeStorageMux.primeStorage'].UnderlyingMemory
    File.WriteAllBytes(_bw_nuttx_config['output']+'/'+name+'-flash.bin',memory.ReadBytes(0,0x2000000))
try:
    log=''.join(chr(int(b)) for b in bus.ReadBytes(_bw_nuttx_config['ramlogBase'],_bw_nuttx_config['ramlogSize']))
    if 'LittleFS mounted at /mnt/flash' not in log:raise Exception('LittleFS not mounted')
    phase=_bw_nuttx_config['phase']
    if status('boot-empty')['state']!=0:raise Exception('unexpected automatic execution/load')
    if phase=='write':
        exchange(header(9,301),-2)
        upload(301,struct.pack('<8i',2,50,0,0,0,0,0,0)+'\x00'*(254*16))
        exchange(header(8,301));snapshot('native')
        exchange(header(3,301));exchange(header(8,301),-16)
        run(100)
        if status('native-complete')['state']!=3:raise Exception('native failed')
        source='assert sum(range(11)) == 55\n#'
        upload(302,source+' '*(4095-len(source)),True)
        exchange(header(3,302));run(100)
        if status('python-complete')['state']!=3:raise Exception('Python failed')
        # Saving AFTER Python completion must retain source/language.
        exchange(header(8,302));snapshot('python')
        exchange(header(9,301),-2)
        if status('wrong-id-preserved')['id']!=302:raise Exception('failed load replaced committed program')
    else:
        ident=301 if phase=='native' else 302
        exchange(header(9,ident))
        if status('restored-ready')['state']!=1:raise Exception('load did not leave READY')
        exchange(header(3,ident));run(100)
        if status('restored-complete')['state']!=3:raise Exception('restored execution failed')
    result={'passed':True,'observations':observations}
except Exception as error:result={'passed':False,'error':str(error),'observations':observations}
f=open(_bw_nuttx_config['result'],'w');json.dump(result,f);f.close()
