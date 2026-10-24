import importlib.util
from pathlib import Path
import tempfile
import unittest

from relic_org.service import Service, TOOLS
from relic_org.store import Store, OrgError, gate
from test_organization import FakeBridge

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('strength_hook', ROOT / 'hooks/hook.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class ProtocolStrengthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'org.db')
        self.service = Service(self.store, FakeBridge(), 'a')
        self.org = self.service.create({'name': 'Strength test', 'members': ['a', 'b'], 'leader': 'a', 'execution_mode': 'desktop'})
        self.oid = self.org['id']
        self.ep = self.runop('a', 'episode_open', {'title': 'Observed coordination', 'participants': ['a', 'b']})

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def runop(self, actor, op, args):
        return self.store.execute(self.oid, actor, op, args)

    def weak(self, **extra):
        return self.runop('a', 'protocol_propose', {
            'episode_id': self.ep['id'], 'title': 'Versioned handoff', 'rationale': 'We confused two artifacts.',
            'strength': 'weak', 'trigger': 'When handing over an artifact', 'scope': 'Shared release work',
            'guidance': 'The builder shares a release identifier; the receiver compares that release.',
            'evidence': ['work/actual-handoff.json'], **extra})

    def agree(self, p):
        for actor in ('a', 'b'):
            result = self.runop(actor, 'protocol_agree', {'protocol_id': p['id'], 'body': 'I will identify the release in my handoffs.'})
        return result

    def close(self):
        self.runop('a', 'episode_close', {'episode_id': self.ep['id'], 'outcome': 'observed', 'summary': 'Handoff observed', 'evidence': ['work/actual-handoff.json']})
        self.runop('a', 'episode_reflect', {'episode_id': self.ep['id'], 'body': 'The release identity resolved our mismatch.'})

    def test_weak_agreement_is_real_quorum_and_never_a_gate(self):
        p = self.weak()
        one = self.runop('b', 'protocol_agree', {'protocol_id': p['id'], 'body': 'I agree as receiver.'})
        self.assertEqual(one['status'], 'proposed')
        p = self.runop('a', 'protocol_agree', {'protocol_id': p['id'], 'body': 'I agree as builder.'})
        self.assertEqual(p['status'], 'active')
        self.assertEqual(p['adoption_mode'], 'member_agreement')
        self.assertEqual(set(p['votes']), {'a', 'b'})
        org = self.store.get(self.oid)
        self.assertEqual(gate(org, 'a', 'Bash', {'command': 'build'})['protocol_ids'], [])
        context = hook.handle({'hook_event_name': 'UserPromptSubmit', 'session_id': 'b'}, self.store)
        self.assertIn('Versioned handoff', context['hookSpecificOutput']['additionalContext'])
        self.assertIn('receiver compares', context['hookSpecificOutput']['additionalContext'])

    def test_use_is_versioned_actor_bound_idempotent_and_not_enforcement(self):
        p = self.agree(self.weak())
        data = {'protocol_id': p['id'], 'version': 1, 'idempotency_key': 'handoff-1', 'work_unit': 'release-1',
                'outcome': 'followed', 'note': 'I consumed this exact release.', 'evidence': ['work/release-1-result.json']}
        one = self.runop('b', 'protocol_record_use', data)
        two = self.runop('b', 'protocol_record_use', data)
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(one['actor'], 'b')
        self.assertEqual(one['evidence_source'], 'member_report')
        for bad in ({'version': 2}, {'evidence': []}, {'outcome': 'planned'}, {'note': 'changed'}):
            with self.assertRaises(OrgError):
                self.runop('b', 'protocol_record_use', {**data, **bad})
        self.runop('a', 'protocol_record_use', {**data, 'idempotency_key': 'deviation-1', 'outcome': 'deviated', 'note': 'I omitted the release label.'})
        activity = self.store.protocol_activity(self.oid, 'a')
        self.assertEqual(activity['protocols'][p['id']]['member_reported_uses'], 2)
        self.assertEqual(activity['protocols'][p['id']]['member_reported_deviated'], 1)
        self.assertEqual(activity['recorded_enforcement_attempts'], 0)
        self.assertEqual(activity['registered_weak_protocols'], 1)
        self.assertEqual(activity['registered_strong_protocols'], 0)
        self.assertEqual(len(Store(self.store.path).get(self.oid)['protocols'][p['id']]['uses']), 2)
        with self.assertRaises(OrgError):
            self.runop('c', 'protocol_record_use', data)

    def test_weak_cannot_smuggle_blocking_rules_or_create_peer_review(self):
        for extra in ({'strength': 'unknown'}, {'guidance': ''}, {'evidence': []}, {'rules': [{'tools': ['*'], 'effect': 'deny'}]}):
            with self.assertRaises(OrgError):
                self.weak(**extra)
        p = self.agree(self.weak())
        with self.assertRaises(OrgError):
            self.runop('b', 'review_record', {'protocol_id': p['id'], 'subject': 'a', 'tool': 'Bash', 'arguments': {}, 'evidence': ['review']})

    def test_revision_keeps_old_guidance_until_members_agree(self):
        p = self.agree(self.weak())
        replacement = self.weak(supersedes=p['id'], guidance='Share the release and changed modules.')
        self.assertEqual(replacement['version'], 2)
        self.assertEqual(self.store.get(self.oid)['protocols'][p['id']]['status'], 'active')
        self.agree(replacement)
        self.assertEqual(self.store.get(self.oid)['protocols'][p['id']]['status'], 'superseded')

    def test_strength_change_requires_strong_governance_and_legacy_stays_strong(self):
        weak = self.agree(self.weak())
        self.close()
        p = self.runop('a', 'protocol_propose', {'episode_id': self.ep['id'], 'title': 'Release gate', 'rationale': 'Repeated issue',
             'supersedes': weak['id'], 'rules': [{'tools': ['Bash'], 'effect': 'require_peer_review'}]})
        self.assertEqual(p['strength'], 'strong')
        with self.assertRaises(OrgError):
            self.runop('b', 'protocol_agree', {'protocol_id': p['id'], 'body': 'Agree'})
        self.runop('b', 'protocol_comment', {'protocol_id': p['id'], 'body': 'Exact review addresses the repeated issue.'})
        for actor in ('a', 'b'):
            self.runop(actor, 'protocol_vote', {'protocol_id': p['id'], 'vote': 'approve', 'reason': 'Useful.'})
        self.runop('a', 'protocol_adopt', {'protocol_id': p['id']})
        org = self.store.get(self.oid)
        self.assertFalse(gate(org, 'a', 'Bash', {'command': 'build'})['allowed'])
        del org['protocols'][p['id']]['strength']
        self.assertFalse(gate(org, 'a', 'Bash', {'command': 'build'})['allowed'])

    def test_closed_work_episode_is_valid_message_provenance(self):
        self.close()
        result = self.runop('b', 'message_send', {'recipients': ['a'], 'body': 'Module ready.', 'idempotency_key': 'ready', 'episode_id': self.ep['id']})
        self.assertEqual(result['episode_id'], self.ep['id'])
        self.assertEqual(self.store.get(self.oid)['episodes'][self.ep['id']]['status'], 'closed')

    def test_closed_meeting_still_rejects_new_contributions(self):
        self.close()
        ep = self.runop('a', 'episode_open', {'title': 'Meeting', 'participants': ['a', 'b'], 'kind': 'meeting'})
        self.runop('a', 'episode_close', {'episode_id': ep['id'], 'outcome': 'observed', 'summary': 'Done', 'evidence': ['message']})
        with self.assertRaises(OrgError):
            self.runop('b', 'message_send', {'recipients': ['a'], 'body': 'Another contribution.', 'idempotency_key': 'late', 'episode_id': ep['id']})

    def test_schema_exposes_actual_new_operations(self):
        tool = next(t for t in TOOLS if t['name'] == 'org_protocol')
        self.assertIn('agree', tool['inputSchema']['properties']['operation']['enum'])
        self.assertIn('record_use', tool['inputSchema']['properties']['operation']['enum'])
        context = self.service.call('org_context', {'org_id': self.oid})
        self.assertEqual(context['protocol_capabilities']['strengths'], ['weak', 'strong'])
