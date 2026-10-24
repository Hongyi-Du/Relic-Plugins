"""Isolated fixture identities; these are not live member adoption evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from relic_org.store import Store, OrgError, gate
from relic_org.service import Service, TOOLS
from relic_org.benchmark import Benchmarks
from relic_org.scope_evolution.runtime import ScopeRuntime
from relic_org.scope_evolution.models import patch_ref, scope_ref


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scope_hook', ROOT / 'hooks' / 'hook.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class FixtureBridge:
    def close(self):
        pass


class ScopeGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'fixture.db')
        self.org = self.store.create('Explicit isolated fixture identities',
            [{'thread_id': m, 'workspace': 'fixture/' + m} for m in ('fixture-a', 'fixture-b')],
            'fixture-a', execution_mode='desktop')
        self.oid = self.org['id']
        self.rt = ScopeRuntime(self.store)
        self.service = Service(self.store, FixtureBridge(), 'fixture-a')
        self.serial = 0

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def call(self, op, data=None, actor='fixture-a', runtime=None):
        return (runtime or self.rt).call(self.oid, actor, op, {} if data is None else data)

    def patch(self, kind='tool', payload=None, **extra):
        self.serial += 1
        payload = {'operation': 'money.format_cents'} if payload is None else payload
        record = self.call('register_patch', {'spec': {'patch_id': 'p' + str(self.serial), 'kind': kind, 'payload': payload, **extra},
            'expected_revision': 0, 'request_id': 'patch-' + str(self.serial)})
        return patch_ref(record)

    def scope(self, include=None, exclude=None):
        self.serial += 1
        record = self.call('register_scope', {'spec': {'scope_id': 's' + str(self.serial),
            'include': {'const': True} if include is None else include,
            'exclude': {'const': False} if exclude is None else exclude},
            'expected_revision': 0, 'request_id': 'scope-' + str(self.serial)})
        return scope_ref(record)

    def proposal(self, bindings):
        revision = self.call('snapshot').get('deployment_revision', 0)
        return self.call('propose', {'bindings': bindings, 'expected_revision': revision, 'evidence': ['fixture/independent-validation']})

    def adopt(self, pref, sref=None):
        proposal = self.proposal([{'patch_ref': pref, 'scope_ref': sref or self.scope()}])
        for actor in ('fixture-a', 'fixture-b'):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'Reviewed exact fixture binding.'}, actor)
        return self.call('deploy', {'proposal_id': proposal['proposal_id']})['deployments'][0]

    def execute(self, pref, value=9007199254740993, token=None, actor='fixture-a'):
        self.serial += 1
        return self.call('execute', {'patch_ref': pref, 'input': value, 'idempotency_key': token or str(self.serial)}, actor)

    def test_individual_identity_quorum_and_service_membership(self):
        pref = self.patch()
        proposal = self.proposal([{'patch_ref': pref, 'scope_ref': self.scope()}])
        for actor in ('not-a-member', 'human'):
            with self.assertRaises(OrgError):
                self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'spoof'}, actor)
        with self.assertRaises(OrgError):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'spoof', 'actor': 'fixture-b'})
        self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'actual leader'})
        with self.assertRaises(OrgError):
            self.call('deploy', {'proposal_id': proposal['proposal_id']})
        self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'actual peer'}, 'fixture-b')
        with self.assertRaises(OrgError):
            self.call('deploy', {'proposal_id': proposal['proposal_id']}, 'fixture-b')
        self.assertTrue(self.call('deploy', {'proposal_id': proposal['proposal_id']})['deployments'])
        with self.assertRaises(OrgError):
            self.service.call('org_scope_evolution', {'org_id': self.oid, 'operation': 'snapshot', 'data': {}}, actor='unknown')

    def test_scope_revision_requires_new_approvals_and_payload_is_frozen(self):
        pref, sref = self.patch(), self.scope()
        proposal = self.proposal([{'patch_ref': pref, 'scope_ref': sref}])
        self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'old exact scope'})
        new_scope = self.call('register_scope', {'spec': {'scope_id': sref['scope_id'], 'include': {'const': False}, 'exclude': {'const': False}},
            'expected_revision': 1, 'request_id': 'scope-change'})
        new_proposal = self.proposal([{'patch_ref': pref, 'scope_ref': scope_ref(new_scope)}])
        self.assertEqual(new_proposal['approvals'], {})
        with self.assertRaises(OrgError):
            self.call('deploy', {'proposal_id': proposal['proposal_id'], 'bindings': new_proposal['bindings']})
        copy = self.call('get_patch', {'patch_ref': pref})
        copy['payload']['operation'] = 'arbitrary.python'
        self.assertEqual(self.call('get_patch', {'patch_ref': pref})['payload']['operation'], 'money.format_cents')

    def test_adapter_revision_and_deployment_revision_invalidate_approval(self):
        custom = ScopeRuntime(self.store, operations={'fixture.identity': {'revision': '1', 'execute': lambda v, p: v}})
        pref = self.patch(payload={'operation': 'fixture.identity'})
        bindings = [{'patch_ref': pref, 'scope_ref': self.scope()}]
        proposal = self.call('propose', {'bindings': bindings, 'expected_revision': 0, 'evidence': ['fixture/custom']}, runtime=custom)
        upgraded = ScopeRuntime(self.store, operations={'fixture.identity': {'revision': '2', 'execute': lambda v, p: v}})
        with self.assertRaises(OrgError):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'stale adapter'}, runtime=upgraded)
        self.adopt(self.patch())
        with self.assertRaises(OrgError):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'stale deployment'}, runtime=custom)

    def test_atomic_dependencies_and_one_sided_conflicts(self):
        parent = self.patch()
        child = self.patch(dependencies=[parent])
        sref = self.scope()
        with self.assertRaises(OrgError):
            self.proposal([{'patch_ref': child, 'scope_ref': sref}])
        self.assertEqual(self.call('snapshot')['deployments'], {})
        proposal = self.proposal([{'patch_ref': child, 'scope_ref': sref}, {'patch_ref': parent, 'scope_ref': sref}])
        for actor in ('fixture-a', 'fixture-b'):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'review both'}, actor)
        result = self.call('deploy', {'proposal_id': proposal['proposal_id']})
        self.assertEqual(len(result['deployments']), 2)
        other = self.patch(conflicts=[parent])
        with self.assertRaises(OrgError):
            self.proposal([{'patch_ref': other, 'scope_ref': sref}])
        self.assertEqual(len(self.call('snapshot')['deployments']), 2)
        parent_deployment = next(d for d in result['deployments'] if d['patch_ref'] == parent)
        withdrawn = self.call('withdraw', {'deployment_id': parent_deployment['deployment_id'], 'reason': 'fixture negative evidence'})
        self.assertEqual(len(withdrawn['withdrawn']), 2)
        self.assertFalse(self.execute(child)['allowed'])

    def test_out_of_scope_dependency_cannot_activate_child(self):
        parent = self.patch()
        child = self.patch(dependencies=[parent])
        proposal = self.proposal([{'patch_ref': parent, 'scope_ref': self.scope({'field': 'member_id', 'op': 'eq', 'value': 'fixture-b'})},
            {'patch_ref': child, 'scope_ref': self.scope()}])
        for actor in ('fixture-a', 'fixture-b'):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'review scopes'}, actor)
        self.call('deploy', {'proposal_id': proposal['proposal_id']})
        self.assertFalse(self.execute(child)['allowed'])
        self.assertTrue(self.execute(child, actor='fixture-b')['allowed'])

    def test_actual_store_action_denied_and_out_of_scope_control_writes(self):
        pref = self.patch('protocol', {'rules': [{'tools': ['org_document_write'], 'effect': 'deny', 'argument_equals': {'key': 'release'}}]})
        self.adopt(pref, self.scope({'field': 'member_id', 'op': 'eq', 'value': 'fixture-a'}))
        request = {'key': 'release', 'body': 'fixture actual output', 'expected_revision': 0}
        with self.assertRaises(OrgError):
            self.store.execute(self.oid, 'fixture-a', 'document_write', request)
        self.assertNotIn('release', self.store.get(self.oid)['documents'])
        self.store.execute(self.oid, 'fixture-b', 'document_write', request)
        self.assertIn('release', self.store.get(self.oid)['documents'])
        self.assertTrue(any(e['kind'] == 'scope.enforced' and not e['body']['allowed'] for e in self.store.events(self.oid, limit=200)))
        self.assertTrue(self.call('snapshot')['deployments'])

    def test_hook_and_benchmark_paths_enforce_without_grader_edits(self):
        pref = self.patch('protocol', {'rules': [{'tools': ['Bash', 'org_benchmark_submit', 'bench_mutate'], 'effect': 'deny'}]})
        self.adopt(pref)
        result = hook.handle({'hook_event_name': 'PreToolUse', 'session_id': 'fixture-a', 'tool_name': 'exec_command', 'tool_input': {'cmd': 'fixture mutation'}}, self.store)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        bench = Benchmarks(self.store)
        run = bench.start(self.oid, {'api.py': 'fixture-a', 'ledger.py': 'fixture-b', 'policy.py': 'fixture-a'})
        with self.assertRaises(OrgError):
            bench.call(self.oid, 'fixture-a', 'submit', {'run_id': run['id'], 'component': 'api.py', 'content': 'x=1', 'expected_revision': 0})
        with self.store.transaction(self.oid, 'fixture-a', 'fixture.binding', {}) as (org, db):
            org['organizationbench'] = {'url': 'http://127.0.0.1:1', 'session_id': 'fixture', 'actors': {'fixture-a': ['fixture-actor']}}
        bench.request = lambda *args: self.fail('Denied upstream action must not reach transport.')
        with self.assertRaises(OrgError):
            bench.upstream(self.oid, 'fixture-a', 'invoke', {'tool': 'mutate', 'arguments': {}, 'request_id': 'fixture'})

    def test_unknown_model_cannot_disable_guard_or_be_spoofed(self):
        pref = self.patch('protocol', {'rules': [{'tools': ['org_document_write'], 'effect': 'deny'}]})
        self.adopt(pref, self.scope({'field': 'model', 'op': 'eq', 'value': 'trusted-model'}))
        with self.assertRaises(OrgError):
            self.store.execute(self.oid, 'fixture-a', 'document_write', {'key': 'x', 'body': 'x', 'expected_revision': 0, 'model': 'other'})
        with self.assertRaises(OrgError):
            self.call('context', {'model': 'trusted-model'})
        self.assertIn('unknown', gate(self.store.get(self.oid), 'fixture-a', 'org_document_write', {})['reasons'][0])

    def test_identity_change_requires_explicit_host_revalidation(self):
        pref = self.patch()
        deployment = self.adopt(pref)
        self.assertTrue(self.execute(pref)['allowed'])
        with self.store.transaction(self.oid, 'fixture-a', 'fixture.model_replacement', {}) as (org, db):
            org['members']['fixture-a']['scope_context'] = {'model': 'replacement-model', 'carrier_id': 'replacement-carrier'}
        self.assertFalse(self.execute(pref)['allowed'])
        assessment = self.call('revalidate', {'deployment_id': deployment['deployment_id']})
        self.assertTrue(assessment['adoption_required'])
        self.assertFalse(self.execute(pref)['allowed'])
        proposal = self.call('propose', {'bindings': [{'patch_ref': pref, 'scope_ref': deployment['scope_ref']}],
            'expected_revision': self.call('snapshot')['deployment_revision'], 'evidence': ['fixture/replacement-independent-validation'],
            'revalidate_deployment_id': deployment['deployment_id']})
        for actor in ('fixture-a', 'fixture-b'):
            self.call('approve', {'proposal_id': proposal['proposal_id'], 'note': 'Reviewed replacement context validation.'}, actor)
        self.call('deploy', {'proposal_id': proposal['proposal_id']})
        self.assertTrue(self.execute(pref)['allowed'])

    def test_tool_predicate_uses_same_trusted_invocation_context(self):
        pref = self.patch()
        self.adopt(pref, self.scope({'field': 'tool', 'op': 'eq', 'value': 'scope_tool:money.format_cents'}))
        result = self.execute(pref, 1)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['output'], '0.01')

    def test_changed_dependency_adapter_suppresses_dependent_execution(self):
        self.rt = ScopeRuntime(self.store, operations={'fixture.dependency': {'revision': '1', 'execute': lambda v, p: v}})
        parent = self.patch(payload={'operation': 'fixture.dependency'})
        self.adopt(parent)
        child = self.patch(dependencies=[parent])
        self.adopt(child)
        self.assertTrue(self.execute(child)['allowed'])
        changed = ScopeRuntime(self.store, operations={'fixture.dependency': {'revision': '2', 'execute': lambda v, p: v}})
        self.assertFalse(self.call('execute', {'patch_ref': child, 'input': 1, 'idempotency_key': 'changed-dep'}, runtime=changed)['allowed'])

    def test_vetted_consumers_prompt_memory_money_and_code_rejection(self):
        money = self.patch()
        self.adopt(money)
        self.assertEqual(self.execute(money)['output'], '90071992547409.93')
        self.assertEqual(self.execute(money, -1)['output'], '-0.01')
        for kind in ('prompt', 'memory'):
            pref = self.patch(kind, {'text': 'Fixture scoped ' + kind})
            self.adopt(pref)
            self.assertEqual(self.execute(pref, None)['effect'], 'context_content_supplied')
        output = hook.handle({'hook_event_name': 'UserPromptSubmit', 'session_id': 'fixture-a'}, self.store)
        self.assertIn('Fixture scoped memory', output['hookSpecificOutput']['additionalContext'])
        self.assertTrue(any(e['kind'] == 'observation.scope.context_supplied' for e in self.store.events(self.oid, limit=200)))
        for kind, payload in [('tool', {'operation': 'exec', 'code': 'print(1)'}), ('workflow', {'steps': []})]:
            pref = self.patch(kind, payload)
            with self.assertRaises(OrgError):
                self.proposal([{'patch_ref': pref, 'scope_ref': self.scope()}])

    def test_withdrawal_and_fresh_store_replay(self):
        pref = self.patch()
        deployment = self.adopt(pref)
        first = self.execute(pref, token='same')
        self.assertTrue(self.execute(pref, token='same')['replayed'])
        with self.assertRaises(OrgError):
            self.execute(pref, 3, token='same')
        reopened = ScopeRuntime(Store(self.store.path))
        self.assertEqual(self.call('execute', {'patch_ref': pref, 'input': 9007199254740993, 'idempotency_key': 'fresh'}, runtime=reopened)['output'], first['output'])
        self.call('withdraw', {'deployment_id': deployment['deployment_id'], 'reason': 'Observed negative transfer.'})
        self.assertFalse(self.execute(pref)['allowed'])
        self.assertFalse(self.call('execute', {'patch_ref': pref, 'input': 1, 'idempotency_key': 'fresh-after-withdraw'}, runtime=reopened)['allowed'])
        self.assertEqual(self.call('snapshot')['deployments'][deployment['deployment_id']]['status'], 'withdrawn')

    def test_peer_review_exact_action_and_legacy_gate_remain_independent(self):
        pref = self.patch('protocol', {'rules': [{'tools': ['org_document_write'], 'effect': 'require_peer_review'}]})
        deployment = self.adopt(pref)
        request = {'key': 'reviewed', 'body': 'fixture', 'expected_revision': 0}
        with self.assertRaises(OrgError):
            self.call('review', {'deployment_id': deployment['deployment_id'], 'subject': 'fixture-a', 'tool': 'org_document_write', 'arguments': request, 'evidence': ['fixture']})
        self.call('review', {'deployment_id': deployment['deployment_id'], 'subject': 'fixture-a', 'tool': 'org_document_write', 'arguments': request, 'evidence': ['fixture']}, 'fixture-b')
        self.assertTrue(gate(self.store.get(self.oid), 'fixture-a', 'org_document_write', request)['allowed'])
        self.assertFalse(gate(self.store.get(self.oid), 'fixture-a', 'org_document_write', {**request, 'body': 'changed'})['allowed'])
        with self.store.transaction(self.oid, 'fixture-a', 'fixture.legacy_rule', {}) as (org, db):
            org['protocols']['fixture-legacy'] = {'id': 'fixture-legacy', 'title': 'Legacy authoritative deny', 'status': 'active', 'version': 1,
                'rules': [{'tools': ['org_document_write'], 'effect': 'deny'}]}
        self.assertFalse(gate(self.store.get(self.oid), 'fixture-a', 'org_document_write', request)['allowed'])

    def test_transfer_revalidates_without_importing_approval_authority(self):
        pref = self.patch()
        self.adopt(pref, self.scope({'field': 'member_id', 'op': 'eq', 'value': 'fixture-a'}))
        pack = self.call('export_transfer')
        self.assertNotIn('approvals', json.dumps(pack))
        self.assertTrue(self.call('validate_transfer', {'pack': pack})['compatible'])
        other = self.call('validate_transfer', {'pack': pack}, 'fixture-b')
        self.assertFalse(other['compatible'])
        self.assertTrue(other['adoption_required'])
        self.assertFalse(other['deployed'])
        with self.assertRaises(OrgError):
            self.call('validate_transfer', {'pack': {**pack, 'approvals': {'fixture-b': True}}})

    def test_paused_inspection_and_interface_capability(self):
        self.adopt(self.patch('prompt', {'text': 'Must not be supplied while paused.'}))
        self.store.human_control(self.oid, 'pause')
        self.assertIsInstance(self.call('snapshot'), dict)
        self.assertEqual(self.call('context')['selected'], [])
        with self.assertRaises(OrgError):
            self.patch()
        tool = next(t for t in TOOLS if t['name'] == 'org_scope_evolution')
        self.assertIn('withdraw', tool['inputSchema']['properties']['operation']['enum'])
        result = self.service.call('org_scope_evolution', {'org_id': self.oid, 'operation': 'context', 'data': {}})
        self.assertEqual(result['content'], [])

    def test_service_registry_retry_does_not_commit_revision_or_event(self):
        data = {'spec': {'patch_id': 'retry', 'kind': 'tool', 'payload': {'operation': 'money.format_cents'}},
                'expected_revision': 0, 'request_id': 'service-retry'}
        args = {'org_id': self.oid, 'operation': 'register_patch', 'data': data}
        first = self.service.call('org_scope_evolution', args)
        before = self.store.get(self.oid)
        events = self.store.events(self.oid, limit=200)
        self.assertEqual(self.service.call('org_scope_evolution', args), first)
        self.assertEqual(self.store.get(self.oid), before)
        self.assertEqual(self.store.events(self.oid, limit=200), events)
        data['spec']['payload'] = {'operation': 'text.normalize_whitespace'}
        with self.assertRaises(OrgError):
            self.service.call('org_scope_evolution', args)
