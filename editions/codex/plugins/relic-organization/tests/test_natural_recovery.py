"""Crash-boundary fixtures; these actors/transports do not represent live calls."""
import json
import os
import base64
import unittest
from unittest.mock import patch

from relic_org.store import OrgError
from relic_org.scope_evolution.codex_episode import write_json
from relic_org.scope_evolution.natural_driver import read_json
from relic_org.scope_evolution.natural_recovery import reconcile_phase, auth_validity_receipt
from relic_org.scope_evolution.natural_pilot import NaturalPilot
from relic_org.scope_evolution.runtime import state
if __package__:
    from . import test_natural_driver as fixtures
else:
    import test_natural_driver as fixtures


ROSTER = fixtures.ROSTER


class RecoveryTests(unittest.TestCase):
    setUp = fixtures.DriverTests.setUp
    tearDown = fixtures.DriverTests.tearDown
    factory = fixtures.DriverTests.factory
    make_driver = fixtures.DriverTests.make_driver
    jobs = fixtures.DriverTests.jobs
    def prepared_discovery(self, charge=True):
        job = self.jobs('train')[0]
        job['spec'].update(split='discovery', deployment_arm='Static', attempt_id='attempt-01')
        self.driver.prepare_phase('discovery', [job])
        staged = self.driver.stage(**job)
        phase = self.driver.phases['discovery']
        if charge:
            event = {'kind': 'attempt_started', 'attempt_id': 'attempt-01',
                'job_id': job['spec']['job_id'], 'spec': job['spec'], 'reserve': None}
            NaturalPilot(self.root, None)._event(event['kind'], **{k: v for k, v in event.items() if k != 'kind'})
        return job, staged, phase

    def reconcile(self, phase, **arguments):
        return reconcile_phase(phase['path'], roster_reader=lambda: dict(ROSTER),
            is_alive=lambda pid: False,
            container_closer=lambda *a, **k: {'ended': True, 'test_only': True}, **arguments)

    def test_prepared_without_intent_releases_charge_and_requires_a_new_child(self):
        job, staged, phase = self.prepared_discovery()
        original = phase['record']['jobs'][job['spec']['job_id']]['thread_id']
        self.driver.close()
        result = self.reconcile(phase, apply=True, note='TEST no intent means no submission')
        self.assertEqual(result['jobs'][0]['status'], 'not_submitted')
        self.assertEqual(result['jobs'][0]['call_charge'], 0)
        events = [json.loads(line) for line in (self.root / 'attempts.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['status'], 'not_submitted')
        self.assertEqual(NaturalPilot(self.root, None).ledger(), events)
        replacement = self.make_driver()
        replacement.prepare_phase('discovery', [job])
        self.assertNotEqual(replacement.phases['discovery']['record']['jobs'][job['spec']['job_id']]['thread_id'], original)
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))

    def test_actual_terminal_restores_receipt_without_another_turn(self):
        job, staged, phase = self.prepared_discovery()
        actual = self.driver.run(staged)
        self.driver.close()
        count = sum(m.get('method') == 'turn/start' for t in self.transports for m in t.sent)
        result = self.reconcile(phase, apply=True, note='TEST recover terminal after controller loss')
        recovered = read_json(result['jobs'][0]['receipt'])
        self.assertEqual(recovered, actual)
        self.assertEqual(NaturalPilot(self.root, None).ledger()[-1]['kind'], 'attempt_reconciled')
        self.assertEqual(result['jobs'][0]['call_charge'], 1)
        self.assertEqual(sum(m.get('method') == 'turn/start' for t in self.transports for m in t.sent), count)

    def test_missing_rpc_started_cannot_release_an_existing_intent_for_free(self):
        job, staged, phase = self.prepared_discovery()
        with phase['store'].transaction(phase['record']['org_id'], ROSTER['scope-lead'],
                'test_only_intent', {}) as (org, db):
            state(org)['turn_attempts']['test-only-intent'] = {
                'attempt_id': 'test-only-intent', 'executor_thread_id': staged['thread_id'],
                'prepared_id': staged['prepared_id'], 'status': 'submission_unknown'}
        self.driver.close()
        result = self.reconcile(phase, apply=True, note='TEST preserve uncertain charge')
        self.assertEqual(result['jobs'][0]['status'], 'unknown_closed')
        self.assertEqual(result['jobs'][0]['call_charge'], 1)
        self.assertFalse(result['jobs'][0]['retry_released'])
        released = self.reconcile(phase, apply=True, resolve_unknown=True,
            note='TEST explicit ended-container decision for same-slot reserve')
        self.assertTrue(released['jobs'][0]['retry_released'])
        events = [json.loads(line) for line in (self.root / 'attempts.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['status'], 'infrastructure_error')
        self.assertTrue(events[-1]['retryable'])
        self.assertEqual(sum(e['kind'] == 'attempt_started' for e in events), 1)
        self.assertEqual(NaturalPilot(self.root, None).ledger(), events)
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))

    def test_live_controller_and_wrong_actor_are_refused_before_mutation(self):
        job, staged, phase = self.prepared_discovery()
        before = (self.root / 'attempts.jsonl').read_bytes()
        with self.assertRaisesRegex(OrgError, 'alive'):
            reconcile_phase(phase['path'], apply=True, note='TEST',
                roster_reader=lambda: dict(ROSTER), is_alive=lambda pid: True)
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'test-only-other'}), self.assertRaises(OrgError):
            self.reconcile(phase, apply=True, note='TEST')
        self.assertEqual((self.root / 'attempts.jsonl').read_bytes(), before)

    def test_mismatched_terminal_cannot_become_a_completed_receipt(self):
        job, staged, phase = self.prepared_discovery()
        self.driver.run(staged)
        self.driver.close()
        output = self.driver.phases['discovery']['path'].parent / 'executors' / job['spec']['job_id']
        terminal = read_json(output / 'terminal.json')
        terminal['thread_id'] = 'test-only-wrong-child'
        write_json(output / 'terminal.json', terminal)
        with self.assertRaisesRegex(OrgError, 'identity'):
            self.reconcile(phase, apply=True, note='TEST reject foreign result')

    def test_auth_gate_returns_only_metadata_and_refuses_short_or_missing_lifetime(self):
        path = self.root / 'test-only-auth.json'
        claims = base64.urlsafe_b64encode(json.dumps({'exp': 20000, 'private': 'TEST_ONLY_SECRET'}).encode()).decode().rstrip('=')
        write_json(path, {'tokens': {'access_token': 'test-only.' + claims + '.test-only'}})
        receipt = auth_validity_receipt(1000, auth_path=path, clock=lambda: 10000)
        self.assertEqual(receipt['remaining_seconds'], 10000)
        self.assertNotIn('TEST_ONLY_SECRET', json.dumps(receipt))
        with self.assertRaisesRegex(OrgError, 'remaining lifetime'):
            auth_validity_receipt(10001, auth_path=path, clock=lambda: 10000)
        with self.assertRaises(OrgError):
            auth_validity_receipt(1000, auth_path=self.root / 'missing-auth')

    def test_failed_auth_gate_precedes_all_phase_children(self):
        self.driver.auth_reader = lambda required: {'passed': False, 'test_only': True}
        with self.assertRaisesRegex(OrgError, 'lifetime gate'):
            self.prepared_discovery()
        self.assertEqual(self.transports, [])
        self.assertNotIn('discovery', self.driver.phases)

    def test_known_contamination_is_never_released_as_an_uncertain_retry(self):
        job, staged, phase = self.prepared_discovery()
        with phase['store'].transaction(phase['record']['org_id'], ROSTER['scope-lead'],
                'test_only_intent', {}) as (org, db):
            state(org)['turn_attempts']['test-only-intent'] = {
                'attempt_id': 'test-only-intent', 'executor_thread_id': staged['thread_id'],
                'prepared_id': staged['prepared_id'], 'status': 'submission_unknown'}
        self.driver.close()
        output = phase['path'].parent / 'executors' / job['spec']['job_id']
        write_json(output / 'contamination.json', {'invalid': True, 'test_only': True})
        with self.assertRaisesRegex(OrgError, 'Known contamination'):
            self.reconcile(phase, apply=True, resolve_unknown=True, note='TEST forbidden retry')
        self.assertFalse(any(m.get('method') == 'turn/start' for t in self.transports for m in t.sent))
