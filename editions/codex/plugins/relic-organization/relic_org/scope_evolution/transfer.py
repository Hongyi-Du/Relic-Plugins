"""Portable candidate assets; transfer never conveys deployment authority."""
from ..store import OrgError, now
from .adapters import detached
from .models import validate_patch, validate_scope, patch_ref, scope_ref
from .resolver import Truth, matches_scope


PATCH_FIELDS = ('patch_id', 'kind', 'payload', 'base_version', 'payload_ref', 'rollback_ref',
                'dependencies', 'conflicts', 'evidence_refs', 'affected_objects', 'cost', 'risk_level')
SCOPE_FIELDS = ('scope_id', 'include', 'exclude', 'evidence_refs', 'base_version')


def export_transfer(org, actor, selected):
    assets = []
    for deployment in selected:
        patch, scope = deployment['patch'], deployment['scope']
        assets.append({'source_patch_ref': patch_ref(patch), 'source_scope_ref': scope_ref(scope),
            'patch': {k: patch[k] for k in PATCH_FIELDS if k in patch},
            'scope': {k: scope[k] for k in SCOPE_FIELDS if k in scope}, 'adapter': deployment['adapter']})
    return detached({'format': 'scope-transfer-v1', 'source_org': org['id'], 'exported_by': actor,
        'exported_at': now(), 'assets': assets, 'authority': 'none; destination registration and governed adoption required'})


def validate_transfer(pack, org, context, adapters):
    pack = detached(pack)
    if not isinstance(pack, dict) or set(pack) != {'format', 'source_org', 'exported_by', 'exported_at', 'assets', 'authority'}:
        raise OrgError('Invalid transfer pack; approval/deployment records must not be imported.')
    if pack['format'] != 'scope-transfer-v1' or not isinstance(pack['assets'], list):
        raise OrgError('Unsupported transfer format.')
    results, refs = [], set()
    for asset in pack['assets']:
        if not isinstance(asset, dict) or set(asset) != {'source_patch_ref', 'source_scope_ref', 'patch', 'scope', 'adapter'}:
            raise OrgError('Transfer assets contain candidate content and exact provenance only.')
        patch = validate_patch(asset['patch'], context['member_id'])
        scope = validate_scope(asset['scope'])
        pref = asset['source_patch_ref']
        from .models import validate_patch_ref, validate_scope_ref
        validate_patch_ref(pref)
        validate_scope_ref(asset['source_scope_ref'])
        if patch['patch_id'] != pref['patch_id'] or scope['scope_id'] != asset['source_scope_ref']['scope_id']:
            raise OrgError('Transfer provenance does not match the candidate identity.')
        identity = (pref['patch_id'], pref['revision'])
        if identity in refs:
            raise OrgError('Duplicate transferred Patch reference.')
        refs.add(identity)
        try:
            descriptor = adapters.validate(patch, org)
            compatible = descriptor == asset['adapter']
            reason = None if compatible else 'Adapter revision differs.'
        except OrgError as error:
            compatible, reason = False, str(error)
        applicability = matches_scope(scope, context)
        results.append({'source_patch_ref': pref, 'adapter_compatible': compatible,
            'applicability': applicability.value, 'reason': reason,
            'compatible': compatible and applicability is Truth.TRUE,
            'dependencies': patch['dependencies']})
    for result in results:
        if any((d['patch_id'], d['revision']) not in refs for d in result.pop('dependencies')):
            result.update(compatible=False, reason='Transfer dependency closure is incomplete.')
    return {'destination_org': org['id'], 'validated_context': detached(context), 'assets': results,
        'compatible': bool(results) and all(r['compatible'] for r in results), 'adoption_required': True,
        'deployed': False, 'effect': 'Compatibility assessment only; no approvals or deployments imported.'}
