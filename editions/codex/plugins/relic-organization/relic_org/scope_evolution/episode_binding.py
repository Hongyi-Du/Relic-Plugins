"""Launcher-owned actual-child binding to approved prompt assets.

EpisodeBinding(store, org_id, launcher_actor) exposes enroll_created_thread,
prepare_turn and dispatch_turn. Approvals remain ordinary real member calls.
"""
from pathlib import Path

from ..store import OrgError, now, uid
from .codex_episode import CodexExecutor, _VERIFIED, copy_json, fingerprint, write_json
from .runtime import selected_assets, state, same


def _tables(org):
    value = state(org)
    for name in ('episode_bindings', 'prepared_turns', 'turn_attempts'):
        value.setdefault(name, {})
    return value


class EpisodeBinding:
    def __init__(self, store, org_id, launcher_actor):
        self.store, self.org_id, self.actor = store, org_id, launcher_actor

    def _authorize(self, org):
        if self.actor not in org['members'] or self.actor not in org.get('scope_episode_launchers', [org['leader']]):
            raise OrgError('Only the experiment setup authorized launcher may bind an episode.')
        if org['status'] != 'active':
            raise OrgError('Organization is paused.')

    def _binding(self, org, binding_id):
        self._authorize(org)
        binding = _tables(org)['episode_bindings'].get(binding_id)
        if not binding or binding['launcher_actor'] != self.actor:
            raise OrgError('Unknown binding for this actual launcher.')
        actual = org['members'].get(binding['executor_thread_id'])
        if not actual or any(not same(actual.get(k), v) for k, v in binding['member'].items()):
            raise OrgError('Actual child roster facts changed; fresh enrollment and adoption are required.')
        return binding

    def enroll_created_thread(self, executor, spec, request_id):
        if not isinstance(executor, CodexExecutor) or executor._verified is not _VERIFIED:
            raise OrgError('Enroll only the owned executor returned by create_executor, never raw thread JSON.')
        if executor._used:
            raise OrgError('Enrollment must precede the actual child model turn.')
        if not isinstance(request_id, str) or not request_id:
            raise OrgError('Stable enrollment request_id is required.')
        required = {'task_id', 'task_family', 'environment_version', 'phase', 'replicate'}
        if not isinstance(spec, dict) or required - set(spec) or set(spec) - required - {'role', 'batch_id', 'team_ids'}:
            raise OrgError('Episode spec requires exact task/family/environment/phase/replicate provenance.')
        if any(not isinstance(spec[k], str) or not spec[k] for k in required - {'replicate'}):
            raise OrgError('Episode provenance fields must be nonempty strings.')
        if type(spec['replicate']) is not int or spec['replicate'] < 0:
            raise OrgError('replicate must be explicit and nonnegative; sampling seed stays unseeded.')
        facts = executor.facts
        context = {'task_id': spec['task_id'], 'task_family': spec['task_family'],
            'environment_version': spec['environment_version'], 'workflow': spec['phase'],
            'role': spec.get('role', 'implementer'), 'model': facts['effective_model'],
            'carrier_id': executor.thread_id, 'runtime_version': 'codex-episode-v1:' + fingerprint(facts),
            'capabilities': ['prompt_conditioning']}
        if 'batch_id' in spec:
            context['batch_id'] = spec['batch_id']
        if 'team_ids' in spec:
            context['team_ids'] = spec['team_ids']
        from .resolver import trusted_context
        probe = {'id': self.org_id, 'members': {executor.thread_id: {'scope_context': context}}}
        trusted_context(probe, executor.thread_id)
        request = {'facts': facts, 'spec': copy_json(spec), 'request_id': request_id}
        detail = {'request_id': request_id, 'executor_thread_id': executor.thread_id}
        with self.store.transaction(self.org_id, self.actor, 'scope.episode_enroll', detail) as (org, db):
            self._authorize(org)
            value = _tables(org)
            for existing in value['episode_bindings'].values():
                if existing['request']['request_id'] == request_id or existing['executor_thread_id'] == executor.thread_id:
                    if existing['launcher_actor'] != self.actor or not same(existing['request'], request):
                        raise OrgError('Enrollment request/thread is already bound to different immutable facts.')
                    self._binding(org, existing['binding_id'])
                    return copy_json(existing)
            if any(p.get('approvals') or p.get('status') == 'deployed' for p in value['proposals'].values()):
                raise OrgError('Enroll every phase child before any exact deployment approval.')
            if executor.thread_id == self.actor or executor.thread_id in org['members']:
                raise OrgError('Fresh child identity must differ from launcher and every existing member.')
            if len(org['members']) >= 20:
                raise OrgError('Natural pilot roster limit is 20; create a separate phase organization.')
            member = {'thread_id': executor.thread_id, 'workspace': facts['workspace'],
                'scope_context': context, 'episode_executor': facts,
                'joined_at': now(), 'active_episode': None}
            org['members'][executor.thread_id] = member
            binding = {'binding_id': uid('episode_binding'), 'launcher_actor': self.actor,
                'executor_thread_id': executor.thread_id, 'request': request,
                'member': copy_json(member), 'output': str(executor.output), 'created_at': now()}
            value['episode_bindings'][binding['binding_id']] = binding
            detail['binding_id'] = binding['binding_id']
        return copy_json(binding)

    def _selection(self, org, binding):
        resolution = selected_assets(org, binding['executor_thread_id'])
        selected = []
        for deployment in resolution['selected']:
            if deployment['patch']['kind'] != 'prompt':
                raise OrgError('Natural episodes consume only approved prompt patches.')
            selected.append({k: copy_json(deployment[k]) for k in
                             ('deployment_id', 'patch_ref', 'scope_ref', 'adapter', 'patch')})
        return {'selected': selected, 'context': resolution['context'],
                'rejected': resolution['rejected'], 'snapshot_revision': org['revision']}

    def prepare_turn(self, binding_id, base_input, expected_asset_refs, request_id):
        if not isinstance(base_input, str) or not base_input.strip() or not isinstance(request_id, str) or not request_id:
            raise OrgError('Exact nonempty base_input and a stable prepare request_id are required.')
        if not isinstance(expected_asset_refs, list):
            raise OrgError('Expected exact Patch refs are explicit, including [] for controls.')
        request = {'binding_id': binding_id, 'base_input': base_input,
                   'expected_asset_refs': copy_json(expected_asset_refs), 'request_id': request_id}
        detail = {'binding_id': binding_id, 'request_id': request_id}
        with self.store.transaction(self.org_id, self.actor, 'scope.episode_prepare', detail) as (org, db):
            binding = self._binding(org, binding_id)
            value = _tables(org)
            for previous in value['prepared_turns'].values():
                if previous['request']['request_id'] == request_id:
                    if not same(previous['request'], request):
                        raise OrgError('Prepare idempotency key identifies different exact input.')
                    return copy_json(previous)
            selection = self._selection(org, binding)
            actual = [d['patch_ref'] for d in selection['selected']]
            if sorted(map(fingerprint, actual)) != sorted(map(fingerprint, expected_asset_refs)):
                raise OrgError('Resolver selection differs from the prespecified treatment/control refs.')
            texts = [d['patch']['payload']['text'] for d in selection['selected']]
            exact_text = base_input + ''.join('\n\n' + t for t in texts)
            input_items = [{'type': 'text', 'text': exact_text}]
            receipt = {'prepared_id': uid('episode_prepared'), 'request': request,
                'launcher_actor': self.actor, 'executor_thread_id': binding['executor_thread_id'],
                'selection': selection, 'input': input_items, 'input_sha256': fingerprint(input_items),
                'created_at': now(), 'effect': 'prompt_conditioning_only'}
            output = Path(binding['output'])
            receipt['input_receipt'] = str(output / (receipt['prepared_id'] + '.json'))
            write_json(receipt['input_receipt'], receipt)
            value['prepared_turns'][receipt['prepared_id']] = receipt
            detail['prepared_id'] = receipt['prepared_id']
        return copy_json(receipt)

    def dispatch_turn(self, prepared_id, executor, request_id, budget=None):
        if not isinstance(request_id, str) or not request_id:
            raise OrgError('Stable dispatch request_id is required.')
        if not isinstance(executor, CodexExecutor) or executor._verified is not _VERIFIED:
            raise OrgError('Dispatch requires the owned verified app-server executor.')
        request = {'prepared_id': prepared_id, 'request_id': request_id, 'budget': copy_json(budget)}
        detail = {'prepared_id': prepared_id, 'request_id': request_id}
        with self.store.transaction(self.org_id, self.actor, 'scope.episode_dispatch_intent', detail) as (org, db):
            self._authorize(org)
            value = _tables(org)
            prepared = value['prepared_turns'].get(prepared_id)
            if not prepared or prepared['launcher_actor'] != self.actor:
                raise OrgError('Unknown prepared turn for this actual launcher.')
            for previous in value['turn_attempts'].values():
                if previous['request']['request_id'] == request_id or previous['prepared_id'] == prepared_id:
                    if not same(previous['request'], request):
                        raise OrgError('A prepared episode already has its unique dispatch intent.')
                    return {**copy_json(previous), 'replayed': True}
            binding = self._binding(org, prepared['request']['binding_id'])
            if executor.thread_id != binding['executor_thread_id'] or not same(executor.facts, binding['request']['facts']):
                raise OrgError('Executor identity/host facts differ from the enrolled actual child.')
            current = self._selection(org, binding)
            if not same(current['context'], prepared['selection']['context']) or not same(
                    current['selected'], prepared['selection']['selected']):
                raise OrgError('Prepared selection is stale or withdrawn; no inference was submitted.')
            if fingerprint(prepared['input']) != prepared['input_sha256']:
                raise OrgError('Frozen exact input receipt changed.')
            if any(a['executor_thread_id'] == executor.thread_id for a in value['turn_attempts'].values()):
                raise OrgError('Actual child already has a submitted or uncertain turn; never infer twice.')
            attempt = {'attempt_id': uid('episode_attempt'), 'request': request,
                'prepared_id': prepared_id, 'executor_thread_id': executor.thread_id,
                'launcher_actor': self.actor, 'status': 'submission_unknown', 'created_at': now(),
                'input_sha256': prepared['input_sha256']}
            value['turn_attempts'][attempt['attempt_id']] = attempt
            detail['attempt_id'] = attempt['attempt_id']
        # Durable local intent precedes the non-transactional remote turn submission.
        try:
            result = executor.run(prepared['input'], budget)
        except Exception as error:
            result = {'status': 'submission_unknown', 'error': str(error), 'scoreable': False}
        detail = {'attempt_id': attempt['attempt_id'], 'status': result['status']}
        with self.store.transaction(self.org_id, self.actor, 'scope.episode_terminal', detail) as (org, db):
            stored = _tables(org)['turn_attempts'][attempt['attempt_id']]
            stored.update(status=result['status'], result=result, finished_at=now())
            receipt = copy_json(stored)
        write_json(Path(binding['output']) / 'dispatch.json', receipt)
        return receipt
