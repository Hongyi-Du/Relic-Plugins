import concurrent.futures
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.native import HostMetadata
from relic_org.quiet import Runner, pending
from relic_org.service import Service
from relic_org.store import OrgError, Store


class NoDesktop:
    def __getattr__(self, name):
        raise AssertionError('Native organization touched desktop: ' + name)

    def close(self):
        pass


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / 'org.sqlite3')
        self.host_path = self.path / 'host.sqlite3'
        with closing(sqlite3.connect(self.host_path)) as db, db:
            db.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,source TEXT,thread_source TEXT,agent_path TEXT,cwd TEXT,title TEXT,archived INTEGER)')
        self.host_row('root')
        self.host_row('a', 'root', '/root/a')
        self.host_row('b', 'root', '/root/b')
        self.host_row('grandchild', 'a', '/root/a/grandchild')
        self.host_row('other-root')
        self.host_row('outsider', 'other-root', '/root/a')
        self.service = self.executor('root')
        self.args = {'operation': 'start', 'request_id': 'native-create', 'data': {
            'runtime': 'native_subagents', 'name': 'Native work', 'task': 'Implement the human task.', 'new_members': 2}}

    def tearDown(self):
        self.temp.cleanup()

    def host_row(self, thread_id, parent=None, path=None, *, archived=0):
        source = json.dumps({'subagent': {'thread_spawn': {'parent_thread_id': parent, 'agent_path': path,
                                                        'depth': path.count('/') - 1}}}) if parent else 'vscode'
        with closing(sqlite3.connect(self.host_path)) as db, db:
            db.execute('INSERT OR REPLACE INTO threads VALUES(?,?,?,?,?,?,?)',
                       (thread_id, source, 'subagent' if parent else 'user', path, 'workspace', thread_id, archived))

    def executor(self, actor):
        return Service(self.store, NoDesktop(), actor, HostMetadata(self.host_path))

    def create(self, **changes):
        result = self.service.call('org_organize', {**self.args, 'data': {**self.args['data'], **changes}})
        self.org_id = result['org_id']
        return result

    def join(self, executor_id, request_id=None, **extra):
        return self.executor(executor_id).call('org_organize', {'operation': 'start', 'request_id': request_id or 'join-' + executor_id,
                                                       'data': {'runtime': 'native_subagents', 'join_org': self.org_id, **extra}})

    def message(self, actor='root', key='m', **extra):
        return self.executor(actor).call('org_message', {'org_id': self.org_id, 'operation': 'send',
                                                       'data': {'body': 'A real peer task.', 'idempotency_key': key, **extra}})

    def test_root_creation_has_no_spawn_invitation_or_seed_protocol(self):
        result = self.create()
        org = self.store.get(self.org_id)
        self.assertEqual(result['created_threads'], [])
        self.assertEqual(list(org['members']), ['root'])
        self.assertEqual(org['native']['root_agent_path'], '/root')
        self.assertEqual(org['native']['capacity'], 3)
        self.assertEqual(org['native']['formation_request_id'], 'native-create')
        self.assertEqual(org['runtime'], 'native_subagents')
        self.assertEqual(org['execution_mode'], 'native')
        self.assertTrue(org['automatic_reflection'])
        self.assertEqual(org['messages'], {})
        self.assertEqual(org['protocols'], {})
        self.assertEqual(org['documents']['human-task-brief']['body'], 'Implement the human task.')
        self.assertEqual(result, self.service.call('org_organize', self.args))
        self.assertEqual(result, self.service.call('org_organize', {'operation': 'status', 'request_id': 'native-create', 'data': {}}))
        self.assertEqual(len(self.store.list()), 1)

    def test_creation_and_receipt_are_atomic_after_interruption(self):
        with patch.object(self.store, '_event', side_effect=RuntimeError('interrupted after insert')):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(OrgError):
            self.service.call('org_organize', {'operation': 'status', 'request_id': 'native-create', 'data': {}})
        result = self.create()
        self.assertEqual(result, self.service.call('org_organize', self.args))

    def test_concurrent_same_request_has_one_organization(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.executor('root').call('org_organize', self.args), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.list()), 1)

    def test_request_is_bound_to_actor_and_arguments(self):
        self.create()
        with self.assertRaises(OrgError):
            self.service.call('org_organize', {**self.args, 'data': {**self.args['data'], 'task': 'Changed'}})
        with self.assertRaises(OrgError):
            self.executor('a').call('org_organize', {'operation': 'status', 'request_id': 'native-create', 'data': {}})

    def test_join_uses_actual_descendant_and_replays_receipt(self):
        self.create()
        joined = self.join('a')
        self.assertEqual(joined['member']['agent_path'], '/root/a')
        self.assertEqual(joined['member']['parent_thread_id'], 'root')
        self.assertEqual(joined, self.join('a'))
        with self.assertRaises(OrgError):
            self.join('a', request_id='duplicate-agent')
        self.join('grandchild')
        self.assertEqual(self.store.get(self.org_id)['members']['grandchild']['agent_path'], '/root/a/grandchild')

    def test_join_receipt_and_membership_roll_back_together(self):
        self.create()
        with patch.object(self.store, '_event', side_effect=RuntimeError('join interrupted')):
            with self.assertRaises(RuntimeError):
                self.join('a')
        self.assertNotIn('a', self.store.get(self.org_id)['members'])
        self.assertTrue(self.join('a')['joined'])

    def test_unrelated_parent_and_spoofed_fields_cannot_enroll(self):
        self.create()
        for actor in ('outsider', 'other-root', 'root', 'missing'):
            with self.subTest(actor=actor), self.assertRaises(OrgError):
                self.join(actor)
        for field in ('actor', 'thread_id', 'agent_path', 'parent_thread_id'):
            with self.subTest(field=field), self.assertRaises(OrgError):
                self.join('a', **{field: 'root'})
        self.assertEqual(list(self.store.get(self.org_id)['members']), ['root'])

    def test_duplicate_canonical_path_and_inconsistent_ancestry_fail(self):
        self.create(new_members=3)
        self.join('a')
        self.host_row('clone', 'root', '/root/a')
        with self.assertRaises(OrgError):
            self.join('clone')
        self.host_row('bad-parent-path', 'a', '/root/wrong/child')
        with self.assertRaises(OrgError):
            self.join('bad-parent-path')
        with closing(sqlite3.connect(self.host_path)) as db, db:
            db.execute('UPDATE threads SET agent_path=? WHERE id=?', ('/root/forged', 'b'))
        with self.assertRaises(OrgError):
            self.join('b')

    def test_capacity_and_active_membership_are_enforced(self):
        self.create(new_members=1)
        self.join('a')
        with self.assertRaises(OrgError):
            self.join('b')

    def test_active_membership_conflict_is_rejected_with_space_available(self):
        self.create(new_members=2)
        busy = self.store.create('Other work', [{'thread_id': 'b'}], 'b')
        with self.assertRaises(OrgError):
            self.join('b')
        self.assertEqual(self.store.get(busy['id'])['members']['b']['thread_id'], 'b')

    def test_invalid_native_creation_options_do_not_mutate_state(self):
        for changes in ({'new_members': True}, {'new_members': -1}, {'new_members': 13}, {'execution_mode': 'desktop'},
                        {'members': ['a']}, {'leader': 'a'}, {'include_current': False}, {'governance': 'invented'}):
            with self.subTest(changes=changes), self.assertRaises(OrgError):
                self.create(**changes)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.create(new_members=0)['capacity'], 1)
        with self.assertRaises(OrgError):
            self.join('a')

    def test_subagent_root_accepts_only_its_descendants(self):
        self.service = self.executor('a')
        result = self.create(new_members=1)
        self.assertEqual(result['root_agent_path'], '/root/a')
        self.assertEqual(self.join('grandchild')['member']['agent_path'], '/root/a/grandchild')
        for actor in ('root', 'b'):
            with self.assertRaises(OrgError):
                self.join(actor)

    def test_host_metadata_is_readonly_and_missing_metadata_fails_closed(self):
        missing = self.path / 'does-not-exist.sqlite3'
        with self.assertRaises(OrgError):
            HostMetadata(missing).read('root')
        self.assertFalse(missing.exists())
        self.host_row('archived', archived=1)
        with self.assertRaises(OrgError):
            self.executor('archived').call('org_organize', self.args)
        with closing(sqlite3.connect(self.host_path)) as db, db:
            db.execute("UPDATE threads SET thread_source='unknown' WHERE id='other-root'")
        with self.assertRaises(OrgError):
            self.executor('other-root').call('org_organize', self.args)

    def test_native_outbox_returns_exact_routes_and_recipient_ack_is_only_receipt(self):
        self.create()
        self.join('a')
        with patch('relic_org.quiet.wake', side_effect=AssertionError('quiet wake')):
            message = self.message(delivery_mode='immediate')
        route = message['native_outbox'][0]
        self.assertEqual(route['target'], '/root/a')
        self.assertEqual(route['send_message']['tool'], 'collaboration.send_message')
        self.assertEqual(route['followup_task']['arguments']['target'], '/root/a')
        self.assertEqual(route['envelope']['to'], 'a')
        self.assertEqual(route['envelope']['body'], 'A real peer task.')
        self.assertEqual(message['deliveries']['a'], {'status': 'pending'})
        self.assertEqual(self.message(delivery_mode='immediate')['id'], message['id'])
        state = self.executor('a').call('org_context', {'org_id': self.org_id})
        self.assertEqual(state['native']['self']['agent_path'], '/root/a')
        self.assertEqual(state['native']['inbox'][0]['message_id'], message['id'])
        with self.assertRaises(OrgError):
            self.service.call('org_message', {'org_id': self.org_id, 'operation': 'ack', 'data': {'message_id': message['id']}})
        with self.assertRaises(OrgError):
            self.store.delivery(self.org_id, message['id'], 'a', 'sent', 'made-up receipt')
        self.executor('a').call('org_message', {'org_id': self.org_id, 'operation': 'ack', 'data': {'message_id': message['id']}})
        state = self.service.call('org_context', {'org_id': self.org_id})
        self.assertEqual(state['native']['outbox'], [])
        self.assertEqual(state['organization']['messages'][message['id']]['deliveries']['a']['status'], 'acknowledged')

    def test_member_to_root_uses_root_canonical_path_without_followup(self):
        self.create()
        self.join('a')
        route = self.message(actor='a')['native_outbox'][0]
        self.assertEqual(route['target'], '/root')
        self.assertNotIn('followup_task', route)

    def test_quiet_worker_never_claims_native_messages_including_immediate(self):
        self.create()
        self.join('a')
        message = self.message(delivery_mode='immediate')
        org = self.store.get(self.org_id)
        self.assertEqual(pending(org), {})
        runner = Runner(self.store, NoDesktop())
        runner.start(org, 'a', [message['id']])
        self.assertEqual(runner.jobs, {})
        self.assertEqual(self.store.get(self.org_id)['messages'][message['id']]['deliveries']['a']['status'], 'pending')
        (runner.root / 'stale.receipt.json').write_text(json.dumps({'state': 'running', 'org_id': self.org_id,
                                                                 'recipient': 'a', 'accepted': True}), encoding='utf-8')
        runner.restore_jobs()
        self.assertEqual(runner.jobs, {})

    def test_pause_retire_and_mode_controls_preserve_native_transport(self):
        self.create()
        self.join('a')
        self.message()
        for mode in ('quiet', 'desktop'):
            with self.assertRaises(OrgError):
                self.store.human_control(self.org_id, 'execution_mode', mode)
        self.store.human_control(self.org_id, 'pause')
        with self.assertRaises(OrgError):
            self.join('b')
        with self.assertRaises(OrgError):
            self.message(key='paused')
        self.assertEqual(self.service.call('org_context', {'org_id': self.org_id})['native']['outbox'], [])
        self.store.human_control(self.org_id, 'resume')
        self.assertTrue(self.service.call('org_context', {'org_id': self.org_id})['native']['outbox'])
        self.store.human_control(self.org_id, 'retire_organization')
        for operation in ('pause', 'resume'):
            with self.assertRaises(OrgError):
                self.store.human_control(self.org_id, operation)
        with self.assertRaises(OrgError):
            self.message(key='retired')
        self.assertEqual(self.service.call('org_context', {'org_id': self.org_id})['native']['outbox'], [])

    def test_episode_reflection_protocol_adoption_and_retirement_still_work(self):
        self.create()
        self.join('a')
        ep = self.store.execute(self.org_id, 'root', 'episode_open', {'title': 'Observed failure', 'participants': ['root', 'a']})
        self.store.execute(self.org_id, 'root', 'episode_close', {'episode_id': ep['id'], 'outcome': 'failure',
                                                               'summary': 'An exact action failed.', 'evidence': ['test failure output']})
        for actor in ('root', 'a'):
            self.store.execute(self.org_id, actor, 'episode_reflect', {'episode_id': ep['id'], 'body': 'Require review of the reproduced failure.'})
        proposal = self.store.execute(self.org_id, 'a', 'protocol_propose', {'episode_id': ep['id'], 'title': 'Review this action',
            'rationale': 'Outcome evidence supports review.', 'rules': [{'tools': ['org_message_send'], 'effect': 'require_peer_review'}]})
        self.store.execute(self.org_id, 'root', 'protocol_comment', {'protocol_id': proposal['id'], 'body': 'Use exact action evidence.'})
        for actor in ('root', 'a'):
            self.store.execute(self.org_id, actor, 'protocol_vote', {'protocol_id': proposal['id'], 'vote': 'approve', 'reason': 'Supported.'})
        self.store.execute(self.org_id, 'root', 'protocol_adopt', {'protocol_id': proposal['id']})
        with self.assertRaises(OrgError):
            self.message()
        args = {'body': 'A real peer task.', 'idempotency_key': 'm'}
        self.store.execute(self.org_id, 'a', 'review_record', {'protocol_id': proposal['id'], 'subject': 'root',
            'tool': 'org_message_send', 'arguments': args, 'evidence': ['Exact peer action reviewed.']})
        self.assertTrue(self.message()['native_outbox'])
        self.store.execute(self.org_id, 'root', 'protocol_retire', {'protocol_id': proposal['id'], 'reason': 'Review no longer needed.'})
        self.assertTrue(self.message(key='after-retirement')['native_outbox'])
        self.assertFalse(self.store.get(self.org_id)['episodes'][ep['id']]['reflection_due'])


if __name__ == '__main__':
    unittest.main()
