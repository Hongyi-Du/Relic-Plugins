"""Create native Codex members and persist a human-requested organization."""
import hashlib
import json
from pathlib import Path

from .bridge import BridgeUnavailable
from .store import OrgError, now


def _table(store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS formations(request_id TEXT PRIMARY KEY, actor TEXT NOT NULL, fingerprint TEXT NOT NULL, body TEXT NOT NULL)')


def _save(store, request_id, result):
    with store.connect() as db:
        db.execute('UPDATE formations SET body=? WHERE request_id=?', (json.dumps(result, ensure_ascii=False), request_id))


def formation(service, operation, request_id, data, actor):
    if not actor or not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 160:
        raise OrgError('Current session and a fresh request_id are required.')
    _table(service.store)
    if operation not in ('start', 'status'):
        raise OrgError('Formation operation must be start or status.')
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if operation == 'start' and data.get('runtime') == 'native_subagents':
        from .native import start
        return start(service, request_id, data, actor, fingerprint)
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT actor,fingerprint,body FROM formations WHERE request_id=?', (request_id,)).fetchone()
        if row:
            if row[0] != actor:
                raise OrgError('This formation belongs to another chat.')
            if operation == 'start' and row[1] != fingerprint:
                raise OrgError('request_id was already used for different organization arguments.')
            return json.loads(row[2])
        if operation == 'status':
            raise OrgError('Unknown formation request_id.')
        if set(data) - {'name', 'task', 'new_members', 'include_current', 'members', 'leader', 'governance', 'execution_mode', 'project_id', 'delivery_mode'}:
            raise OrgError('Unknown organization creation field.')
        name, task = data.get('name', ''), data.get('task', '')
        count = data.get('new_members', 2)
        include = data.get('include_current', True)
        ids = data.get('members', [])
        if not isinstance(name, str) or not name.strip() or not isinstance(task, str) or not task.strip():
            raise OrgError('Provide an organization name and concrete human task.')
        if type(count) is not int or not 0 <= count <= 12 or type(include) is not bool:
            raise OrgError('new_members must be 0–12; include_current must be boolean.')
        if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids):
            raise OrgError('members must contain distinct existing chat IDs.')
        ids = list(dict.fromkeys(([actor] if include else []) + ids))
        if not 1 <= len(ids) + count <= 24:
            raise OrgError('Choose 1–24 members in total.')
        leader = data.get('leader') or (actor if include else ids[0] if ids else None)
        if leader and leader not in ids:
            raise OrgError('The requested leader must be a selected existing chat.')
        governance = data.get('governance', 'leader_with_peer')
        execution = data.get('execution_mode', 'quiet')
        delivery_mode = data.get('delivery_mode', 'after_turn')
        if governance not in ('leader_with_peer', 'majority') or execution not in ('quiet', 'desktop'):
            raise OrgError('Unsupported governance or execution mode.')
        if delivery_mode not in ('after_turn','immediate'):
            raise OrgError('Delivery mode must be after_turn or immediate.')
        # Validate before any native chat mutation. Do not disrupt active organizations.
        for existing in service.store.list():
            if existing['status'] == 'active' and set(ids) & set(existing['members']):
                raise OrgError('A selected chat already belongs to an active organization; pause it or select different chats.')
        result = {'request_id': request_id, 'status': 'preparing', 'requested_by': actor, 'at': now(), 'created_threads': [], 'org_id': None}
        db.execute('INSERT INTO formations VALUES(?,?,?,?)', (request_id, actor, fingerprint, json.dumps(result)))
    try:
        discovery = service.discover()
        if discovery['transport'] != 'desktop':
            raise BridgeUnavailable('Native Codex transport unavailable; no members created.')
        by_id = {i['id']: i for i in service.inventory}
        if any(i not in by_id or by_id[i].get('archived') for i in ids):
            raise OrgError('A selected chat is missing or archived; refresh the catalog.')
        project_id = data.get('project_id')
        projects = []
        if project_id:
            projects = service.bridge.call('list_projects', {})['projects']
            if not any(p['projectId'] == project_id and p.get('projectKind') == 'local' and p.get('hostId') == 'local' for p in projects):
                raise OrgError('project_id must identify a local project returned by list_projects.')
        for index in range(count):
            title = name.strip() + ' · ' + ('负责人' if not leader and index == 0 else '成员 ' + str(index + 1))
            prompt = ('The human requested a Relic organization named ' + name.strip() + '. You are a newly created member in your own native Codex chat. '
                      'Read $relic-organization, report your workspace, then finish this turn and wait for the persisted membership/task message. '
                      'Members will choose their own work division and interfaces through org_message. Do not inspect unrelated workspaces or start a separate model runtime. '
                      'Do not use CLI resume/forks/replacement sessions. Follow the human task constraints from your first action; '
                      'wait for persisted membership and ready materials before implementing. Internal messaging authorization arrives through org_context after enrollment. '
                      '\n\nHuman task and constraints:\n' + task.strip())
            target = ({'type': 'project', 'projectId': project_id, 'environment': {'type': 'local'}} if project_id else
                      {'type': 'projectless', 'directoryName': 'relic-member-' + fingerprint[:8] + '-' + hashlib.sha256(request_id.encode()).hexdigest()[:8] + '-' + str(index + 1)})
            result.update(status='creating', pending_member=index + 1)
            _save(service.store, request_id, result)
            # Mark before sending: a timeout may have created a real chat. Never blindly retry.
            created = service.bridge.call('create_thread', {'title': title, 'prompt': prompt, 'target': target})
            if not created.get('threadId'):
                result.update(status='uncertain', pending_creation=created, reason='Host did not return a ready threadId; inspect before retrying.')
                _save(service.store, request_id, result)
                return result
            # Persist a known native identity before validating its metadata. A
            # malformed ready response must not hide a chat already created.
            chat = {'thread_id': created['threadId'], 'host_id': created.get('hostId', 'local'), 'title': title,
                    'workspace': None, 'creation': created}
            result['created_threads'].append(chat)
            _save(service.store, request_id, result)
            if chat['host_id'] != 'local':
                raise OrgError('The host returned an unsupported remote member.')
            if created.get('projectlessOutputDirectory'):
                chat['workspace'] = str(Path(created['projectlessOutputDirectory']).parent)
            elif project_id:
                chat['workspace'] = next(p['path'] for p in projects if p['projectId'] == project_id)
            else:
                raise OrgError('The native member was created but its workspace metadata is missing; inspect the saved creation receipt.')
            ids.append(chat['thread_id'])
            by_id[chat['thread_id']] = {'id': chat['thread_id'], 'title': title, 'cwd': chat['workspace']}
            if not leader:
                leader = chat['thread_id']
            _save(service.store, request_id, result)
        members = [{'thread_id': i, 'host_id': 'local', 'title': by_id[i]['title'], 'workspace': by_id[i].get('cwd')} for i in ids]
        org = service.store.create(name.strip(), members, leader, governance, execution, delivery_mode)
        result.update(org_id=org['id'], status='enrolled', leader=leader, members=ids)
        _save(service.store, request_id, result)
        authorization = ('Human requested automatic organization formation through Codex chat/window. Internal messages, shared work, meetings and protocol governance among these members are authorized. '
                         'Leader is ' + leader + '. Each member retains its native workspace. Members decide division of work and interfaces themselves. No SDL.\n\nHuman task:\n' + task.strip())
        service.store.execute(org['id'], 'human', 'document_write', {'key': 'human-task-brief', 'body': authorization, 'expected_revision': 0})
        message = service.store.execute(org['id'], 'human', 'message_send', {'body': authorization, 'recipients': ids, 'idempotency_key': 'formation:' + request_id})
        service.deliver(org['id'], message['id'])
        result.update(status='complete', invitation_id=message['id'], completed_at=now(),
                      instruction='Read org_context and coordinate this task. Newly created chats are user-owned and visible in the sidebar.')
        _save(service.store, request_id, result)
        return result
    except Exception as error:
        result.update(status='uncertain' if result['status'] in ('creating', 'enrolled') else 'failed', reason=str(error),
                      instruction='Inspect created_threads and org_id. Reuse this request_id to read the receipt; it never creates duplicate chats. Do not blindly retry an uncertain creation.')
        _save(service.store, request_id, result)
        return result
