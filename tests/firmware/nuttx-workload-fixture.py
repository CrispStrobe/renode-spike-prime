# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
# Actual protected guest workload, using only packet requests and public inputs.
execfile(_bw_nuttx_config['fixtureRoot']+'/nuttx-robot-fixture.py')
try:
    if not result['passed']:raise Exception('baseline robot scenarios failed: '+result.get('error',''))
    def request(packet,expected=0):
        seq=mb.submit(base,list(bytearray(packet)),bus.ReadDoubleWord,bus.WriteDoubleWord)
        for attempt in range(100):
            run(10)
            reply=mb.reply(base,seq,bus.ReadDoubleWord,bus.ReadBytes)
            if reply is not None:
                rc=struct.unpack('<i',str(bytearray(reply)[8:12]))[0]
                if rc!=expected:raise Exception('unexpected packet result '+str(rc)+' expected '+str(expected))
                return
        raise Exception('workload packet exceeded one guest second')
    for cycle in range(30):
        ident=400+cycle
        apply_arena_inputs({'sensors':[{'port':'E','kind':'force','values':{'forcePercent':0,'pressed':False}}],'loads':[]},device)
        positions=[float(device(p).PositionDegrees) for p in 'AB']
        sign=1 if cycle%2==0 else -1
        rows=[(1,0,200*sign,0),(1,1,-200*sign,0),(3,3,1,0),(0,0,0,0)]
        upload(ident,''.join(struct.pack('<4i',*row) for row in rows))
        run(100)
        state=observe('workload-running-'+str(cycle))
        if state['state']!=2 or state['pc']!=2:raise Exception('sensor wait did not retain running motors')
        for p,initial,direction in zip('AB',positions,(sign,-sign)):
            if (float(device(p).PositionDegrees)-initial)*direction<=0.1 or device(p).Power==0:
                raise Exception('workload motor motion absent or wrong direction')
        request(header(8,ident),-16) # busy SAVE cannot replace persistent data
        request(header(9,ident),-16) # busy LOAD cannot replace the running job
        if cycle:
            request(header(4,ident-1),-22) # old program cannot stop its successor
            if observe('stale-stop-refused-'+str(cycle))['state']!=2:raise Exception('old owner stopped replacement')
        if cycle%2:
            request(header(4,ident));run(100)
            if observe('workload-cancelled-'+str(cycle))['state']!=4:raise Exception('cancel not retained')
        else:
            apply_arena_inputs({'sensors':[{'port':'E','kind':'force','values':{'forcePercent':75,'pressed':True}}],'loads':[]},device)
            run(200)
            complete('workload sensor completion',observe('workload-completed-'+str(cycle)))
        for p in 'AB':
            if device(p).Power!=0:raise Exception('terminal workload left motor powered')
        request(header(8,ident));request(header(9,ident))
        state=observe('workload-restored-'+str(cycle))
        if state['id']!=ident or state['state']!=1:raise Exception('saved workload did not restore READY')
        with open(_bw_nuttx_config['progress'],'w') as progress:
            progress.write(json.dumps({'cycle':cycle+1,'guestClockMs':state['clockMs']}))
    result={'passed':True,'cycles':30,'observations':observations}
except Exception as error:
    result={'passed':False,'error':str(error),'observations':observations}
with open(_bw_nuttx_config['result'],'w') as output:
    output.write(json.dumps(result,ensure_ascii=True))
