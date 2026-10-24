"""Member-governed, versioned overlays over the existing organization store."""
import json
from datetime import datetime, timedelta, timezone

from ..store import OrgError, now, uid, matches, short_tool
from .adapters import Adapters, detached
from .models import ensure_state, patch_ref, scope_ref
from .registry import get_patch_in, get_scope_in, register_patch_in, register_scope_in
from .resolver import Truth, matches_scope, resolve, trusted_context


class _Replay(Exception):
    def __init__(self, receipt):
        self.receipt = receipt


def state(org):
    value = ensure_state(org)
    for key in ('proposals', 'deployments', 'reviews', 'executions'):
        value.setdefault(key, {})
    value.setdefault('deployment_revision', 0)
    return value


def same(left, right):
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False)


def key(ref):
    return (ref['patch_id'], ref['revision'])


def context_for(org, actor, tool=None):
    attributes = {}
    workspace = org['members'].get(actor, {}).get('workspace')
    if workspace:
        attributes['repository'] = workspace
    if tool:
        attributes['tool'] = tool
    return trusted_context(org, actor, attributes=attributes)


def profile(context):
    return {k: detached(context[k]) for k in ('member_id', 'role', 'team_ids', 'model', 'carrier_id',
            'capabilities', 'runtime_version', 'repository', 'environment_version',
            'task_id', 'task_family', 'workflow', 'batch_id') if k in context}


def validated(deployment, context):
    previous = deployment.get('validated_contexts', {}).get(context.get('member_id'))
    return previous is not None and same(previous, profile(context))


def selected_assets(org, actor, tool=None, adapters=None):
    context = context_for(org, actor, tool)
    if org.get('status') != 'active':
        return {'selected': [], 'rejected': [], 'snapshot_revision': org.get('revision'), 'context': context}
    resolution = resolve(org, context)
    selected = []
    rejected = list(resolution['rejected'])
    available = set()
    adapters = adapters or Adapters()
    for deployment in resolution['selected']:
        try:
            adapter_current = same(adapters.validate(deployment['patch'], org), deployment['adapter'])
        except OrgError:
            adapter_current = False
        if not adapter_current:
            rejected.append({'deployment_id': deployment['deployment_id'], 'patch_ref': deployment['patch_ref'],
                             'reason': 'Adapter operation/revision is unavailable or changed.'})
        elif not validated(deployment, context):
            rejected.append({'deployment_id': deployment['deployment_id'], 'patch_ref': deployment['patch_ref'],
                             'reason': 'Execution identity/capabilities require revalidation.'})
        elif any(key(dep) not in available for dep in deployment['patch'].get('dependencies', [])):
            rejected.append({'deployment_id': deployment['deployment_id'], 'patch_ref': deployment['patch_ref'],
                             'reason': 'A dependency requires revalidation.'})
        else:
            selected.append(deployment)
            available.add(key(deployment['patch_ref']))
    return {**resolution, 'selected': selected, 'rejected': rejected, 'context': context}


def scoped_gate(org, actor, tool, arguments):
    verdict = {'allowed': True, 'reasons': [], 'scope_deployment_ids': [], 'scope_decisions': {}}
    if 'scope_evolution' not in org or org.get('status') != 'active':
        return verdict
    name = short_tool(tool)
    if name.startswith('org_scope_') or name in {'org_context', 'org_review', 'org_protocol'} or name.startswith(('org_protocol_', 'org_review_')):
        return verdict
    context = context_for(org, actor, tool)
    resolution = selected_assets(org, actor, tool)
    selected = {d['deployment_id'] for d in resolution['selected']}
    for deployment in org['scope_evolution'].get('deployments', {}).values():
        if deployment['status'] != 'active':
            continue
        patch = get_patch_in(org, deployment['patch_ref'])
        if patch['kind'] != 'protocol':
            continue
        indexes = [i for i, rule in enumerate(patch['payload']['rules']) if matches(rule, actor, tool, arguments)]
        if not indexes:
            continue
        applicability = matches_scope(get_scope_in(org, deployment['scope_ref']), context)
        if applicability is Truth.FALSE:
            continue
        reasons = []
        did = deployment['deployment_id']
        if applicability is Truth.UNKNOWN:
            reasons.append('Scoped protocol applicability is unknown for this authoritative context.')
        elif did not in selected:
            reasons.append('Scoped protocol dependency, conflict, or identity revalidation prevents admission.')
        else:
            for index in indexes:
                rule = patch['payload']['rules'][index]
                if rule['effect'] == 'deny':
                    reasons.append(rule.get('reason', 'Action blocked by approved scoped protocol.'))
                else:
                    reviewed = any(r['deployment_id'] == did and r['subject'] == actor
                        and r['reviewer'] != actor and r['reviewer'] in org['members']
                        and r['expires_at'] > now() and r['tool'] == tool and same(r['arguments'], arguments)
                        and same(r['profile'], profile(context))
                        for r in org['scope_evolution'].get('reviews', {}).values())
                    if not reviewed:
                        reasons.append('Another member must review this exact action and scoped deployment.')
        verdict['scope_deployment_ids'].append(did)
        verdict['scope_decisions'][did] = {'allowed': not reasons, 'patch_ref': deployment['patch_ref'],
            'scope_ref': deployment['scope_ref'], 'matched_rule_indexes': indexes, 'reasons': reasons}
        verdict['reasons'].extend(reasons)
    verdict['scope_deployment_ids'].sort()
    verdict['allowed'] = not verdict['reasons']
    return verdict


