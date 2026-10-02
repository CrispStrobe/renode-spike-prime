# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import pathlib
import struct
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
import spike_arena_mailbox as m

class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.words = [m.SIGNATURE, 1, 200, 0, 1000, 255, 0, 0, 0, 0, 0, 0,
                      -30000, 30000, -300, 300, 0, 0, 2, -300, 300]
        self.writes = []
    def read(self, address):
        if address >= m.PROGRAM_BASE: return 0
        return self.words[(address-m.BASE)//4] & 0xffffffff
    def raw(self, address, size): return struct.pack('<21i', *self.words)
    def write(self, address, value):
        self.writes.append((address, value))
        self.words[(address-m.BASE)//4] = value if value < 0x80000000 else value-0x100000000
    def test_observation_uses_guest_time_and_signed_positions(self):
        data = m.read_state(self.raw, self.read)
        frame = m.snapshot(data, {'firmware':'brickwright-arena-demo'}, 3, 7)
        self.assertEqual(frame['clockNs'], 200000000)
        self.assertEqual(frame['motors'][0]['position'], -30)
        self.assertEqual(frame['motors'][1]['demandDirection'], 1)
        self.assertEqual(frame['lifecycle']['connectionGeneration'], 7)
    def test_invalid_and_torn_frames_are_rejected(self):
        for index, value in [(0,0), (1,2), (2,3601001), (18,3), (3,1)]:
            old=self.words[index]; self.words[index]=value
            with self.assertRaises(ValueError): m.read_state(self.raw,self.read)
            self.words[index]=old
        def changing(address):
            self.words[18] += 2
            return self.read(address)
        with self.assertRaises(ValueError): m.read_state(self.raw,changing)
    def test_input_commit_is_bounded_and_sequenced(self):
        m.write_inputs({'sensors':[{'port':'D','kind':'distance','values':{'distanceMillimeters':-1}}],
                        'loads':[{'port':'A','percent':100}]},self.read,self.write)
        self.assertEqual(self.writes,[(m.BASE+12,1),(m.BASE+16,0xffffffff),(m.BASE+40,100),(m.BASE+12,2)])
    def test_wrong_ports_late_values_and_odd_sequence_never_write(self):
        for frame in [ {'sensors':[], 'loads':[{'port':'C','percent':10}]},
                       {'sensors':[], 'loads':[{'port':'A','percent':101}]},
                       {'sensors':[{'port':'C','kind':'distance','values':{'distanceMillimeters':1}}], 'loads':[]} ]:
            with self.assertRaises(ValueError): m.write_inputs(frame,self.read,self.write)
            self.assertEqual(self.writes,[])
        self.words[3]=1
        with self.assertRaises(ValueError): m.write_inputs({'sensors':[], 'loads':[]},self.read,self.write)
        self.assertEqual(self.writes,[])
    def test_failed_write_leaves_uncommitted_frame(self):
        def fail(address,value):
            if address != m.BASE+12: raise IOError('connection lost')
            self.write(address,value)
        with self.assertRaises(IOError): m.write_inputs({'sensors':[], 'loads':[{'port':'A','percent':50}]},self.read,fail)
        self.assertEqual(self.words[3],1)

if __name__ == '__main__': unittest.main()
