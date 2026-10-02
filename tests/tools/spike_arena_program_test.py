# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import pathlib, sys, unittest, ast, types
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
import spike_arena_mailbox as m
class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.words = {m.BASE:m.SIGNATURE, m.PROGRAM_BASE:m.PROGRAM_SIGNATURE, m.PROGRAM_BASE+4:1}
        self.writes = []
    def read(self, address): return self.words.get(address, 0)
    def write(self, address, value): self.writes.append((address,value)); self.words[address]=value
    def test_committed_fixed_address_code_and_single_load(self):
        p={'version':1,'instructions':[[1,1,-1110,0],[2,100,0,0],[0,0,0,0]]}
        m.write_program(p,self.read,self.write)
        self.assertEqual(self.writes[0],(m.PROGRAM_BASE+8,1))
        self.assertEqual(self.writes[-1],(m.PROGRAM_BASE+8,2))
        self.assertEqual(self.words[m.PROGRAM_BASE+28+8],(-1110)&0xffffffff)
        before=list(self.writes)
        with self.assertRaises(ValueError): m.write_program(p,self.read,self.write)
        self.assertEqual(before,self.writes)
    def test_invalid_programs_never_write(self):
        for code in [[], [[1,0,1111,0],[0,0,0,0]], [[4,9,0,0],[0,0,0,0]], [[0,False,0,0]], [[0,0,0,0]]*257,
                     [[3,3,2,0],[0,0,0,0]], [[6,0,36001,1],[0,0,0,0]], [[1,1,300,0]]]:
            with self.assertRaises(ValueError): m.write_program({'version':1,'instructions':code},self.read,self.write)
            self.assertEqual(self.writes,[])
    def test_legacy_guest_refused_without_writes(self):
        self.words[m.PROGRAM_BASE]=0
        with self.assertRaises(ValueError): m.write_program({'version':1,'instructions':[[0,0,0,0]]},self.read,self.write)
        self.assertEqual(self.writes,[])
    def test_float_version_and_extra_fields_refuse(self):
        for program in [{'version':1.0,'instructions':[[0,0,0,0]]}, {'version':1,'instructions':[[0,0,0,0]],'address':0x20000000}]:
            with self.assertRaises(ValueError): m.write_program(program,self.read,self.write)
            self.assertEqual(self.writes,[])
    def test_boundary_sensor_and_jump_instructions(self):
        m.validate_program({'version':1,'instructions':[[3,1,65535,0],[3,4,255,0],[5,3,1,4],[6,0,-36000,1110],[4,0,0,0],[0,0,0,0]]})
class SnapshotTests(unittest.TestCase):
    def test_torn_observation_retries_once_paused_and_releases_scope(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        tree=ast.parse((root/'scripts/spike-state-server.py').read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_snapshot')
        calls=[]
        scope=types.SimpleNamespace(Dispose=lambda:calls.append('release'))
        machine=types.SimpleNamespace(SystemBus=types.SimpleNamespace(ReadBytes=lambda *a:None,ReadDoubleWord=lambda *a:0),
                                      ObtainPausedState=lambda value:(calls.append('pause') or scope))
        def read(*args):
            calls.append('read')
            if len(calls)==1: raise ValueError('arena guest frame changed during observation')
            return 'coherent'
        mailbox=types.SimpleNamespace(read_state=read,snapshot=lambda data,*args:data)
        namespace={'monitor':types.SimpleNamespace(Machine=machine),'spike_arena_mailbox':mailbox}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'monitor-snapshot-test','exec'),namespace)
        self.assertEqual(namespace['_snapshot']({'identity':{'firmware':'brickwright-arena-demo'}},1,1),'coherent')
        self.assertEqual(calls,['read','pause','read','release'])
        calls.clear()
        mailbox.read_state=lambda *args:(_ for _ in ()).throw(ValueError('arena guest has not initialized its mailbox'))
        with self.assertRaisesRegex(ValueError,'initialized'):namespace['_snapshot']({'identity':{'firmware':'brickwright-arena-demo'}},1,1)
        self.assertEqual(calls,[])
if __name__=='__main__': unittest.main()
