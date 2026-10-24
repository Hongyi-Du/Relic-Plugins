"""Actual app-server episodes and member-governed adoption for the natural pilot.

The constructor reads the launcher's own CODEX_THREAD_ID. No driver operation
casts votes. The approval CLI below is run separately by each actual approver.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time

from ..store import Store, OrgError, now
from .codex_episode import create_executor, copy_json, fingerprint, write_json, execution_contract
from .episode_binding import EpisodeBinding
from .models import patch_ref, scope_ref
from .runtime import ScopeRuntime, state, same


COORDINATION_ORG = 'org_cab2a2'
ARMS = ('Static', 'Local', 'Global', 'Adaptive', 'Conservative-LCB', 'Proposer-declared')


def episode_receipt(attempt, job, staged, trace_ref):
    result = attempt.get('result', {})
    status = {'completed': 'completed', 'task_policy_failure': 'completed',
              'task_budget_expired': 'budget_expired', 'submission_unknown': 'uncertain'}.get(
                  attempt['status'], attempt['status'])
    return {'status': status, 'trace_ref': str(trace_ref), 'thread_id': job['thread_id'],
        'turn_id': result.get('turn_id'),
        'output_text': result.get('output_text', ''), 'output': result.get('output_text', ''),
        'token_usage': result.get('token_usage'), 'token_usage_report': result.get('token_usage_report'),
        'tool_actions': result.get('tool_actions'),
        'elapsed_seconds': result.get('elapsed_seconds'), 'cost': 0.0,
        'cost_status': 'subscription_no_per_call_price',
        'execution_status': result.get('execution_status'),
        'postflight_isolation': result.get('postflight_isolation'),
        **{key: copy_json(result.get(key)) for key in
            ('retryable', 'stop_required', 'failure_code', 'failure_kind', 'result_flags', 'contamination')},
        'binding_attempt': copy_json(attempt), 'staged': copy_json(staged)}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def freeze_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not same(read_json(path), value):
            raise OrgError('Frozen driver artifact differs: ' + str(path))
    else:
        write_json(path, value)
    return copy_json(value)


def coordination_roster():
    """Read current seat carriers only, never peer trajectories or memory."""
    path = Path(os.getenv('RELIC_HOME', str(Path.home() / '.relic'))) / 'relic.sqlite3'
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT body FROM orgs WHERE id=?', (COORDINATION_ORG,)).fetchone()
    if row is None:
        raise OrgError('Current coordination organization is missing.')
    org = json.loads(row[0])
    result = {}
    for seat in ('scope-lead', 'scope-governance'):
        member = org['members'][seat]
        carrier = member.get('carrier', '')
        if member.get('harness') != 'codex' or not carrier.startswith('codex:'):
            raise OrgError('Actual persistent Codex carrier required for ' + seat)
        result[seat] = carrier.removeprefix('codex:')
    if len(set(result.values())) != 2:
        raise OrgError('Lead and governance must be distinct actual carriers.')
    return result


class NaturalEpisodeDriver:
    def __init__(self, run, *, wait_for_approval=True, executor_factory=create_executor,
                 roster_reader=coordination_roster, contract_reader=execution_contract,
                 auth_reader=None, poll_seconds=1):
        self.root = Path(run).resolve()
        self.directory = self.root / 'driver'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.actor = os.getenv('CODEX_THREAD_ID')
        self.roster_reader = roster_reader
        self.roster = roster_reader()
        if not self.actor or self.actor != self.roster['scope-lead']:
            raise OrgError('Only the actual scope-lead launcher CODEX_THREAD_ID starts natural episodes.')
        self.peer = self.roster['scope-governance']
        self.wait_for_approval = wait_for_approval
        self.factory = executor_factory
        self.contract_reader = contract_reader
        if auth_reader is None:
            from .natural_recovery import auth_validity_receipt
            auth_reader = auth_validity_receipt
        self.auth_reader = auth_reader
        self.poll_seconds = poll_seconds
        self.phases = {}
        self.jobs = {}
        self.closed = False

    def _execution_contract(self):
        manifest = read_json(self.root / 'manifest.json')['manifest']
        if not same(manifest['execution_contract'], self.contract_reader()):
            raise OrgError('Frozen solver image/CLI/executor/isolation contract changed; no inference submitted.')
        return fingerprint(manifest['execution_contract'])

    def _identity(self):
        if self.closed:
            raise OrgError('Closed driver has no live executor handles; refuse dispatch.')
        if os.getenv('CODEX_THREAD_ID') != self.actor or self.roster_reader() != self.roster:
            raise OrgError('Actual launcher or governance carrier changed; refuse source rebind.')

    def _new_phase(self, phase):
        self._identity()
        parent = self.directory / phase
        parent.mkdir(parents=True, exist_ok=True)
        previous = sorted(parent.glob('batch-*/phase.json'))
        for path in previous:
            old = read_json(path)
            if old.get('jobs') and any(j.get('status') not in ('completed', 'budget_expired', 'infrastructure_error', 'unsubmitted_closed')
                                       for j in old['jobs'].values()):
                raise OrgError('Prior phase has lost live handles or uncertain work; preserve and reconcile: ' + str(path))
        output = parent / ('batch-' + str(len(previous) + 1).zfill(3))
        output.mkdir()
        store = Store(output / 'organization.sqlite3')
        org = store.create('SCOPE natural ' + phase,
            [{'thread_id': self.actor, 'scope_context': {'role': 'launcher'}},
             {'thread_id': self.peer, 'scope_context': {'role': 'governance'}}], self.actor)
        record = {'phase': phase, 'store': str(store.path), 'org_id': org['id'],
            'launcher_actor': self.actor, 'peer_actor': self.peer, 'coordination_roster': self.roster,
            'created_at': now(), 'controller_pid': os.getpid(), 'status': 'preparing', 'jobs': {}, 'scope_refs': {},
            'proposals': {}, 'deployments': {}, 'live_handles': True}
        handle = {'record': record, 'path': output / 'phase.json', 'store': store,
                  'runtime': ScopeRuntime(store), 'binding': EpisodeBinding(store, org['id'], self.actor),
                  'executors': {}}
        self.phases[phase] = handle
        self._persist(handle)
        return handle

    def _persist(self, phase):
        write_json(phase['path'], phase['record'])

    def _call(self, phase, operation, arguments):
        self._identity()
        return phase['runtime'].call(phase['record']['org_id'], self.actor, operation, arguments)

    def _candidate(self, phase):
        asset = read_json(self.directory / 'candidate-asset.json')
        registered = self._call(phase, 'register_patch', {'spec': asset['spec'],
            'expected_revision': 0, 'request_id': 'candidate:' + asset['sha256']})
        if patch_ref(registered) != asset['patch_ref'] or registered['payload'] != asset['spec']['payload']:
            raise OrgError('Phase candidate differs from the exact immutable payload/ref.')
        phase['record']['patch_ref'] = asset['patch_ref']
        self._persist(phase)
        return asset['patch_ref']

    def register_candidate(self, candidate):
        self._identity()
        if candidate.get('status') != 'accepted' or not isinstance(candidate.get('candidate'), dict):
            raise OrgError('Only the producer-validated accepted candidate can be registered.')
        prompt = candidate['candidate']['prompt']
        if not isinstance(prompt, str) or not prompt.strip():
            raise OrgError('Candidate prompt is empty.')
        identity = fingerprint({'prompt': prompt, 'provenance': candidate['provenance_sha256']})
        spec = {'patch_id': 'natural-' + identity[:24], 'kind': 'prompt',
                'payload': {'text': prompt}, 'payload_ref': str(self.root / 'candidate.json'),
                'evidence_refs': list(candidate['candidate']['source_refs'])}
        asset = {'spec': spec, 'sha256': identity, 'patch_ref': {'patch_id': spec['patch_id'], 'revision': 1}}
        freeze_json(self.directory / 'candidate-asset.json', asset)
        phase = self.phases.get('generation') or self._new_phase('candidate')
        return {'patch_ref': self._candidate(phase), 'payload_sha256': fingerprint(spec['payload']),
                'asset_receipt': str(self.directory / 'candidate-asset.json')}

    def _register_scope(self, phase, arm, include):
        specification = {'scope_id': 'natural-' + arm, 'include': include, 'exclude': {'const': False},
                         'evidence_refs': [str(self.root / ('policies.json' if phase['record']['phase'] in
                                                          ('policies', 'evaluation') else 'candidate.json'))]}
        record = self._call(phase, 'register_scope', {'spec': specification, 'expected_revision': 0,
                                                     'request_id': 'scope:' + arm})
        reference = scope_ref(record)
        phase['record']['scope_refs'][arm] = reference
        return reference

    def _policy_scopes(self, phase, frozen):
        decisions = frozen['decisions']
        if fingerprint(decisions) != frozen['sha256'] or set(decisions['arms']) != set(ARMS):
            raise OrgError('All six exact policy decisions must be frozen before evaluation.')
        self._candidate(phase)
        for arm in ARMS:
            choices = decisions['arms'][arm]
            if not choices or any(type(v) is not bool for v in choices.values()):
                raise OrgError('Frozen policy choices must be explicit family booleans.')
            enabled = sorted(f for f, on in choices.items() if on)
            include = {'all': [{'field': 'workflow', 'op': 'eq', 'value': 'evaluation'},
                               {'field': 'batch_id', 'op': 'eq', 'value': arm},
                               {'field': 'task_family', 'op': 'in', 'value': enabled}]} if enabled else {'const': False}
            self._register_scope(phase, arm, include)
        phase['record']['policy_sha256'] = frozen['sha256']
        self._persist(phase)

    def stage_policies(self, frozen_record):
        self._identity()
        freeze_json(self.directory / 'frozen-policies.json', frozen_record)
        if 'policies' not in self.phases:
            previous = sorted((self.directory / 'policies').glob('batch-*/phase.json'))
            if previous:
                record = read_json(previous[-1])
                if record.get('policy_sha256') != frozen_record['sha256']:
                    raise OrgError('Previously registered policy choices differ.')
                return {'status': 'frozen', **record}
            phase = self._new_phase('policies')
            self._policy_scopes(phase, frozen_record)
            phase['record']['status'] = 'frozen'
            self._persist(phase)
        return {'status': 'frozen', **self.phases['policies']['record']}

    def prepare_phase(self, phase, jobspecs):
        """Create and enroll the entire supplied batch before any proposal/approval."""
        self._identity()
        self._execution_contract()
        if phase not in ('discovery', 'generation', 'train', 'evaluation') or not jobspecs or len(jobspecs) > 18:
            raise OrgError('Natural phase needs 1–18 actual job specifications.')
        if phase in self.phases:
            handle = self.phases[phase]
            if set(handle['record']['jobs']) != {j['spec']['job_id'] for j in jobspecs}:
                raise OrgError('Prepared phase batch differs; never enroll after approval.')
            return copy_json(handle['record'])
        if len({j['spec']['job_id'] for j in jobspecs}) != len(jobspecs):
            raise OrgError('Duplicate phase job identity.')
        required_seconds = sum(j['spec'].get('limits', {}).get('wall_seconds', 1800) for j in jobspecs) + 600
        auth_lifetime = self.auth_reader(required_seconds)
        if auth_lifetime.get('passed') is not True:
            raise OrgError('Actual login lifetime gate failed before phase children were created.')
        handle = self._new_phase(phase)
        handle['record']['auth_lifetime'] = auth_lifetime
        try:
            for job in jobspecs:
                self._enroll(handle, job)
            if phase == 'train':
                self._candidate(handle)
                children = [j['thread_id'] for j in handle['record']['jobs'].values() if j['spec']['patch']]
                include = {'all': [{'field': 'workflow', 'op': 'eq', 'value': 'validation'},
                    {'field': 'member_id', 'op': 'in', 'value': children}]} if children else {'const': False}
                self._register_scope(handle, 'Validation', include)
            elif phase == 'evaluation':
                self._policy_scopes(handle, read_json(self.root / 'policies.json'))
            handle['record']['status'] = 'prepared'
            self._persist(handle)
            return copy_json(handle['record'])
        except BaseException:
            handle['record']['status'] = 'preparation_failed'
            self._persist(handle)
            raise

    def _enroll(self, phase, job):
        spec = copy_json(job['spec'])
        contract_sha256 = self._execution_contract()
        if spec.get('execution_contract_sha256') != contract_sha256:
            raise OrgError('Job execution-contract digest differs from frozen P0.')
        job_id = spec['job_id']
        if spec.get('sampling_seed') is not None or spec.get('model', 'gpt-6.1-sol') != 'gpt-6.1-sol' or spec.get('effort', 'xhigh') != 'xhigh':
            raise OrgError('Frozen model, effort and unseeded sampling are required.')
        output = Path(job['directory']).resolve()
        executor_output = phase['path'].parent / 'executors' / job_id
        executor = self.factory(spec['workspace'], executor_output, model='gpt-6.1-sol', effort='xhigh')
        frozen = read_json(self.root / 'manifest.json')['manifest']['execution_contract']
        if executor.facts.get('host_identity') and any(
                executor.facts['host_identity'].get(k) != frozen.get(k) for k in
                ('transport', 'image_id', 'cli_version', 'dockerfile_sha256')):
            executor.close()
            raise OrgError('Actual created executor host differs from frozen P0 contract.')
        phase['executors'][job_id] = executor
        binding_spec = {'task_id': spec.get('task_id', 'scb_' + spec['family'] + '_v1'),
            'task_family': spec.get('task_family', spec['family']),
            'environment_version': spec.get('environment_version', spec.get('checkpoint', spec['split'])),
            'phase': 'validation' if spec['split'] == 'train' else spec['split'],
            'replicate': spec['replicate'], 'role': 'generator' if spec['split'] == 'generation' else 'implementer',
            'batch_id': spec.get('deployment_arm', 'Static')}
        binding = phase['binding'].enroll_created_thread(executor, binding_spec, 'enroll:' + job_id)
        record = {'spec': spec, 'prompt': job['prompt'], 'directory': str(output),
            'expected_asset_refs': copy_json(job['expected_asset_refs']), 'thread_id': executor.thread_id,
            'binding_id': binding['binding_id'], 'status': 'created',
            'executor_output': str(executor_output),
            'container_name': getattr(executor.transport, 'container_name', None)}
        phase['record']['jobs'][job_id] = record
        self.jobs[job_id] = phase
        self._persist(phase)

    def _adopt(self, phase):
        record = phase['record']
        arms = ['Validation'] if record['phase'] == 'train' else ['Adaptive', 'Global', 'Static']
        for arm in arms:
            while True:
                org = phase['store'].get(record['org_id'], self.actor)
                value = state(org)
                proposal_id = record['proposals'].get(arm)
                if not proposal_id:
                    proposal = self._call(phase, 'propose', {'expected_revision': value['deployment_revision'],
                        'bindings': [{'patch_ref': record['patch_ref'], 'scope_ref': record['scope_refs'][arm]}],
                        'evidence': [str(phase['path']), str(self.root / 'manifest.json')],
                        'note': 'Exact natural phase adoption: ' + arm})
                    proposal_id = proposal['proposal_id']
                    record['proposals'][arm] = proposal_id
                    self._persist(phase)
                else:
                    proposal = value['proposals'][proposal_id]
                if proposal['status'] == 'deployed':
                    deployments = [d for d in value['deployments'].values() if d['proposal_id'] == proposal_id]
                    if len(deployments) != 1 or deployments[0]['status'] != 'active':
                        raise OrgError('Operational deployment was withdrawn or differs.')
                    record['deployments'][arm] = copy_json(deployments[0])
                    self._persist(phase)
                    break
                approval = {'status': 'awaiting_approval', 'phase_state': str(phase['path']),
                    'store': record['store'], 'org_id': record['org_id'], 'proposal_id': proposal_id,
                    'arm': arm, 'launcher_actor': self.actor, 'peer_actor': self.peer,
                    'approvals': proposal['approvals'], 'live_handles': True,
                    'inspect': 'python -m relic_org.scope_evolution.natural_driver inspect --state ' + str(self.root / 'approval_required.json'),
                    'approve': 'python -m relic_org.scope_evolution.natural_driver approve --state <approval_required.json> --note <review>',
                    'deploy': 'python -m relic_org.scope_evolution.natural_driver deploy --state <approval_required.json>'}
                write_json(self.root / 'approval_required.json', approval)
                record['status'] = 'awaiting_approval'
                self._persist(phase)
                if not self.wait_for_approval:
                    return False
                time.sleep(self.poll_seconds)
                self._identity()
        record['status'] = 'approved'
        self._persist(phase)
        write_json(self.root / 'approval_required.json', {'status': 'approved', 'phase_state': str(phase['path']),
                                                          'store': record['store'], 'org_id': record['org_id']})
        return True

    def stage(self, spec, prompt, directory, expected_asset_refs):
        self._identity()
        phase_name = spec['split']
        phase = self.jobs.get(spec['job_id'])
        if phase is None:
            if phase_name in ('train', 'evaluation'):
                raise OrgError('prepare_phase must create/enroll ALL phase children before stage.')
            job = {'spec': spec, 'prompt': prompt, 'directory': str(directory),
                   'expected_asset_refs': expected_asset_refs}
            if phase_name not in self.phases:
                self.prepare_phase(phase_name, [job])
            else:
                self._enroll(self.phases[phase_name], job)
            phase = self.jobs[spec['job_id']]
        job = phase['record']['jobs'][spec['job_id']]
        if not same(job['spec'], spec) or job['prompt'] != prompt or job['expected_asset_refs'] != expected_asset_refs or Path(directory).resolve() != Path(job['directory']):
            raise OrgError('Stage differs from the exact precreated phase job.')
        if phase_name in ('train', 'evaluation') and not self._adopt(phase):
            return {'approved': False, 'status': 'awaiting_approval', 'phase_state': str(phase['path'])}
        if phase_name == 'evaluation':
            frozen = read_json(self.root / 'policies.json')
            if fingerprint(frozen['decisions']) != phase['record']['policy_sha256'] or spec['policy_sha256'] != frozen['sha256']:
                raise OrgError('Policy hash changed before actual evaluation input.')
        prepared = phase['binding'].prepare_turn(job['binding_id'], prompt, expected_asset_refs,
                                                'prepare:' + spec['job_id'])
        arm = spec.get('deployment_arm', 'Static')
        deployment = phase['record']['deployments'].get(arm)
        return {'approved': True, 'job_id': spec['job_id'], 'prepared_id': prepared['prepared_id'],
            'thread_id': job['thread_id'], 'phase_state': str(phase['path']),
            'store': phase['record']['store'], 'org_id': phase['record']['org_id'],
            'selection': prepared['selection'], 'input_receipt': prepared['input_receipt'],
            'input_sha256': prepared['input_sha256'], 'operational_arm': arm,
            'operational_deployment': copy_json(deployment)}

    def run(self, staged):
        self._identity()
        self._execution_contract()
        if not staged.get('approved'):
            raise OrgError('No inference while phase approval is pending.')
        phase = self.jobs[staged['job_id']]
        job = phase['record']['jobs'][staged['job_id']]
        executor = phase['executors'][staged['job_id']]
        limits = job['spec'].get('limits', {})
        budget = {'wall_seconds': limits.get('wall_seconds', 1800), 'tool_actions': limits.get('tool_actions', 80)}
        attempt = phase['binding'].dispatch_turn(staged['prepared_id'], executor, 'dispatch:' + staged['job_id'], budget)
        result = attempt.get('result', {})
        receipt = episode_receipt(attempt, job, staged, executor.events_path)
        job['status'] = receipt['status']
        job['attempt_id'] = attempt['attempt_id']
        phase['record']['status'] = 'running' if any(j['status'] == 'created' for j in phase['record']['jobs'].values()) else 'finished'
        self._persist(phase)
        executor.close()
        return receipt

    def withdraw_validation(self):
        self._identity()
        withdrawals = []
        for path in sorted((self.directory / 'train').glob('batch-*/phase.json')):
            record = read_json(path)
            if record['launcher_actor'] != self.actor:
                raise OrgError('Cannot rebind validation deployment source to a different launcher.')
            store = Store(record['store'])
            org = store.get(record['org_id'], self.actor)
            runtime = ScopeRuntime(store)
            for deployment in state(org)['deployments'].values():
                if deployment['status'] == 'active':
                    receipt = runtime.call(record['org_id'], self.actor, 'withdraw', {
                        'deployment_id': deployment['deployment_id'], 'reason': 'Training validation ended before P4 policy freeze.'})
                    withdrawals.append({'store': record['store'], 'org_id': record['org_id'], **receipt})
            if any(d['status'] == 'active' for d in state(store.get(record['org_id'], self.actor))['deployments'].values()):
                raise OrgError('Validation deployment remains active before P4.')
            record.update(status='withdrawn', withdrawn_at=record.get('withdrawn_at', now()))
            write_json(path, record)
            if 'train' in self.phases and self.phases['train']['path'] == path:
                self.phases['train']['record'] = record
        return {'status': 'withdrawn', 'withdrawals': withdrawals}

    def close(self):
        if self.closed:
            return
        for phase in self.phases.values():
            org = phase['store'].get(phase['record']['org_id'], self.actor)
            value = state(org)
            for job in phase['record']['jobs'].values():
                if job['status'] == 'created':
                    prepared = any(p['request']['binding_id'] == job['binding_id']
                                   for p in value.get('prepared_turns', {}).values())
                    dispatched = any(a['executor_thread_id'] == job['thread_id']
                                     for a in value.get('turn_attempts', {}).values())
                    job['status'] = 'uncertain' if dispatched else 'prepared_handle_lost' if prepared else 'unsubmitted_closed'
                    job['reconciliation'] = {'prepared': prepared, 'dispatch_intent': dispatched,
                        'at': now(), 'evidence': str(phase['store'].path)}
            for executor in phase['executors'].values():
                executor.close()
            phase['record']['live_handles'] = False
            self._persist(phase)
            pending_path = self.root / 'approval_required.json'
            if pending_path.exists():
                pending = read_json(pending_path)
                if pending.get('phase_state') == str(phase['path']):
                    write_json(pending_path, {**pending, 'live_handles': False})
        self.closed = True


def approval_action(path, operation, note=None, *, roster_reader=coordination_roster):
    """No actor argument: approvals derive only from this executor's environment."""
    pending = read_json(path)
    record = read_json(pending['phase_state'])
    actor = os.getenv('CODEX_THREAD_ID')
    roster = roster_reader()
    if roster != record['coordination_roster'] or actor not in (record['launcher_actor'], record['peer_actor']):
        raise OrgError('Approval must run in an enrolled actual current leader/governance executor.')
    store = Store(record['store'])
    runtime = ScopeRuntime(store)
    org = store.get(record['org_id'], actor)
    proposal = state(org)['proposals'][pending['proposal_id']]
    if record['proposals'].get(pending['arm']) != proposal['proposal_id'] or proposal['bindings'][0]['scope_ref'] != record['scope_refs'][pending['arm']]:
        raise OrgError('Pending approval differs from the exact staged proposal.')
    if operation == 'inspect':
        return {'phase': record, 'proposal': proposal, 'actual_actor': actor}
    if not record.get('live_handles'):
        raise OrgError('Phase executor handles are closed; inspect/reconcile instead of approving dead children.')
    data = {'proposal_id': proposal['proposal_id']}
    if operation == 'approve':
        data['note'] = note
    elif operation != 'deploy':
        raise OrgError('Use inspect, approve or deploy.')
    return runtime.call(record['org_id'], actor, operation, data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('inspect', 'approve', 'deploy'))
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--note')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(approval_action(args.state, args.operation, args.note), ensure_ascii=False, indent=2))
        return 0
    except (OrgError, OSError, KeyError) as error:
        print(json.dumps({'status': 'stopped', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
