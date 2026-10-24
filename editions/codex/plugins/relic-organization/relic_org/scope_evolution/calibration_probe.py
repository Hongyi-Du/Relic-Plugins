"""Development-only checks executed through the model's own local command tool."""
import hashlib
import inspect
import ipaddress
import json
from pathlib import Path
import re
import shlex

from ..store import OrgError


SCRIPT_NAME = 'calibration_sandbox_check.py'
PROBE_SCHEMA = 'scope-calibration-model-isolation-v1'
PROOF_SCHEMA = 'scope-calibration-model-path-proof-v1'


def targets(probes):
    result = [{k: p[k] for k in ('host', 'address', 'port')} for p in probes if p.get('kind') == 'tcp']
    if (len(result) != 2 or {p['host'] for p in result} != {'github.com', 'pypi.org'} or
            any(not ipaddress.ip_address(p['address']).is_global or p['port'] != 443 for p in result)):
        raise OrgError('Model-path probes require the two actual public preflight TCP targets.')
    return result


def probe_source(probes):
    expected = targets(probes)
    return '''import errno,json,os,socket
targets = json.loads(%r)
tcp = []
for target in targets:
    connection = None
    result = dict(target, blocked=False, error_code=None)
    try:
        connection = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        connection.settimeout(3)
        connection.connect((target['address'],target['port']))
    except OSError as error:
        result.update(blocked=error.errno in (errno.EPERM,errno.EACCES),error_code=error.errno)
    finally:
        if connection is not None: connection.close()
    tcp.append(result)
credentials = []
for label,path in [('env',os.path.join(os.environ.get('CODEX_HOME','/scope-home'),'auth.json')),('literal','/scope-home/auth.json')]:
    result = dict(label=label,path=path,blocked=False,error_code=None)
    if label=='env': result['environment_variable_present']='CODEX_HOME' in os.environ
    try:
        descriptor = os.open(path,os.O_RDONLY)
        os.close(descriptor)
    except OSError as error:
        result.update(blocked=error.errno in (errno.EPERM,errno.EACCES,errno.ENOENT),error_code=error.errno)
    credentials.append(result)
result = dict(schema=%r,tcp=tcp,credentials=credentials)
print(json.dumps(result,sort_keys=True))
raise SystemExit(0 if all(row['blocked'] for row in tcp+credentials) else 2)
''' % (json.dumps(expected, sort_keys=True), PROBE_SCHEMA)


def is_probe_command(command):
    try:
        words = shlex.split(command)
        if words and Path(words[0]).name in ('bash', 'sh'):
            if words[1:-1] not in (['-lc'], ['-c'], ['-l', '-c']):
                return False
            words = shlex.split(words[-1])
    except (ValueError, IndexError, TypeError):
        return False
    if words[:3] == ['cd', '/product', '&&']:
        words = words[3:]
    if words[:1] == ['CODEX_HOME=/scope-home']:
        words = words[1:]
    if not words or not re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(words[0]).name):
        return False
    words = words[1:]
    while words and words[0] in ('-I', '-B', '-u'):
        words = words[1:]
    return words in ([SCRIPT_NAME], ['./' + SCRIPT_NAME], ['/product/' + SCRIPT_NAME])


def model_isolation_evidence(events, *, thread_id, turn_id, probes, script_unchanged):
    expected = targets(probes)
    calls, web_search = [], []
    for row in events:
        message = row.get('message') or {}
        params = message.get('params') or {}
        if (row.get('direction') != 'in' or params.get('threadId') != thread_id or
                not turn_id or params.get('turnId') != turn_id):
            continue
        item = params.get('item') or {}
        if message.get('method') in ('item/started', 'item/completed') and item.get('type') == 'webSearch':
            web_search.append(item.get('id'))
        if message.get('method') != 'item/completed' or item.get('type') != 'commandExecution':
            continue
        command = item.get('command') or ''
        if not is_probe_command(command):
            continue
        for line in (item.get('aggregatedOutput') or '').splitlines():
            try:
                value = json.loads(line.strip())
            except ValueError:
                continue
            if not isinstance(value, dict) or value.get('schema') != PROBE_SCHEMA:
                continue
            tcp, credentials = value.get('tcp', []), value.get('credentials', [])
            valid = (item.get('exitCode') == 0 and item.get('status') == 'completed' and len(tcp) == 2 and len(credentials) == 2 and
                all(isinstance(p, dict) and {k: p.get(k) for k in ('host', 'address', 'port')} == target
                    and p.get('blocked') is True and p.get('error_code') in (1, 13)
                    for p, target in zip(tcp, expected)) and
                {p.get('label') for p in credentials if isinstance(p, dict)} == {'env', 'literal'} and
                all(isinstance(p, dict) and p.get('path') == '/scope-home/auth.json' and
                    p.get('blocked') is True and p.get('error_code') in (1, 2, 13) and
                    (p.get('label') != 'env' or p.get('environment_variable_present') is True) for p in credentials))
            calls.append({'item_id': item.get('id'), 'command': command, 'exit_code': item.get('exitCode'),
                          'checks': value, 'passed': bool(valid)})
    return {'schema': PROOF_SCHEMA, 'thread_id': thread_id, 'turn_id': turn_id,
        'script_sha256': hashlib.sha256(probe_source(probes).encode('utf-8')).hexdigest(),
        'script_unchanged': script_unchanged is True, 'expected_tcp_targets': expected,
        'web_search_item_ids': sorted(set(web_search)), 'completed_probe_commands': calls,
        'passed': bool(script_unchanged and not web_search and any(c['passed'] for c in calls))}


def model_isolation_contract():
    return {'schema': PROOF_SCHEMA, 'probe_schema': PROBE_SCHEMA, 'script_name': SCRIPT_NAME,
        'module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'function_sha256': {f.__name__: hashlib.sha256(inspect.getsource(f).encode('utf-8')).hexdigest()
                            for f in (targets, probe_source, is_probe_command, model_isolation_evidence)},
        'tcp_required_errors': ['EPERM', 'EACCES'],
        'credential_checks': ['CODEX_HOME/auth.json', '/scope-home/auth.json'],
        'credentials_content_read': False, 'web_search': 'forbidden',
        'evidence': 'actual current-turn completed command, unchanged supplied probe and exact preflight targets'}
