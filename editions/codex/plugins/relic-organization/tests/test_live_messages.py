import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from relic_org.store import Store, OrgError
spec=importlib.util.spec_from_file_location('message_hook',ROOT/'hooks/hook.py')
hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)


class LiveMessageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.db')
        self.org=self.store.create('Organization',[{'thread_id':i} for i in ('a','b')],'a')
        self.id=self.org['id']

    def tearDown(self):self.tmp.cleanup()

    def message(self, mode):
        return self.store.execute(self.id,'a','message_send',{'body':'Peer correction','recipients':['b'],'idempotency_key':mode,'delivery_mode':mode})

    def event(self, kind='PostToolUse'):
        return {'hook_event_name':kind,'session_id':'b','turn_id':'active-turn','tool_name':'Bash','tool_input':{'cmd':'read'},'tool_response':{'exit_code':0}}

    def test_midturn_context_is_offered_once_and_ack_is_independent(self):
        msg=self.message('immediate')
        result=hook.handle(self.event(),self.store)
        self.assertIn('Peer correction',result['hookSpecificOutput']['additionalContext'])
        receipt=self.store.get(self.id)['messages'][msg['id']]['deliveries']['b']
        self.assertEqual(receipt['status'],'pending')
        self.assertEqual(receipt['context_turn_id'],'active-turn')
        self.assertEqual(receipt['context_state'],'offered')
        self.assertNotIn('additionalContext',hook.handle(self.event(),self.store).get('hookSpecificOutput',{}))
        ack=self.store.execute(self.id,'b','message_ack',{'message_id':msg['id']})
        self.assertEqual(ack['deliveries']['b']['context_state'],'acknowledged')

    def test_after_turn_message_and_paused_org_do_not_inject(self):
        self.message('after_turn')
        self.assertNotIn('hookSpecificOutput',hook.handle(self.event(),self.store))
        self.message('immediate')
        self.store.human_control(self.id,'pause')
        self.assertEqual(hook.handle(self.event(),self.store),{})

    def test_stop_boundary_continues_once_without_claiming_success(self):
        self.message('immediate')
        result=hook.handle(self.event('Stop'),self.store)
        self.assertEqual(result['decision'],'block')
        self.assertIn('Peer correction',result['reason'])
        self.assertEqual(hook.handle({**self.event('Stop'),'stop_hook_active':True},self.store),{})

    def test_default_mode_leader_permission_and_explicit_retry_mode(self):
        self.store.execute(self.id,'a','message_configure',{'delivery_mode':'immediate'})
        msg=self.store.execute(self.id,'a','message_send',{'body':'Default','recipients':['b'],'idempotency_key':'default'})
        self.assertEqual(msg['delivery_mode'],'immediate')
        with self.assertRaises(OrgError):
            self.store.execute(self.id,'b','message_configure',{'delivery_mode':'after_turn'})
        with self.assertRaises(OrgError):
            self.store.execute(self.id,'a','message_send',{'body':'Default','recipients':['b'],'idempotency_key':'default','delivery_mode':'after_turn'})

if __name__=='__main__':unittest.main()
