import asyncio
import unittest
from dataclasses import replace
from protocol import Settings, Lines, check_preflight, acknowledgement
from app import Radio


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_combined_notifications(self):
        f=Lines()
        self.assertEqual(f.feed(b'ACK,QP_STA'),[])
        self.assertEqual(f.feed(b'TUS,2\nTM,BODY_RATE,1\n'),['ACK,QP_STATUS,2','TM,BODY_RATE,1'])

    def test_no_movement_in_prepare(self):
        for strategy in ['REACTION','MOMENTUM']:
            plan=Settings(strategy=strategy).plan()
            for cmd in plan:
                self.assertNotIn(cmd.split(',')[0],['RW','RW_BIAS','RW_CMD','MISSION_START'])
                self.assertNotEqual(cmd,'ADCS_MODE,AUTO')
            self.assertEqual(plan[-1],'MISSION_PREPARE')

    def test_invalid_parameters(self):
        for change in [dict(target=float('nan')),dict(target=360),dict(kp=21),
                       dict(strategy='MOMENTUM',bias=99),dict(strategy='MOMENTUM',cw_ms=-1)]:
            with self.assertRaises(ValueError):replace(Settings(),**change).plan()

    def test_preflight(self):
        check_preflight('ACK,QP_STATUS,2,MANUAL,STOPPED,IDLE')
        for line in ['ERR,UNKNOWN_COMMAND','ACK,QP_STATUS,1,MANUAL,STOPPED,IDLE',
                     'ACK,QP_STATUS,2,AUTO,STOPPED,IDLE',
                     'ACK,QP_STATUS,2,MANUAL,REACTION_DRIVE,IDLE',
                     'ACK,QP_STATUS,2,MANUAL,STOPPED,ACQUIRING']:
            with self.assertRaises(ValueError):check_preflight(line)

    def test_ack_boundaries(self):
        self.assertTrue(acknowledgement('SET_TARGET,30','ACK,SET_TARGET,30.00'))
        self.assertFalse(acknowledgement('STOP','ACK,STOPPED'))
        self.assertFalse(acknowledgement('MISSION_START','ACK,MISSION_PREPARE'))


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setup_radio(self):
        r=Radio(loop=asyncio.get_running_loop())
        self.sent=[]
        async def request(cmd):
            self.sent.append(cmd)
            if cmd=='QP_STATUS':return 'ACK,QP_STATUS,2,MANUAL,STOPPED,IDLE'
            return 'ACK,'+cmd.split(',')[0]
        r.request=request
        return r

    async def test_prepare_then_run(self):
        r=self.setup_radio()
        await r.execute(Settings())
        self.assertTrue(r.ready)
        self.assertEqual(self.sent[0],'QP_STATUS')
        self.assertNotIn('MISSION_START',self.sent)
        await r.execute(run=True)
        self.assertEqual(self.sent[-1],'MISSION_START')
        self.assertFalse(r.ready)

    async def test_run_requires_prepare(self):
        r=self.setup_radio()
        with self.assertRaises(ValueError):await r.execute(run=True)
        self.assertEqual(self.sent,[])

    async def test_old_firmware_blocks_all_setup(self):
        r=self.setup_radio()
        async def old(cmd):
            self.sent.append(cmd)
            raise RuntimeError('ERR,UNKNOWN_COMMAND')
        r.request=old
        with self.assertRaises(RuntimeError):await r.execute(Settings())
        self.assertEqual(self.sent,['QP_STATUS'])
        self.assertFalse(r.ready)

    async def test_stop_cancels_remaining_prepare(self):
        r=self.setup_radio();base=r.request;blocked=asyncio.Event()
        async def wait(cmd):
            if cmd=='MISSION_RESET':
                self.sent.append(cmd);blocked.set();await asyncio.sleep(60)
            return await base(cmd)
        r.request=wait
        task=asyncio.create_task(r.execute(Settings()))
        await blocked.wait();await r.stop()
        self.assertTrue(task.cancelled())
        self.assertEqual(self.sent,['QP_STATUS','MISSION_RESET','STOP'])
        self.assertFalse(r.ready)

    async def test_mid_prepare_error_blocks_ready(self):
        r=self.setup_radio();base=r.request
        async def fail(cmd):
            if cmd=='ADCS_PREPARE':raise RuntimeError('ERR,GYRO_NOT_READY')
            return await base(cmd)
        r.request=fail
        with self.assertRaises(RuntimeError):await r.execute(Settings())
        self.assertFalse(r.ready)
        self.assertNotIn('MISSION_PREPARE',self.sent)


if __name__=='__main__':unittest.main()