def require_fields(data, required, optional=()):
    if not isinstance(data, dict) or set(required) - set(data) or set(data) - set(required) - set(optional):
        raise OrgError('Invalid SCOPE operation fields; identity and authoritative context are never caller arguments.')


class ScopeRuntime:
    def __init__(self, store, *, operations=None):
        self.store = store
        self.adapters = Adapters(operations)

    def _member(self, org, actor):
        if not actor or actor == 'human' or actor not in org['members']:
            raise OrgError('SCOPE requires the actual authorized member executor identity.')

    def _authority(self, org):
        return {'members': sorted(org['members']), 'leader': org['leader'], 'governance': org['governance']}

    def _bindings(self, org, bindings):
        if not isinstance(bindings, list) or not bindings:
            raise OrgError('A deployment proposal needs a nonempty binding list.')
        result, seen = [], set()
        for binding in bindings:
            require_fields(binding, ('patch_ref', 'scope_ref'))
            patch = get_patch_in(org, binding['patch_ref'])
            scope = get_scope_in(org, binding['scope_ref'])
            if key(patch_ref(patch)) in seen:
                raise OrgError('A proposal cannot bind one exact Patch twice.')
            seen.add(key(patch_ref(patch)))
            result.append({'patch_ref': patch_ref(patch), 'scope_ref': scope_ref(scope),
                'patch': patch, 'scope': scope, 'adapter': self.adapters.validate(patch, org)})
        return sorted(result, key=lambda b: key(b['patch_ref']))

    def _check_graph(self, org, bindings):
        candidates = {key(b['patch_ref']): b['patch'] for b in bindings}
        active = {key(d['patch_ref']): get_patch_in(org, d['patch_ref']) for d in state(org)['deployments'].values() if d['status'] == 'active'}
        all_patches = {**active, **candidates}
        for ref, patch in candidates.items():
            if any(key(dep) not in all_patches for dep in patch.get('dependencies', [])):
                raise OrgError('Atomic deployment requires every exact dependency in the group or active deployment.')
            for other_ref, other in all_patches.items():
                if other_ref == ref:
                    continue
                if (ref[0] == other_ref[0] or other_ref in {key(r) for r in patch.get('conflicts', [])}
                        or ref in {key(r) for r in other.get('conflicts', [])}):
                    raise OrgError('Conflicting Patch revisions cannot be deployed together.')
        visiting, done = set(), set()
        def visit(ref):
            if ref in visiting:
                raise OrgError('Patch dependency cycle.')
            if ref in done:
                return
            visiting.add(ref)
            for dep in all_patches[ref].get('dependencies', []):
                visit(key(dep))
            visiting.remove(ref)
            done.add(ref)
        for ref in candidates:
            visit(ref)
        dependencies = []
        for ref in sorted(done - set(candidates)):
            patch = all_patches[ref]
            adapter = self.adapters.validate(patch, org)
            deployments = [d for d in state(org)['deployments'].values() if d['status'] == 'active' and key(d['patch_ref']) == ref]
            if any(not same(d['adapter'], adapter) for d in deployments):
                raise OrgError('Active dependency adapter changed; fresh governed adoption is required.')
            dependencies.append({'patch': patch, 'adapter': adapter,
                'bindings': sorted([{'deployment_id': d['deployment_id'], 'scope_ref': d['scope_ref']} for d in deployments], key=lambda d: d['deployment_id'])})
        return dependencies

    def call(self, org_id, actor, operation, data):
        org = self.store.get(org_id, actor)
        self._member(org, actor)
        if operation == 'snapshot':
            require_fields(data, ())
            return detached(org.get('scope_evolution', {}))
        if operation in ('get_patch', 'get_scope'):
            field = 'patch_ref' if operation == 'get_patch' else 'scope_ref'
            require_fields(data, (field,))
            return (get_patch_in if operation == 'get_patch' else get_scope_in)(org, data[field])
        if operation == 'context':
            require_fields(data, ())
            result = selected_assets(org, actor, adapters=self.adapters)
            result['content'] = [{'deployment_id': d['deployment_id'], 'kind': d['patch']['kind'],
                                  'text': d['patch']['payload']['text']} for d in result['selected'] if d['patch']['kind'] in ('prompt', 'memory')]
            return detached(result)
        if operation in ('export_transfer', 'validate_transfer'):
            from .transfer import export_transfer, validate_transfer
            if operation == 'export_transfer':
                require_fields(data, ())
                return export_transfer(org, actor, selected_assets(org, actor, adapters=self.adapters)['selected'])
            require_fields(data, ('pack',))
            return validate_transfer(data['pack'], org, context_for(org, actor), self.adapters)
        if org['status'] != 'active':
            raise OrgError('Organization is paused.')
        detail = {'operation': operation}
        try:
            with self.store.transaction(org_id, actor, 'scope.' + operation, detail) as (fresh, db):
                self._member(fresh, actor)
                if fresh['status'] != 'active':
                    raise OrgError('Organization is paused.')
                from ..store import gate
                if operation != 'execute':
                    verdict = gate(fresh, actor, 'org_scope_' + operation, data)
                    if not verdict['allowed']:
                        raise OrgError('; '.join(verdict['reasons']))
                result = self._operate(fresh, actor, operation, data)
                detail['receipt'] = detached(result)
            return detached(result)
        except _Replay as replay:
            return detached(replay.receipt)
        except OrgError as error:
            with self.store.connect() as db:
                self.store._event(db, org, actor, 'scope.rejected', {'operation': operation, 'reason': str(error)})
            raise

    def _operate(self, org, actor, operation, data):
        value = state(org)
        if operation in ('register_patch', 'register_scope'):
            require_fields(data, ('spec', 'expected_revision', 'request_id'))
            registered = (register_patch_in if operation == 'register_patch' else register_scope_in)(
                org, actor, data['spec'], expected_revision=data['expected_revision'], request_id=data['request_id'])
            if registered['replayed']:
                raise _Replay(registered['record'])
            return registered['record']
        if operation == 'propose':
            require_fields(data, ('bindings', 'expected_revision', 'evidence'), ('note', 'revalidate_deployment_id'))
            if type(data['expected_revision']) is not int or data['expected_revision'] != value['deployment_revision']:
                raise OrgError('Deployment revision conflict.')
            if not isinstance(data['evidence'], list) or not data['evidence'] or not all(isinstance(x, str) and x.strip() for x in data['evidence']):
                raise OrgError('Proposal requires actual validation evidence references.')
            bindings = self._bindings(org, data['bindings'])
            revalidating = data.get('revalidate_deployment_id')
            if revalidating:
                deployment = value['deployments'].get(revalidating)
                if (not deployment or deployment['status'] != 'active' or len(bindings) != 1
                        or not same(bindings[0]['patch_ref'], deployment['patch_ref'])
                        or not same(bindings[0]['scope_ref'], deployment['scope_ref'])):
                    raise OrgError('Governed revalidation must bind exactly the existing active deployment.')
            dependencies = self._check_graph(org, bindings)
            proposal = {'proposal_id': uid('scope_proposal'), 'proposer': actor, 'status': 'proposed',
                'bindings': bindings, 'dependencies': dependencies, 'expected_revision': data['expected_revision'],
                'authority': self._authority(org), 'evidence': detached(data['evidence']), 'note': data.get('note', ''),
                'profiles': {member: profile(context_for(org, member)) for member in org['members']},
                'approvals': {}, 'created_at': now(), 'revalidate_deployment_id': revalidating}
            value['proposals'][proposal['proposal_id']] = proposal
            return proposal
        if operation in ('approve', 'deploy'):
            require_fields(data, ('proposal_id', 'note') if operation == 'approve' else ('proposal_id',))
            proposal = value['proposals'].get(data['proposal_id'])
            if not proposal or proposal['status'] != 'proposed':
                raise OrgError('Unknown or no longer proposed deployment.')
            if proposal['expected_revision'] != value['deployment_revision']:
                raise OrgError('Approval is stale: deployment revision changed; propose again.')
            if not same(proposal['authority'], self._authority(org)):
                raise OrgError('Approval is stale: membership, leader or quorum changed.')
            actual = self._bindings(org, [{'patch_ref': b['patch_ref'], 'scope_ref': b['scope_ref']} for b in proposal['bindings']])
            if not same(actual, proposal['bindings']) or not same(self._check_graph(org, actual), proposal['dependencies']):
                raise OrgError('Approval binding changed: Patch, Scope, dependency or adapter differs.')
            if not same(proposal['profiles'], {m: profile(context_for(org, m)) for m in org['members']}):
                raise OrgError('Approval is stale: authoritative execution metadata changed.')
            if operation == 'approve':
                if not isinstance(data['note'], str) or not data['note'].strip():
                    raise OrgError('Each actual approver must state their review.')
                proposal['approvals'][actor] = {'actor': actor, 'note': data['note'], 'at': now()}
                return proposal
            if actor != org['leader']:
                raise OrgError('Only the actual organization leader deploys approved Patches.')
            approvals = set(proposal['approvals']) & set(org['members'])
            needed = min(2, len(org['members'])) if org['governance'] == 'leader_with_peer' else len(org['members']) // 2 + 1
            if org['leader'] not in approvals or len(approvals) < needed:
                raise OrgError('Deployment requires individual leader approval and the configured member quorum.')
            deployments = []
            for binding in proposal['bindings']:
                revalidating = proposal.get('revalidate_deployment_id')
                if revalidating:
                    deployment = value['deployments'].get(revalidating)
                    if not deployment or deployment['status'] != 'active':
                        raise OrgError('Deployment changed before governed revalidation.')
                    deployment.setdefault('adoption_history', [deployment['proposal_id']]).append(proposal['proposal_id'])
                    deployment.update(proposal_id=proposal['proposal_id'], adapter=binding['adapter'],
                        validated_contexts=detached(proposal['profiles']), revalidated_by=actor, revalidated_at=now())
                    deployments.append(deployment)
                    continue
                deployment = {'deployment_id': uid('scope_deploy'), 'proposal_id': proposal['proposal_id'],
                    'patch_ref': binding['patch_ref'], 'scope_ref': binding['scope_ref'], 'adapter': binding['adapter'],
                    'status': 'active', 'deployed_by': actor, 'deployed_at': now(),
                    'validated_contexts': detached(proposal['profiles'])}
                value['deployments'][deployment['deployment_id']] = deployment
                deployments.append(deployment)
            value['deployment_revision'] += 1
            proposal.update(status='deployed', deployed_at=now())
            return {'deployment_revision': value['deployment_revision'], 'deployments': deployments}
        if operation == 'withdraw':
            require_fields(data, ('deployment_id', 'reason'))
            if actor != org['leader']:
                raise OrgError('Only the actual leader withdraws deployments.')
            if not isinstance(data['reason'], str) or not data['reason'].strip():
                raise OrgError('Withdrawal needs a reason.')
            first = value['deployments'].get(data['deployment_id'])
            if not first or first['status'] != 'active':
                raise OrgError('Withdraw an active deployment.')
            withdrawn = []
            def remove(deployment, reason):
                deployment.update(status='withdrawn', withdrawn_by=actor, withdrawn_at=now(), withdrawal_reason=reason)
                withdrawn.append(deployment['deployment_id'])
            remove(first, data['reason'])
            changed = True
            while changed:
                changed = False
                active_refs = {key(d['patch_ref']) for d in value['deployments'].values() if d['status'] == 'active'}
                for deployment in value['deployments'].values():
                    if deployment['status'] == 'active' and any(key(dep) not in active_refs for dep in get_patch_in(org, deployment['patch_ref']).get('dependencies', [])):
                        remove(deployment, 'Required dependency withdrawn.')
                        changed = True
            value['deployment_revision'] += 1
            return {'withdrawn': withdrawn, 'deployment_revision': value['deployment_revision'],
                    'effect': 'Future admission revoked; completed external effects are not undone.'}
        if operation == 'revalidate':
            require_fields(data, ('deployment_id',))
            deployment = value['deployments'].get(data['deployment_id'])
            if not deployment or deployment['status'] != 'active':
                raise OrgError('Revalidate an active deployment.')
            context = context_for(org, actor)
            if matches_scope(get_scope_in(org, deployment['scope_ref']), context) is not Truth.TRUE:
                raise OrgError('Current authoritative context is not in the approved Scope.')
            patch = get_patch_in(org, deployment['patch_ref'])
            if not same(self.adapters.validate(patch, org), deployment['adapter']):
                raise OrgError('Adapter changed; new governed adoption is required.')
            return {'deployment_id': deployment['deployment_id'], 'actor': actor, 'profile': profile(context),
                    'adoption_required': not validated(deployment, context), 'authorized': validated(deployment, context),
                    'effect': 'Schema/metadata assessment only; changed identities require fresh governed adoption.'}
        if operation == 'review':
            require_fields(data, ('deployment_id', 'subject', 'tool', 'arguments', 'evidence'))
            deployment = value['deployments'].get(data['deployment_id'])
            if (not deployment or deployment['status'] != 'active' or actor == data['subject']
                    or data['subject'] not in org['members'] or not isinstance(data['tool'], str)
                    or not isinstance(data['arguments'], dict) or not data['evidence']):
                raise OrgError('A different actual member reviews an active deployment exact action with evidence.')
            if get_patch_in(org, deployment['patch_ref'])['kind'] != 'protocol':
                raise OrgError('Action review requires a governed protocol deployment.')
            receipt = {'review_id': uid('scope_review'), 'deployment_id': deployment['deployment_id'],
                'reviewer': actor, 'subject': data['subject'], 'tool': data['tool'], 'arguments': detached(data['arguments']),
                'profile': profile(context_for(org, data['subject'])), 'evidence': detached(data['evidence']),
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), 'at': now()}
            value['reviews'][receipt['review_id']] = receipt
            return receipt
        if operation == 'execute':
            require_fields(data, ('patch_ref', 'input', 'idempotency_key'))
            if not isinstance(data['idempotency_key'], str) or not data['idempotency_key']:
                raise OrgError('Execution requires a stable idempotency key.')
            request = detached(data)
            request_key = json.dumps([actor, data['idempotency_key']])
            if request_key in value['executions']:
                previous = value['executions'][request_key]
                if not same(previous['request'], request):
                    raise OrgError('Execution idempotency key identifies different arguments.')
                return {**previous, 'replayed': True}
            receipt = {'execution_id': uid('scope_execution'), 'actor': actor, 'request': request, 'at': now(),
                       'allowed': False, 'output': None, 'effect': 'refused'}
            try:
                requested_patch = get_patch_in(org, data['patch_ref'])
            except OrgError:
                requested_patch = None
            execution_tool = ('scope_tool:' + requested_patch['payload'].get('operation', requested_patch['kind'])) if requested_patch else None
            resolution = selected_assets(org, actor, execution_tool, self.adapters)
            selected = next((d for d in resolution['selected'] if same(d['patch_ref'], data['patch_ref'])), None)
            if selected is None:
                receipt['reason'] = 'Exact Patch is not approved, applicable and revalidated in this context.'
            else:
                patch = selected['patch']
                descriptor = self.adapters.validate(patch, org)
                if not same(descriptor, selected['adapter']):
                    receipt['reason'] = 'Adapter revision changed; new governed adoption required.'
                else:
                    from ..store import gate
                    tool = 'scope_tool:' + patch['payload'].get('operation', patch['kind'])
                    verdict = gate(org, actor, tool, {'patch_ref': data['patch_ref'], 'input': data['input']})
                    receipt['gate'] = verdict
                    receipt.update(deployment_id=selected['deployment_id'], patch_ref=selected['patch_ref'], scope_ref=selected['scope_ref'])
                    if not verdict['allowed']:
                        receipt['reason'] = '; '.join(verdict['reasons'])
                    else:
                        receipt.update(self.adapters.execute(patch, data['input'], org), allowed=True)
            value['executions'][request_key] = receipt
            return receipt
        raise OrgError('Unknown SCOPE operation: ' + operation)
