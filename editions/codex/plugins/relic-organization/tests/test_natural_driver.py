"""Isolated Store actors and fake transports; no live approvals or inference."""
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from relic_org.store import OrgError
from relic_org.scope_evolution.codex_episode import create_executor, fingerprint, write_json
from relic_org.scope_evolution.natural_driver import NaturalEpisodeDriver, approval_action, ARMS
from relic_org.scope_evolution.runtime import state, selected_assets
if __package__:
    from .test_codex_episode import FakeTransport
else:
    from test_codex_episode import FakeTransport


ROSTER = {'scope-lead': 'test-only-lead', 'scope-governance': 'test-only-peer'}
FAMILIES = ('meshctl', 'database_migration', 'dynamic_config_service_api')


class DistinctFakeTransport(FakeTransport):
    def __init__(self, workspace, identity, mode='complete'):
        super().__init__(workspace, mode=mode, thread={'id': identity, 'sessionId': identity, 'ephemeral': True})
        self.identity = identity

    def event(self, method, **params):
        self.messages.append({'method': method, 'params': {'threadId': self.identity, 'turnId': 'fake-turn', **params}})


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ('driver-fixture-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.env = patch.dict(os.environ, {'CODEX_THREAD_ID': ROSTER['scope-lead']})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transports = []
        self.drivers = []
        self.candidate = {'status': 'accepted', 'provenance_sha256': 'test-only-provenance',
            'candidate': {'prompt': 'EXACT reusable test instruction.\nRetain this whitespace. ',
                          'source_refs': ['test-only-trace', 'test-only-diagnostics']}}
        write_json(self.root / 'manifest.json', {'manifest': {'execution_contract': {'test_only': True}}})
        self.driver = self.make_driver()
        self.ref = self.driver.register_candidate(self.candidate)['patch_ref']

    def tearDown(self):
        for driver in self.drivers:
            driver.close()

    def factory(self, workspace, output, **kwargs):
        transport = DistinctFakeTransport(workspace, 'test-only-child-' + str(len(self.transports)))
        self.transports.append(transport)
        return create_executor(workspace, output, transport=transport, **kwargs)

    def make_driver(self, **kwargs):
        driver = NaturalEpisodeDriver(self.root, executor_factory=self.factory,
            roster_reader=lambda: dict(ROSTER), contract_reader=lambda: {'test_only': True},
            auth_reader=lambda required: {'test_only': True, 'passed': True, 'required_seconds': required},
            wait_for_approval=False, **kwargs)
        self.drivers.append(driver)
        return driver

    def jobs(self, phase, adaptive=None):
        result = []
        for replicate in (1, 2, 3):
            for family in FAMILIES:
                for present in (False, True):
                    job_id = f'{phase}-{family}-{replicate}-{present}'
                    workspace = self.root / 'products' / job_id
                    workspace.mkdir(parents=True)
                    arm = 'Validation' if phase == 'train' else (
                        'Adaptive' if adaptive[family] == present else 'Global' if present else 'Static')
                    spec = {'job_id': job_id, 'split': phase, 'family': family, 'replicate': replicate,
                        'patch': present, 'workspace': str(workspace), 'checkpoint': 'test-checkpoint',
                        'task_id': 'task-' + family, 'task_family': family, 'environment_version': 'test-env',
                        'deployment_arm': arm, 'model': 'gpt-6.1-sol', 'effort': 'xhigh',
                        'execution_contract_sha256': fingerprint({'test_only': True}),
                        'sampling_seed': None, 'limits': {'wall_seconds': 600, 'tool_actions': 80, 'reported_tokens': 180000}}
                    if phase == 'evaluation':
                        spec['policy_sha256'] = json.loads((self.root / 'policies.json').read_text())['sha256']
                    result.append({'spec': spec, 'prompt': 'SAME PUBLIC TASK INPUT',
                        'directory': str(self.root / 'private' / job_id), 'expected_asset_refs': [self.ref] if present else []})
        return result

    def approve_and_deploy_pending(self):
        path = self.root / 'approval_required.json'
        for actor in ROSTER.values():
            with patch.dict(os.environ, {'CODEX_THREAD_ID': actor}):
                approval_action(path, 'approve', 'TEST ONLY isolated fake executor review', roster_reader=lambda: dict(ROSTER))
        approval_action(path, 'deploy', roster_reader=lambda: dict(ROSTER))

    def stage(self, job):
        return self.driver.stage(**job)

    def test_all_18_precede_approval_and_no_inference_until_actual_approvals(self):
        jobs = self.jobs('train')
        record = self.driver.prepare_phase('train', jobs)
        handle = self.driver.phases['train']
        self.assertEqual(len(handle['store'].get(record['org_id'])['members']), 20)
        self.assertEqual(len(record['jobs']), 18)
        self.assertFalse(self.stage(jobs[0])['approved'])
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))
        pending = json.loads((self.root / 'approval_required.json').read_text())
        proposal = state(handle['store'].get(record['org_id']))['proposals'][pending['proposal_id']]
        self.assertEqual(len(proposal['profiles']), 20)
        self.assertEqual(proposal['approvals'], {})
        with patch.dict(os.environ, {'CODEX_THREAD_ID': ROSTER['scope-lead']}):
            approval_action(self.root / 'approval_required.json', 'approve', 'TEST lead alone', roster_reader=lambda: dict(ROSTER))
            with self.assertRaises(OrgError):
                approval_action(self.root / 'approval_required.json', 'deploy', roster_reader=lambda: dict(ROSTER))
        self.approve_and_deploy_pending()
        control = self.stage(jobs[0])
        treatment = self.stage(jobs[1])
        self.assertEqual(control['selection']['selected'], [])
        self.assertEqual(treatment['selection']['selected'][0]['patch_ref'], self.ref)
        self.assertEqual(control['operational_deployment']['deployment_id'], treatment['operational_deployment']['deployment_id'])
        result = self.driver.run(treatment)
        self.assertEqual(result['status'], 'completed')
        message = next(m for m in self.transports[1].sent if m.get('method') == 'turn/start')
        self.assertEqual(message['params']['input'][0]['text'], jobs[1]['prompt'] + '\n\n' + self.candidate['candidate']['prompt'])
        self.assertEqual(message['params']['effort'], 'xhigh')

    def test_six_policy_scopes_and_actual_adaptive_complement_deployments(self):
        adaptive = {f: f == FAMILIES[0] for f in FAMILIES}
        arms = {arm: {f: (False if arm in ('Static', 'Conservative-LCB') else True if arm == 'Global' else adaptive[f]) for f in FAMILIES} for arm in ARMS}
        frozen = {'decisions': {'arms': arms}, 'sha256': fingerprint({'arms': arms})}
        write_json(self.root / 'policies.json', frozen)
        self.driver.stage_policies(frozen)
        jobs = self.jobs('evaluation', adaptive)
        self.driver.prepare_phase('evaluation', jobs)
        for expected_arm in ('Adaptive', 'Global', 'Static'):
            self.assertFalse(self.stage(jobs[0])['approved'])
            self.assertEqual(json.loads((self.root / 'approval_required.json').read_text())['arm'], expected_arm)
            self.approve_and_deploy_pending()
        selected = {}
        for job in jobs:
            staged = self.stage(job)
            self.assertTrue(staged['approved'])
            actual = [d['patch_ref'] for d in staged['selection']['selected']]
            self.assertEqual(actual, job['expected_asset_refs'])
            self.assertEqual(staged['operational_deployment']['scope_ref'],
                self.driver.phases['evaluation']['record']['scope_refs'][job['spec']['deployment_arm']])
            selected[job['spec']['deployment_arm']] = staged['operational_deployment']['deployment_id']
        self.assertEqual(len(set(selected.values())), 3)
        handle = self.driver.phases['evaluation']
        self.assertEqual(len(state(handle['store'].get(handle['record']['org_id']))['scopes']), 6)
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))

    def test_validation_withdrawal_revokes_prepared_dispatch_before_p4(self):
        jobs = self.jobs('train')
        self.driver.prepare_phase('train', jobs)
        self.stage(jobs[1])
        self.approve_and_deploy_pending()
        staged = self.stage(jobs[1])
        receipt = self.driver.withdraw_validation()
        self.assertEqual(len(receipt['withdrawals']), 1)
        with self.assertRaises(OrgError):
            self.driver.run(staged)
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))
        self.assertEqual(self.driver.withdraw_validation()['withdrawals'], [])

    def test_missing_wholephase_identity_drift_or_rebound_source_refused(self):
        jobs = self.jobs('train')
        with self.assertRaises(OrgError):
            self.stage(jobs[0])
        self.driver.prepare_phase('train', jobs)
        changed = {**jobs[0], 'prompt': 'CHANGED'}
        with self.assertRaises(OrgError):
            self.stage(changed)
        self.stage(jobs[0])
        self.approve_and_deploy_pending()
        self.stage(jobs[0])
        self.driver.close()
        replacement = self.make_driver()
        with self.assertRaises(OrgError):
            replacement.prepare_phase('train', jobs)
        with patch.dict(os.environ, {'CODEX_THREAD_ID': ROSTER['scope-governance']}):
            with self.assertRaises(OrgError):
                self.make_driver()

    def test_provably_never_prepared_children_can_be_recreated_after_closed_phase(self):
        jobs = self.jobs('train')
        self.driver.prepare_phase('train', jobs)
        self.stage(jobs[0])
        self.driver.close()
        old = self.driver.phases['train']['record']
        self.assertTrue(all(j['status'] == 'unsubmitted_closed' for j in old['jobs'].values()))
        replacement = self.make_driver()
        fresh = replacement.prepare_phase('train', jobs)
        self.assertNotEqual(old['org_id'], fresh['org_id'])
        self.assertTrue(set(j['thread_id'] for j in old['jobs'].values()).isdisjoint(
            j['thread_id'] for j in fresh['jobs'].values()))

    def test_actual_approval_identity_and_candidate_immutability(self):
        self.assertEqual(self.driver.register_candidate(self.candidate)['patch_ref'], self.ref)
        altered = {**self.candidate, 'candidate': {**self.candidate['candidate'], 'prompt': 'different'}}
        with self.assertRaises(OrgError):
            self.driver.register_candidate(altered)
        jobs = self.jobs('train')
        self.driver.prepare_phase('train', jobs)
        self.stage(jobs[0])
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'test-only-unenrolled'}):
            with self.assertRaises(OrgError):
                approval_action(self.root / 'approval_required.json', 'approve', 'TEST', roster_reader=lambda: dict(ROSTER))
        with self.assertRaises(OrgError):
            approval_action(self.root / 'approval_required.json', 'approve', 'TEST',
                roster_reader=lambda: {**ROSTER, 'scope-governance': 'test-only-replacement'})

    def test_policy_hash_mutation_and_empty_context_fail_closed(self):
        adaptive = {f: True for f in FAMILIES}
        arms = {a: adaptive for a in ARMS}
        frozen = {'decisions': {'arms': arms}, 'sha256': fingerprint({'arms': arms})}
        write_json(self.root / 'policies.json', frozen)
        jobs = self.jobs('evaluation', adaptive)
        self.driver.prepare_phase('evaluation', jobs)
        handle = self.driver.phases['evaluation']
        org = handle['store'].get(handle['record']['org_id'])
        self.assertEqual(selected_assets(org, ROSTER['scope-governance'])['selected'], [])
        for _ in range(3):
            self.stage(jobs[0]); self.approve_and_deploy_pending()
        write_json(self.root / 'policies.json', {**frozen, 'sha256': 'changed'})
        with self.assertRaises(OrgError):
            self.stage(jobs[0])


if __name__ == '__main__':
    unittest.main()
