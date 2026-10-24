"""Evidence about protocol decisions, without storing private tool bodies."""
import hashlib
import json


def decision_context(org, actor, tool, arguments, verdict, *, source, turn_id=None, tool_use_id=None):
    protocols = []
    for pid in verdict['protocol_ids']:
        p = org['protocols'][pid]
        protocols.append({'id': pid, 'version': p.get('version'), 'title': p['title'], 'rules': p['rules']})
    return {
        **verdict, 'source': source, 'tool': tool,
        'protocol_versions': {p['id']: p['version'] for p in protocols},
        'protocol_snapshots': protocols,
        'episode_id': org['members'].get(actor, {}).get('active_episode'),
        'turn_id': turn_id, 'tool_use_id': tool_use_id,
        'argument_keys': sorted(arguments),
        'argument_value_hashes': {k: hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                                  for k, v in arguments.items()},
        'argument_context': {k: arguments[k] for k in ('key', 'expected_revision')
                             if k in arguments and isinstance(arguments[k], (str, int, float, bool, type(None)))},
        'context_boundary': 'Exact action hash, argument field hashes, protocol snapshot, episode/turn and nearby tool status. '
                            'Private commands, prompts, source bodies and stdout are not copied; the actor can locate the original call in its own chat.',
    }


def protocol_activity(store, org_id, actor=None, *, after=0, recent_limit=12):
    """Count canonical decisions across the entire requested event range, never wrapper duplicates."""
    org = store.get(org_id, actor)
    kinds = ('protocol.enforced', 'protocol.preflight', 'observation.protocol.blocked', 'observation.protocol.checked', 'benchmark.release_attempt')
    with store.connect() as db:
        rows = db.execute('SELECT seq,id,actor,kind,body,at FROM events WHERE org_id=? AND seq>? '
                          'AND kind IN (?,?,?,?,?) ORDER BY seq', (org_id, after, *kinds)).fetchall()
    events = [dict(seq=r[0], id=r[1], actor=r[2], kind=r[3], body=json.loads(r[4]), at=r[5]) for r in rows]
    counts = {pid: {'protocol_id': pid, 'version': p.get('version'), 'status': p['status'], 'title': p['title'],
                    'strength': p.get('strength', 'strong'),
                    'member_reported_uses': len(p.get('uses', {})),
                    'member_reported_followed': sum(u['outcome'] == 'followed' for u in p.get('uses', {}).values()),
                    'member_reported_deviated': sum(u['outcome'] == 'deviated' for u in p.get('uses', {}).values()),
                    'member_reported_inapplicable': sum(u['outcome'] == 'inapplicable' for u in p.get('uses', {}).values()),
                    'use_work_units': sorted({u['work_unit'] for u in p.get('uses', {}).values()}),
                    'use_evidence': list(p.get('uses', {}).values()),
                    'enforcement_attempts': 0, 'blocked_attempts': 0, 'allowed_attempts': 0,
                    'preflight_checks': 0, 'preflight_denied': 0, 'preflight_allowed': 0,
                    'operation_errors_after_allow': 0, 'review_receipts': 0, 'ambiguous_legacy_block_attribution': 0}
              for pid, p in org['protocols'].items()}
    for event in events:
        body = event['body']
        for pid in set(body.get('protocol_ids', [])):
            if pid not in counts:
                continue
            c = counts[pid]
            allowed = body.get('allowed', event['kind'] == 'observation.protocol.checked')
            specific = body.get('protocol_decisions', {}).get(pid)
            ambiguous = not specific and not allowed and len(set(body.get('protocol_ids', []))) > 1
            protocol_allowed = specific['allowed'] if specific else allowed
            if event['kind'] == 'protocol.preflight':
                c['preflight_checks'] += 1
                if not ambiguous:
                    c['preflight_allowed' if protocol_allowed else 'preflight_denied'] += 1
            else:
                c['enforcement_attempts'] += 1
                if not ambiguous:
                    c['allowed_attempts' if protocol_allowed else 'blocked_attempts'] += 1
                c['operation_errors_after_allow'] += int(allowed and body.get('operation_status') == 'error')
            c['ambiguous_legacy_block_attribution'] += int(ambiguous)
    for review in org['reviews'].values():
        if review['protocol_id'] in counts:
            counts[review['protocol_id']]['review_receipts'] += 1
    events = [e for e in events if e['body'].get('protocol_ids')]
    limit = max(0, min(recent_limit, 50))
    recent = events[-limit:] if limit else []
    with store.connect() as db:
        for event in recent:
            if event['kind'].startswith('observation.'):
                event['body']['source'] = 'trusted_local_hook'
            event['linked_episode_ids'] = [ep['id'] for ep in org['episodes'].values() if event['id'] in ep.get('events', [])]
            nearby = []
            for comparator, order in (('<', 'DESC'), ('>', 'ASC')):
                neighbors = db.execute(f'SELECT seq,id,kind,body,at FROM events WHERE org_id=? AND actor=? AND seq{comparator}? '
                                       "AND kind IN ('observation.tool.result','protocol.enforced','protocol.preflight') "
                                       f'ORDER BY seq {order} LIMIT 2', (org_id, event['actor'], event['seq'])).fetchall()
                for row in neighbors:
                    body = json.loads(row[3])
                    nearby.append({'seq': row[0], 'id': row[1], 'kind': row[2], 'at': row[4],
                                   **{k: body[k] for k in ('tool', 'action_hash', 'failed', 'exit_code', 'allowed', 'operation_status') if k in body}})
            event['nearby_same_actor_events'] = sorted(nearby, key=lambda e: e['seq'])
    return {'org_id': org_id, 'after_event': after, 'protocols': counts,
            'registered_weak_protocols': sum(p.get('strength', 'strong') == 'weak' for p in org['protocols'].values()),
            'registered_strong_protocols': sum(p.get('strength', 'strong') == 'strong' for p in org['protocols'].values()),
            'practice_coverage': 'Use records and work units are lifetime member reports with evidence references, not verified execution or causal benefit. '
                                 'Agreement/adoption alone is not use. Weak protocol use is separate from strong enforcement. '
                                 'Unregistered protocols may exist in shared messages/documents; registry totals are not an exhaustive census.',
            'recorded_enforcement_attempts': sum(e['kind'] != 'protocol.preflight' for e in events),
            'recorded_blocked_attempts': sum(e['kind'] != 'protocol.preflight' and not e['body'].get('allowed', e['kind'] == 'observation.protocol.checked') for e in events),
            'recorded_preflight_checks': sum(e['kind'] == 'protocol.preflight' for e in events),
            'first_recorded_decision_at': events[0]['at'] if events else None,
            'historical_coverage': 'Recorded events only. Older server decisions and preflight checks were not logged; '
                                   'zero records is not proof of zero real blocks. Pure gate() simulations are excluded. '
                                   'An allowed gate decision is not proof of successful tool execution or improved task score. '
                                   'Review receipt totals are lifetime metadata, independent of after_event.',
            'recent_decisions': recent}
