"""Explicit local reconciliation; never submit a model call or infer a missing notification.

Only the actual launcher may apply a resolution, after its previous controller
and the exact owned containers have ended. Original intent and event logs stay.
"""
import argparse
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from ..store import Store, OrgError, now
from .codex_episode import fingerprint, write_json
from .natural_driver import coordination_roster, episode_receipt, read_json
from .runtime import state, same


def auth_validity_receipt(required_seconds, *, auth_path=None, clock=time.time):
    """Read only expiry metadata; never return credentials or account claims."""
    if type(required_seconds) not in (int, float) or required_seconds <= 0:
        raise OrgError('A positive remaining-lifetime requirement is required.')
    path = Path(auth_path) if auth_path is not None else Path(
        os.getenv('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
    try:
        token = read_json(path)['tokens']['access_token']
        encoded = token.split('.')[1]
        expiry = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))['exp']
        if type(expiry) not in (int, float):
            raise ValueError('expiry')
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise OrgError('Official login access-token expiry cannot be established; no child created.') from None
    remaining = expiry - clock()
    if remaining < required_seconds:
        raise OrgError('Official login remaining lifetime is below the phase budget plus margin; stop without refreshing or retrying.')
    return {'schema': 'scope-auth-lifetime-v1', 'checked_at': now(), 'expires_at': expiry,
        'remaining_seconds': remaining, 'required_seconds': required_seconds, 'passed': True,
        'credentials_exported': False, 'refresh_performed': False}


