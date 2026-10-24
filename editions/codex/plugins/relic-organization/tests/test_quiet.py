import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.quiet import Runner, pending, prompt, status
from relic_org.service import Service
from relic_org.store import Store


class QuietTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/"org.db")
        self.org = self.store.create("Quiet", [{"thread_id": r, "workspace": self.tmp.name} for r in "ab"], "a")
        self.id = self.org["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def message(self, key="work"):
        return self.store.execute(self.id, "a", "message_send", {"body": key, "recipients": ["b"], "idempotency_key": key})

    def test_quiet_default_never_wakes_desktop_and_batches_pending(self):
        class Bridge:
            def send(self, *_):
                raise AssertionError("quiet delivery cannot wake desktop")
        service = Service(self.store, Bridge(), "a")
        with patch("relic_org.quiet.wake") as wake:
            for key in ("one", "two"):
                m = self.message(key)
                service.deliver(self.id, m["id"])
            self.assertEqual(wake.call_count, 2)
        org = self.store.get(self.id)
        self.assertEqual(len(pending(org)["b"]), 2)
        self.assertEqual(org["execution_mode"], "quiet")

    def test_dispatch_waits_for_native_idle_and_ignores_uncertain(self):
        m = self.message()
        other = self.message("uncertain")
        self.store.delivery(self.id, other["id"], "b", "uncertain")
        runner = Runner(self.store, idle_seconds=0)
        with patch("relic_org.quiet.completion_setting", return_value={"disabled":True}), patch.object(runner, "native_states", return_value={"b": "active"}), patch.object(runner, "start") as start:
            runner.tick()
            start.assert_not_called()
        with patch("relic_org.quiet.completion_setting", return_value={"disabled":True}), patch.object(runner, "native_states", return_value={"b": "idle"}), patch.object(runner, "start") as start:
            runner.tick()
            self.assertEqual(start.call_args.args[2], [m["id"]])

    def test_completed_unloaded_chat_can_receive_wake_batch(self):
        m = self.message()
        runner = Runner(self.store, idle_seconds=0)
        runner.native_polls['b'] = {'latestTurn': {'status': 'completed', 'error': None}}
        with patch('relic_org.quiet.completion_setting', return_value={'disabled': True}), patch.object(runner, 'native_states', return_value={'b': 'notLoaded'}), patch.object(runner, 'start') as start:
            runner.tick()
            self.assertEqual(start.call_args.args[2], [m['id']])
        runner.native_polls['b'] = {'latestTurn': {'status': 'failed', 'error': {'message': 'error'}}}
        with patch('relic_org.quiet.completion_setting', return_value={'disabled': True}), patch.object(runner, 'native_states', return_value={'b': 'notLoaded'}), patch.object(runner, 'start') as start:
            runner.tick()
            start.assert_not_called()

    def test_pause_retains_queue_and_missing_notification_setup_does_not_send(self):
        m = self.message()
        self.store.human_control(self.id, "pause")
        self.assertEqual(pending(self.store.get(self.id)), {})
        self.assertEqual(self.store.get(self.id)["messages"][m["id"]]["deliveries"]["b"]["status"], "pending")
        self.store.human_control(self.id, "resume")
        runner=Runner(self.store,idle_seconds=0)
        with patch("relic_org.quiet.completion_setting",return_value={"disabled":False}), patch.object(runner,"native_states",return_value={"b":"idle"}), patch.object(runner,"start") as start:
            runner.tick()
            start.assert_not_called()
        self.assertEqual(status(self.store)["state"],"notification_setup_required")

    def test_batch_recipient_and_acknowledgement_is_not_fabricated(self):
        m = self.message()
        body = prompt(self.org, "b", [m["id"]])
        packet = json.loads(body.splitlines()[1])
        self.assertEqual(packet["to"], "b")
        self.assertEqual(packet["message_ids"], [m["id"]])
        self.assertEqual(self.store.get(self.id)["messages"][m["id"]]["deliveries"]["b"]["status"], "pending")
        self.store.human_control(self.id, "execution_mode", "desktop")
        self.assertEqual(pending(self.store.get(self.id)), {})

    def test_two_messages_use_one_original_chat_delivery_and_real_ack(self):
        class Bridge:
            def __init__(self):self.sent=[]
            def send(self,member,body):
                self.sent.append((member,body));return {"success":True}
        bridge=Bridge()
        runner=Runner(self.store,bridge,idle_seconds=0)
        messages=[self.message("one"),self.message("two")]
        ids=[m["id"] for m in messages]
        runner.start(self.store.get(self.id),"b",ids)
        self.assertEqual(len(bridge.sent),1)
        self.assertEqual(bridge.sent[0][0]["thread_id"],"b")
        self.assertEqual(json.loads(bridge.sent[0][1].splitlines()[1])["message_ids"],ids)
        for m in ids:
            self.assertEqual(self.store.get(self.id)["messages"][m]["deliveries"]["b"]["status"],"sent")
            self.store.execute(self.id,"b","message_ack",{"message_id":m})
        runner.jobs["b"]["issued_clock"]-=4
        with patch("relic_org.quiet.completion_setting",return_value={"disabled":True}),patch.object(runner,"native_states",return_value={"b":"idle"}):runner.tick()
        self.assertEqual(runner.jobs,{})
        self.assertTrue(all(self.store.get(self.id)["messages"][m]["deliveries"]["b"]["status"]=="acknowledged" for m in ids))

    def test_native_states_excludes_caller_and_fills_partial_snapshots(self):
        class Bridge:
            def __init__(self):self.calls=[]
            def call(self,name,args):
                self.calls.append((name,args))
                if name=='read_thread':
                    self_id=args['threadId']
                    return {'thread':{'id':self_id,'status':{'type':'idle'}}}
                ids=[t['threadId'] for t in args['targets']]
                if 'a' in ids:raise AssertionError('cannot wait on caller')
                # Match the real desktop: one completed target can win.
                return {'polls':[{'thread':{'id':ids[0],'status':{'type':'idle' if ids[0]=='b' else 'active'}}}]}
        bridge=Bridge()
        runner=Runner(self.store,bridge)
        bridge.actor='a'
        self.assertEqual(runner.native_states(['a','b','c']),{'a':'idle','b':'idle','c':'active'})
        self.assertEqual([name for name,_ in bridge.calls],['read_thread','wait_threads','wait_threads'])

    def failure_runner(self):
        class Bridge:
            def send(self, *_):return {'success':True}
        runner = Runner(self.store, Bridge(), idle_seconds=0)
        msg = self.message()
        runner.start(self.store.get(self.id), 'b', [msg['id']])
        started = int(time.time())
        runner.native_polls['b'] = {'thread':{'status':{'type':'systemError'}},
            'latestTurn':{'id':'failed-turn','status':'failed','startedAt':started,
                          'completedAt':started+1,'error':{'message':'This content was flagged for possible cybersecurity risk.'}}}
        return runner, msg

    def test_terminal_failure_settles_batch_without_ack_or_replay(self):
        runner, msg = self.failure_runner()
        pending_msg = self.message('later')
        with patch('relic_org.quiet.completion_setting', return_value={'disabled':True}), patch.object(runner, 'native_states', return_value={'b':'systemError'}), patch.object(runner, 'start') as send:
            runner.tick()
            runner.tick()
            send.assert_not_called()
        self.assertEqual(runner.jobs, {})
        self.assertEqual(self.store.get(self.id)['messages'][msg['id']]['deliveries']['b']['status'], 'uncertain')
        self.assertEqual(self.store.get(self.id)['messages'][pending_msg['id']]['deliveries']['b']['status'], 'pending')
        record = status(self.store)
        self.assertEqual(record['state'], 'attention_required')
        self.assertEqual(record['queued'], 1)
        self.assertEqual(record['attention_required'][0]['category'], 'safety_block')
        self.assertEqual(record['recent_completions'][0]['state'], 'failed')

    def test_acknowledged_message_stays_acknowledged_when_turn_fails(self):
        runner, msg = self.failure_runner()
        self.store.execute(self.id, 'b', 'message_ack', {'message_id':msg['id']})
        with patch('relic_org.quiet.completion_setting', return_value={'disabled':True}), patch.object(runner, 'native_states', return_value={'b':'systemError'}):runner.tick()
        self.assertEqual(self.store.get(self.id)['messages'][msg['id']]['deliveries']['b']['status'], 'acknowledged')
        self.assertEqual(status(self.store)['recent_completions'][0]['state'], 'failed')

    def test_active_and_stale_error_do_not_end_current_job(self):
        runner, msg = self.failure_runner()
        with patch('relic_org.quiet.completion_setting', return_value={'disabled':True}), patch.object(runner, 'native_states', return_value={'b':'active'}):runner.tick()
        self.assertIn('b',runner.jobs)
        runner.native_polls['b']['latestTurn']['startedAt'] = 1
        with patch('relic_org.quiet.completion_setting', return_value={'disabled':True}), patch.object(runner, 'native_states', return_value={'b':'systemError'}):runner.tick()
        self.assertIn('b',runner.jobs)

    def test_restart_restores_accepted_job_without_resending(self):
        runner, msg = self.failure_runner()
        restarted = Runner(self.store, idle_seconds=0)
        restarted.restore_jobs()
        self.assertEqual(restarted.jobs['b']['message_ids'],[msg['id']])
        self.assertEqual(pending(self.store.get(self.id)),{})
        restarted.native_polls = runner.native_polls
        with patch('relic_org.quiet.completion_setting',return_value={'disabled':True}), patch.object(restarted,'native_states',return_value={'b':'systemError'}):restarted.tick()
        third = Runner(self.store, idle_seconds=0)
        third.restore_jobs()
        self.assertEqual(third.jobs,{})
        self.assertEqual(third.attention['b']['turn_id'],'failed-turn')

    def test_confirmed_new_completed_turn_clears_attention_without_replay(self):
        runner, msg = self.failure_runner()
        with patch('relic_org.quiet.completion_setting',return_value={'disabled':True}),patch.object(runner,'native_states',return_value={'b':'systemError'}):runner.tick()
        runner.native_polls['b']={'thread':{'status':{'type':'idle'}},'latestTurn':{'id':'recovered-turn','status':'completed'}}
        with patch('relic_org.quiet.completion_setting',return_value={'disabled':True}),patch.object(runner,'native_states',return_value={'b':'idle'}),patch.object(runner,'start') as send:
            runner.tick()
            send.assert_not_called()
        self.assertEqual(runner.attention,{})
        self.assertEqual(self.store.get(self.id)['messages'][msg['id']]['deliveries']['b']['status'],'uncertain')

    def test_removed_org_receipt_cannot_crash_worker_restart(self):
        runner, msg = self.failure_runner()
        old = dict(runner.jobs['b'],id='old-job',org_id='removed-org')
        (runner.root/'old-job.receipt.json').write_text(json.dumps(old),encoding='utf-8')
        restarted=Runner(self.store,idle_seconds=0)
        restarted.restore_jobs()
        self.assertEqual(list(restarted.jobs),['b'])
        self.assertEqual(restarted.jobs['b']['org_id'],self.id)


if __name__ == "__main__":
    unittest.main()