def process_alive(pid):
    if type(pid) is not int or pid <= 0:
        raise OrgError('A recorded positive controller PID is required.')
    if os.name == 'nt':
        result = subprocess.run(['tasklist', '/FI', 'PID eq ' + str(pid), '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        if result.returncode:
            raise OrgError('Cannot verify old controller process liveness.')
        return any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(result.stdout.splitlines()))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        raise OrgError('Cannot establish that the old controller ended.') from None


def close_owned_container(job, manifest, *, apply, close_owned):
    output = str(Path(job['executor_output']).resolve())
    expected = 'scope-episode-' + hashlib.sha256(output.encode()).hexdigest()[:24]
    if job.get('container_name') != expected:
        raise OrgError('Recovery target differs from the recorded owned container.')
    result = subprocess.run(['docker', 'inspect', expected], capture_output=True,
        text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        if 'no such object' in result.stderr.lower() or 'no such container' in result.stderr.lower():
            return {'container': expected, 'ended': True, 'already_absent': True}
        raise OrgError('Container inspection failed; absence is not established.')
    metadata = json.loads(result.stdout)[0]
    image = manifest['execution_contract']['image_id']
    mounts = metadata.get('Mounts', [])
    products = [m for m in mounts if m.get('Destination') == '/product']
    if (metadata.get('Image') != image or len(mounts) != 2 or len(products) != 1 or
            Path(products[0]['Source']).resolve() != Path(job['spec']['workspace']).resolve()):
        raise OrgError('Live container image/product mount differs from the owned episode.')
    running = metadata['State']['Running']
    if running and not (apply and close_owned):
        raise OrgError('Old owned container is live; explicit --close-owned is required.')
    if running:
        subprocess.run(['docker', 'stop', '--time', '10', expected], check=True,
            capture_output=True, timeout=25)
        check = subprocess.run(['docker', 'inspect', expected], capture_output=True,
            text=True, encoding='utf-8', timeout=30)
        if check.returncode == 0 and json.loads(check.stdout)[0]['State']['Running']:
            raise OrgError('Old container did not end; no retry can be released.')
        if check.returncode and not any(t in check.stderr.lower() for t in ('no such object', 'no such container')):
            raise OrgError('Cannot confirm container termination.')
    return {'container': expected, 'ended': True, 'stopped_by_resolution': bool(running)}


def append_resolution(root, event):
    from .natural_pilot import NaturalPilot
    controller = NaturalPilot(root, None)
    existing = controller.ledger()
    if any(e.get('resolution_id') == event['resolution_id'] for e in existing):
        return
    controller._event(event['kind'], **{k: v for k, v in event.items() if k != 'kind'})


def terminal_result(value, attempt, prepared, job):
    if not isinstance(value, dict) or value.get('status') == 'submission_unknown':
        return None
    terminal = value.get('terminal') or {}
    if (value.get('thread_id') != job['thread_id'] or
            not value.get('turn_id') or terminal.get('id') != value['turn_id'] or
            fingerprint(value.get('submitted_input')) != prepared['input_sha256'] or
            attempt['executor_thread_id'] != job['thread_id']):
        raise OrgError('Terminal identity or exact submitted input differs from durable intent.')
    if terminal.get('status') not in ('completed', 'failed', 'interrupted'):
        raise OrgError('Terminal file has no actual terminal status.')
    return value


def staged_record(record, job, prepared):
    arm = job['spec'].get('deployment_arm', 'Static')
    return {'approved': True, 'job_id': job['spec']['job_id'],
        'prepared_id': prepared['prepared_id'], 'thread_id': job['thread_id'],
        'phase_state': record['phase_state'], 'store': record['store'], 'org_id': record['org_id'],
        'selection': prepared['selection'], 'input_receipt': prepared['input_receipt'],
        'input_sha256': prepared['input_sha256'], 'operational_arm': arm,
        'operational_deployment': record['deployments'].get(arm)}


def _reconcile_phase(path, *, apply=False, close_owned=False, resolve_unknown=False, note='',
                    roster_reader=coordination_roster, is_alive=process_alive,
                    container_closer=close_owned_container):
    path = Path(path).resolve()
    root = path.parents[3]
    if path.parent.parent.parent != root / 'driver' or path.name != 'phase.json':
        raise OrgError('Expected an exact run/driver/phase/batch/phase.json path.')
    record = read_json(path)
    actor = os.getenv('CODEX_THREAD_ID')
    if (actor != record['launcher_actor'] or roster_reader() != record['coordination_roster']):
        raise OrgError('Reconciliation requires the actual current original launcher/roster.')
    if apply and not note.strip():
        raise OrgError('Applying reconciliation requires an explicit review note.')
    if is_alive(record.get('controller_pid')):
        raise OrgError('Old controller is still alive; do not reconcile its active work.')
    manifest = read_json(root / 'manifest.json')['manifest']
    from .natural_pilot import NaturalPilot
    ledger = NaturalPilot(root, None).ledger()
    store = Store(record['store'])
    value = state(store.get(record['org_id'], actor))
    result = {'schema': 'scope-reconciliation-v1', 'phase_state': str(path), 'actor': actor,
        'applied': apply, 'note': note, 'at': now(), 'model_calls_submitted': 0, 'jobs': []}
    for job_id, job in record['jobs'].items():
        intents = [a for a in value.get('turn_attempts', {}).values() if a['executor_thread_id'] == job['thread_id']]
        if len(intents) > 1:
            raise OrgError('Multiple intents for a single executor are invalid.')
        ended = container_closer(job, manifest, apply=apply, close_owned=close_owned)
        if ended.get('ended') is not True:
            raise OrgError('Old executor is not confirmed ended.')
        starts = [e for e in ledger if e['kind'] == 'attempt_started' and e['job_id'] == job_id
                  and e['spec']['workspace'] == job['spec']['workspace']]
        start = starts[-1] if starts else None
        resolution = {'job_id': job_id, 'thread_id': job['thread_id'], 'old_executor': ended,
                      'dispatch_intent': bool(intents), 'submitted_new_call': False}
        controller_event = None
        if not intents:
            resolution.update(status='not_submitted', call_charge=0, basis='no durable Store dispatch intent')
            if apply:
                job['status'] = 'unsubmitted_closed'
        else:
            if not start:
                raise OrgError('Dispatch intent has no controller charge; retain and investigate.')
            attempt = intents[0]
            prepared = value['prepared_turns'][attempt['prepared_id']]
            output = Path(job['executor_output'])
            saved = read_json(output / 'terminal.json') if (output / 'terminal.json').exists() else None
            terminal = terminal_result(attempt.get('result'), attempt, prepared, job)
            if saved is not None:
                from_file = terminal_result(saved, attempt, prepared, job)
                if terminal is not None and from_file is not None and not same(terminal, from_file):
                    raise OrgError('Stored terminal and terminal.json disagree.')
                terminal = terminal or from_file
            if terminal is not None:
                recovered_attempt = {**attempt, 'status': terminal['status'], 'result': terminal}
                staged = staged_record({**record, 'phase_state': str(path)}, job, prepared)
                receipt = episode_receipt(recovered_attempt, job, staged, output / 'rpc-events.jsonl')
                receipt_path = Path(job['directory']) / 'receipt.json'
                if receipt_path.exists() and not same(read_json(receipt_path), receipt):
                    raise OrgError('An existing controller receipt differs; do not overwrite evidence.')
                resolution.update(status=receipt['status'], call_charge=1,
                    basis='matching actual terminal/input/child identity', receipt=str(receipt_path))
                if apply:
                    with store.transaction(record['org_id'], actor, 'scope.episode_reconcile',
                                           {'attempt_id': attempt['attempt_id']}) as (org, db):
                        stored = state(org)['turn_attempts'][attempt['attempt_id']]
                        stored.update(status=terminal['status'], result=terminal)
                    receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    if not receipt_path.exists():
                        write_json(receipt_path, receipt)
                    job['status'] = receipt['status']
                controller_event = {'status': receipt['status'],
                    'receipt': receipt_path.relative_to(root).as_posix(),
                    'retryable': receipt.get('retryable') is True}
            else:
                contamination_path = output / 'contamination.json'
                if ((contamination_path.exists() and read_json(contamination_path).get('invalid') is True) or
                        any((output / name).exists() and read_json(output / name).get('passed') is False
                            for name in ('network-canary-postflight.json', 'credential-canary-postflight.json',
                                         'postflight-isolation.json'))):
                    raise OrgError('Known contamination or failed isolation cannot be released as an uncertain infrastructure retry.')
                resolution.update(status='unknown_closed', call_charge=1,
                    basis='intent exists; missing notifications cannot establish non-submission',
                    partial_workspace=job['spec']['workspace'], partial_product_scored=False,
                    retry_released=bool(apply and resolve_unknown))
                if apply and resolve_unknown:
                    job['status'] = 'infrastructure_error'
                    controller_event = {'status': 'infrastructure_error', 'retryable': True,
                        'failure_kind': 'explicitly_reconciled_unknown', 'original_status': 'uncertain',
                        'same_slot_fresh_workspace_required': True, 'retry_budget_class': 'infrastructure_failure'}
                elif apply:
                    job['status'] = 'uncertain'
        if apply and start:
            event = {'kind': 'attempt_reconciled', 'at': now(), 'attempt_id': start['attempt_id'],
                'job_id': job_id, 'note': note,
                **(controller_event or {'status': 'not_submitted' if not intents else 'uncertain'})}
            event['resolution_id'] = fingerprint({'phase': str(path), 'thread': job['thread_id'],
                'intent': intents[0]['attempt_id'] if intents else None, 'resolution': event['status']})
            append_resolution(root, event)
            resolution['resolution_id'] = event['resolution_id']
        result['jobs'].append(resolution)
    if apply:
        record.update(live_handles=False, reconciliation_at=now())
        write_json(path, record)
        receipt = root / 'recovery' / (fingerprint(result) + '.json')
        receipt.parent.mkdir(exist_ok=True)
        write_json(receipt, result)
        result['reconciliation_receipt'] = str(receipt)
    return result


def reconcile_phase(path, *, apply=False, close_owned=False, resolve_unknown=False, note='',
                    roster_reader=coordination_roster, is_alive=process_alive,
                    container_closer=close_owned_container):
    arguments = dict(apply=apply, close_owned=close_owned, resolve_unknown=resolve_unknown,
        note=note, roster_reader=roster_reader, is_alive=is_alive, container_closer=container_closer)
    if not apply:
        return _reconcile_phase(path, **arguments)
    path = Path(path).resolve()
    root = path.parents[3]
    record = read_json(path)
    if (path.parent.parent.parent != root / 'driver' or path.name != 'phase.json' or
            os.getenv('CODEX_THREAD_ID') != record['launcher_actor'] or
            roster_reader() != record['coordination_roster'] or not note.strip()):
        raise OrgError('Exact owned phase, actual launcher and explicit resolution note required.')
    if is_alive(record.get('controller_pid')):
        raise OrgError('Old controller is still alive.')
    lock = root / '.controller.lock'
    if lock.exists():
        owner = int(lock.read_text(encoding='utf-8').strip())
        if is_alive(owner):
            raise OrgError('Controller lock owner is live; do not remove its lock.')
        lock.unlink()
    from .natural_pilot import controller_lock
    with controller_lock(root):
        return _reconcile_phase(path, **arguments)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--close-owned', action='store_true')
    parser.add_argument('--resolve-unknown', action='store_true')
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile_phase(args.state, apply=args.apply,
            close_owned=args.close_owned, resolve_unknown=args.resolve_unknown, note=args.note),
            ensure_ascii=False, indent=2))
        return 0
    except (OrgError, OSError, ValueError) as error:
        print(json.dumps({'status': 'stopped', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
