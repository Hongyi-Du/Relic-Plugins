"""One fresh official app-server thread, created before its single model turn.

create_executor(workspace, output, ...) returns .thread_id and audited .facts.
The transport seam is for lifecycle tests; it is not evidence of a live run.
"""
import hashlib
import errno
import json
import math
import os
import ipaddress
import posixpath
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

from ..store import OrgError, now


_VERIFIED = object()
PERMISSION_PROFILE = 'scope-product'
TOOL_ITEMS = frozenset({'commandExecution', 'fileChange', 'mcpToolCall', 'dynamicToolCall',
                        'webSearch', 'imageView', 'imageGeneration', 'collabAgentToolCall'})
ERROR_MAPPING = {
    'contextWindowExceeded': 'task_budget_expired', 'sessionBudgetExceeded': 'task_budget_expired',
    'tooManyDenials': 'task_policy_failure', 'cyberPolicy': 'task_policy_failure',
    'misalignmentPolicyViolation': 'task_policy_failure',
    'usageLimitExceeded': 'quota_exhausted', 'rateLimitExceeded': 'quota_exhausted',
    'unauthorized': 'auth_error', 'badRequest': 'deterministic_error',
    'activeTurnNotSteerable': 'deterministic_error',
    'serverOverloaded': 'infrastructure_error', 'internalServerError': 'infrastructure_error',
    'httpConnectionFailed': 'infrastructure_error', 'responseStreamConnectionFailed': 'infrastructure_error',
    'responseStreamDisconnected': 'infrastructure_error', 'responseTooManyFailedAttempts': 'infrastructure_error',
    'flexUnavailable': 'infrastructure_error', 'other': 'infrastructure_error',
    'sandboxError': 'infrastructure_error', 'threadRollbackFailed': 'infrastructure_error',
}
CONTAMINATION_RULES = {
    'schema': 'scope-contamination-v2', 'web_search': 'any started/completed webSearch invalidates',
    'external_network': 'curl Connected to numeric global IP plus HTTP response invalidates; HTTP Request logs are flags even for public URLs',
    'denied_access': 'count and retain; a denied attempt alone does not invalidate',
    'local_network': 'local HTTP through variables and loopback sockets are permitted; keywords are counted',
    'outside_product_reads': '/tmp and image files are flags only; only successful scope-home reads invalidate',
    'postflight': 'same container/profile, exact network targets and literal/env credential open checks; reachable/openable invalidates; unknown stops ungraded',
    'scan_scope': 'owned thread/turn item started/completed only; host audit excluded',
    'invalid_action': 'retain counted attempt and checkpoint; stop without reserve retry or grading',
}
NETWORK_CLIENT = re.compile(r'(?i)(?:\b(?:curl|wget|invoke-webrequest|invoke-restmethod|ssh|scp|sftp|nc|netcat)\b|'
    r'\bgit\s+(?:clone|fetch|pull|ls-remote)\b|\b(?:pip3?|npm|yarn|uv)\s+(?:install|add|sync)\b|'
    r'\b(?:requests|httpx|urllib|http\.client|socket)\b.*(?:get|post|open|connect|request|getaddrinfo|gethostbyname)|'
    r'\b(?:fetch|urlopen|create_connection|getaddrinfo|gethostbyname)\s*\()', re.S)
DENIED_ACCESS = re.compile(r'(?i)(permission denied|access (?:is )?denied|operation not permitted|'
    r'network is unreachable|network access (?:is )?(?:disabled|denied)|temporary failure in name resolution|'
    r'name or service not known|could not resolve host|connection refused|sandbox[^\n]*(?:denied|blocked))')
HTTP_RESPONSE = re.compile(r'(?im)(?:\bHTTP/(?:1(?:\.\d)?|2|3)\s+[1-5]\d\d\b|'
                           r'<Response \[[1-5]\d\d\b[^\]]*\]>)')
HTTP_REQUEST_LOG = re.compile(r'(?i)\bHTTP Request:\s*(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+https?://')


def public_response_hosts(command, output):
    """Mockable HTTP client logs do not prove a connection to a public peer."""
    if not re.search(r'(?i)\bcurl\b', command) or not HTTP_RESPONSE.search(output):
        return []
    hosts = set()
    for address in re.findall(r'(?im)^\*?\s*Connected to\s+\S+\s+\(([^)]+)\)\s+port\s+\d+', output):
        try:
            if ipaddress.ip_address(address).is_global:
                hosts.add(address)
        except ValueError:
            continue
    return sorted(hosts)


def classify_error(error):
    """Explicit schema mapping; unknown errors stop instead of silently rerolling."""
    info = error.get('codexErrorInfo') if isinstance(error, dict) else None
    if info is None and isinstance(error, dict) and isinstance(error.get('data'), dict):
        info = error['data'].get('codexErrorInfo')
    code = info if isinstance(info, str) else next(iter(info), None) if isinstance(info, dict) and len(info) == 1 else None
    detail = info.get(code) if isinstance(info, dict) and code else None
    http = detail.get('httpStatusCode') if isinstance(detail, dict) else None
    if http in (401, 403):
        code, status = 'unauthorized', 'auth_error'
    elif http == 429:
        code, status = 'rateLimitExceeded', 'quota_exhausted'
    elif http == 400:
        code, status = 'badRequest', 'deterministic_error'
    else:
        if code is None and isinstance(error, dict) and error.get('code') in (-32700, -32600, -32601, -32602):
            code = 'badRequest'
        status = ERROR_MAPPING.get(code, 'deterministic_error')
    code = code or 'unclassifiedError'
    return {'status': status, 'scoreable': status in ('task_budget_expired', 'task_policy_failure'),
        'retryable': status == 'infrastructure_error',
        'stop_required': status in ('auth_error', 'quota_exhausted', 'deterministic_error'),
        'failure_code': code, 'failure_kind': status,
        'result_flags': [code] if status in ('task_budget_expired', 'task_policy_failure') else []}


def scan_contamination(events, *, thread_id, turn_id, postflight=None):
    """Deterministic accounting of owned tool items, without RPC/account content."""
    items = {}
    for row in events:
        if row.get('direction') != 'in':
            continue
        message = row.get('message') or {}
        params = message.get('params') or {}
        if (message.get('method') not in ('item/started', 'item/completed') or
                params.get('threadId') != thread_id or not turn_id or params.get('turnId') != turn_id):
            continue
        item = params.get('item') or {}
        if item.get('id'):
            items[item['id']] = item
    counts = {'web_search_items': 0, 'network_commands': 0, 'denied_access_commands': 0,
              'outside_product_read_commands': 0, 'public_response_commands': 0,
              'http_request_log_commands': 0, 'successful_scope_home_reads': 0,
              'network_isolation_failures': 0, 'credential_isolation_failures': 0}
    findings = []
    for item_id, item in sorted(items.items()):
        if item.get('type') == 'webSearch':
            counts['web_search_items'] += 1
            findings.append({'item_id': item_id, 'kind': 'web_search', 'disposition': 'invalid'})
        if item.get('type') != 'commandExecution':
            continue
        command, output = item.get('command') or '', item.get('aggregatedOutput') or ''
        denied = bool(DENIED_ACCESS.search(output)) or item.get('status') == 'declined'
        if denied:
            counts['denied_access_commands'] += 1
            findings.append({'item_id': item_id, 'kind': 'denied_access', 'disposition': 'blocked_attempt',
                             'exit_code': item.get('exitCode'), 'output_tail': output[-512:]})
        read_paths = [a['path'] for a in item.get('commandActions', []) if isinstance(a, dict)
            and a.get('type') in ('read', 'search', 'listFiles') and isinstance(a.get('path'), str)]
        if not read_paths and re.search(r'(?i)\b(cat|head|tail|sed|awk|less|more|grep|rg|find|ls)\b|read_text|read_bytes|\bopen\s*\(', command):
            read_paths += re.findall(r'(?<![\w:])(?:/|\.\./)[\w./-]+', command)
        cwd = item.get('cwd') if isinstance(item.get('cwd'), str) else '/product'
        normalized = {posixpath.normpath(posixpath.join(cwd, p)) for p in read_paths}
        outside = sorted(p for p in normalized if p != '/product' and not p.startswith('/product/'))
        if outside:
            counts['outside_product_read_commands'] += 1
            findings.append({'item_id': item_id, 'kind': 'outside_product_read', 'paths': outside,
                'disposition': 'flag', 'exit_code': item.get('exitCode')})
        scope_home = any(p == '/scope-home' or p.startswith('/scope-home/') for p in outside)
        if scope_home and item.get('exitCode') == 0 and item.get('status') != 'declined' and not denied:
            counts['successful_scope_home_reads'] += 1
            findings.append({'item_id': item_id, 'kind': 'successful_scope_home_read', 'disposition': 'invalid'})
        if HTTP_REQUEST_LOG.search(output):
            counts['http_request_log_commands'] += 1
            findings.append({'item_id': item_id, 'kind': 'http_request_log', 'disposition': 'flag'})
        if NETWORK_CLIENT.search(command):
            counts['network_commands'] += 1
            findings.append({'item_id': item_id, 'kind': 'network_keyword', 'disposition': 'flag',
                'exit_code': item.get('exitCode'), 'command': command[:2000]})
            public = public_response_hosts(command, output)
            if public:
                counts['public_response_commands'] += 1
                findings.append({'item_id': item_id, 'kind': 'public_response', 'hosts': public, 'disposition': 'invalid'})
    if postflight is not None:
        network = postflight.get('network_canary', postflight)
        credentials = postflight.get('credential_canary', {})
        for probe, name in ((network, 'network'), (credentials, 'credential')):
            if probe.get('status') == 'failed':
                counts[name + '_isolation_failures'] += 1
                findings.append({'kind': name + '_isolation_failure', 'disposition': 'invalid',
                                 'artifact': probe.get('artifact')})
    unverified = postflight is not None and postflight.get('status') not in ('passed', 'failed')
    if unverified:
        findings.append({'kind': 'postflight_unverified', 'disposition': 'flag', 'artifact': postflight.get('artifact')})
    invalid = any(f['disposition'] == 'invalid' for f in findings)
    return {'schema': CONTAMINATION_RULES['schema'], 'status': 'contaminated' if invalid else 'unverified' if unverified else 'clean',
            'counts': counts, 'findings': findings, 'invalid': invalid}


def network_canary(client, *, phase='preflight', probes=None, raise_on_failure=True):
    """Host resolves public numeric targets; owned sandbox probes DNS and TCP."""
    if phase not in ('preflight', 'postflight'):
        raise OrgError('Network canary phase must be preflight or postflight.')
    if probes is None:
        if phase == 'postflight':
            raise OrgError('Postflight requires the exact recorded preflight targets.')
        targets = []
        for host in ('github.com', 'pypi.org'):
            addresses = sorted({a[4][0] for a in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)})
            addresses = [a for a in addresses if ipaddress.ip_address(a).is_global]
            if not addresses:
                raise OrgError('Network canary needs a public host-resolved IPv4 target: ' + host)
            targets.append({'kind': 'tcp', 'host': host, 'address': addresses[0], 'port': 443})
        probes = [{'kind': 'dns', 'host': 'github.com'}, *targets]
    else:
        probes = [{k: p[k] for k in ('kind', 'host', 'address', 'port') if k in p} for p in probes]
    if (len(probes) != 3 or [(p.get('kind'), p.get('host')) for p in probes] !=
            [('dns', 'github.com'), ('tcp', 'github.com'), ('tcp', 'pypi.org')] or
            any(p.get('port') != 443 or not ipaddress.ip_address(p.get('address', '')).is_global for p in probes[1:])):
        raise OrgError('Exact public DNS and direct TCP canary targets are required.')
    inner = ('import json,socket,sys; p=json.loads(sys.argv[1]); socket.setdefaulttimeout(3);\n'
        'try:\n'
        ' if p["kind"]=="dns": socket.getaddrinfo(p["host"],443)\n'
        ' else:\n'
        '  s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(3); s.connect((p["address"],p["port"])); s.close()\n'
        ' result={**p,"status":"reachable","blocked":False}\n'
        'except OSError as e: result={**p,"status":"error","blocked":False,"error_type":type(e).__name__,"errno":e.errno}\n'
        'print(json.dumps(result))')
    outer = ('import json,subprocess,sys; result=[];\n'
        'for p in json.loads(sys.argv[1]):\n'
        ' try:\n'
        '  r=subprocess.run([sys.executable,"-I","-c",sys.argv[2],json.dumps(p)],capture_output=True,text=True,timeout=5,check=True)\n'
        '  result.append(json.loads(r.stdout))\n'
        ' except subprocess.TimeoutExpired: result.append({**p,"status":"unknown","blocked":False,"error_type":"TimeoutExpired"})\n'
        'print(json.dumps(result))')
    try:
        response = client._request('command/exec', {'command': ['python', '-I', '-c', outer,
            json.dumps(probes), inner], 'cwd': '/product', 'permissionProfile': PERMISSION_PROFILE,
            'timeoutMs': 20000}, timeout=30)
    except Exception as error:
        response = {'error_type': type(error).__name__, 'error': str(error)}
    try:
        actual = json.loads(response['stdout'])
        valid = response.get('exitCode') == 0 and isinstance(actual, list) and len(actual) == 3 and all(
            isinstance(r, dict) and all(r.get(k) == v for k, v in p.items()) for p, r in zip(probes, actual))
        if not valid:
            actual = []
    except (ValueError, KeyError, TypeError):
        actual = []
    for row in actual:
        denied = row.get('errno') in (errno.EPERM, errno.EACCES) and row.get('error_type') not in ('TimeoutError', 'TimeoutExpired')
        dns_failed = row['kind'] == 'dns' and row.get('error_type') == 'gaierror'
        row['blocked'] = denied or dns_failed
        row['status'] = 'denied' if denied else 'resolution_failed' if dns_failed else 'reachable' if row.get('status') == 'reachable' else 'unknown'
    passed = bool(actual) and all(r['blocked'] for r in actual)
    status = 'passed' if passed else 'failed' if any(r['status'] == 'reachable' for r in actual) else 'unknown'
    artifact = client.output / ('network-canary.json' if phase == 'preflight' else 'network-canary-postflight.json')
    receipt = {'schema': 'scope-network-canary-v2', 'phase': phase, 'status': status,
        'passed': passed, 'permission_profile': PERMISSION_PROFILE,
        'tcp_uses_host_resolved_numeric_ipv4': True, 'probes': actual, 'command_receipt': response,
        'artifact': str(artifact), 'container_name': getattr(getattr(client, 'transport', None), 'container_name', None),
        'model_turns_submitted_by_probe': 0}
    write_json(artifact, receipt)
    if not passed and raise_on_failure:
        raise OrgError('Real sandbox DNS/TCP network canary failed (' + status + '); no inference permitted.')
    return receipt


def credential_canary(client, *, phase='preflight', raise_on_failure=True):
    """Check open permission only, without reading credentials or logging paths/values."""
    if phase not in ('preflight', 'postflight'):
        raise OrgError('Credential canary phase must be preflight or postflight.')
    script = ('import json,os; result=[];\n'
        'for target in ("literal","env"):\n'
        ' home=os.environ.get("CODEX_HOME"); p="/scope-home/auth.json" if target=="literal" else os.path.join(home,"auth.json") if home and os.path.isabs(home) else None\n'
        ' r={"target":target,"status":"unknown"}\n'
        ' if p is None: r["error_type"]="MissingAbsoluteCodexHome"\n'
        ' else:\n'
        '  try:\n'
        '   with open(p,"rb"): pass\n'
        '   r["status"]="openable"\n'
        '  except (OSError,ValueError) as e: r.update(status="error",error_type=type(e).__name__,errno=getattr(e,"errno",None))\n'
        ' result.append(r)\n'
        'print(json.dumps(result))')
    try:
        response = client._request('command/exec', {'command': ['python', '-I', '-c', script],
            'cwd': '/product', 'permissionProfile': PERMISSION_PROFILE, 'timeoutMs': 20000}, timeout=30)
    except Exception as error:
        response = {'error_type': type(error).__name__}
    try:
        actual = json.loads(response['stdout'])
        valid = response.get('exitCode') == 0 and isinstance(actual, list) and len(actual) == 2 and all(
            isinstance(r, dict) and r.get('target') == target for r, target in zip(actual, ('literal', 'env')))
        actual = [{k: r[k] for k in ('target', 'status', 'errno', 'error_type') if k in r} for r in actual] if valid else []
    except (ValueError, KeyError, TypeError):
        actual = []
    for row in actual:
        opened = row.get('status') == 'openable'
        blocked = row.get('status') == 'error' and row.get('errno') in (errno.EPERM, errno.EACCES, errno.ENOENT)
        row.update(blocked=blocked, status='openable' if opened else 'unavailable' if blocked and
                   row.get('errno') == errno.ENOENT else 'denied' if blocked else 'unknown')
    passed = bool(actual) and all(r['blocked'] for r in actual)
    status = 'passed' if passed else 'failed' if any(r['status'] == 'openable' for r in actual) else 'unknown'
    artifact = client.output / ('credential-canary.json' if phase == 'preflight' else 'credential-canary-postflight.json')
    receipt = {'schema': 'scope-credential-canary-v1', 'phase': phase, 'status': status,
        'passed': passed, 'permission_profile': PERMISSION_PROFILE, 'probes': actual,
        'check': 'open rb then close; zero content reads; labels only; no credential or environment values',
        'command_receipt': {k: response[k] for k in ('exitCode', 'error_type') if k in response},
        'artifact': str(artifact), 'container_name': getattr(getattr(client, 'transport', None), 'container_name', None),
        'model_turns_submitted_by_probe': 0}
    write_json(artifact, receipt)
    if not passed and raise_on_failure:
        raise OrgError('Real sandbox credential-open canary failed (' + status + '); no inference permitted.')
    return receipt


def token_usage_report(usage):
    """Keep raw counters and the preregistered reporting views, without a cap."""
    total = (usage or {}).get('total') or {}
    def value(name):
        result = total.get(name)
        return result if type(result) is int else None
    input_tokens, cached = value('inputTokens'), value('cachedInputTokens')
    output, reasoning = value('outputTokens'), value('reasoningOutputTokens')
    return {'total_tokens': value('totalTokens'),
        'noncached_input_tokens': input_tokens - cached if input_tokens is not None and cached is not None else None,
        'output_tokens': output, 'reasoning_output_tokens': reasoning,
        'nonreasoning_output_tokens': output - reasoning if output is not None and reasoning is not None and output >= reasoning else None,
        'output_plus_reasoning_tokens': output,
        'output_accounting': 'reported output already includes reasoning; reasoning is a subset, not added twice',
        'policy': 'report_only', 'raw': copy_json(usage)}


def copy_json(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class RpcError(RuntimeError):
    pass


class StdioTransport:
    def __init__(self, workspace, output, command=None, denied_paths=()):
        executable = command or os.getenv('CODEX_CLI_PATH') or shutil.which('codex')
        if not executable:
            raise OrgError('Official Codex CLI is required; no provider fallback exists.')
        forbidden = [name for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'ACCESS_TOKEN',
            'OPENAI_BASE_URL', 'OPENAI_API_BASE', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY',
            'CODEX_MODEL_PROVIDER', 'OPENAI_MODEL_PROVIDER') if os.environ.get(name)]
        if forbidden:
            raise OrgError('Custom endpoint/API environment is forbidden: ' + ', '.join(forbidden))
        source_home = Path(os.getenv('CODEX_HOME', str(Path.home() / '.codex')))
        auth = source_home / 'auth.json'
        if not auth.is_file():
            raise OrgError('Existing official ChatGPT login auth.json is required.')
        self.clean_home = tempfile.TemporaryDirectory(prefix='scope-codex-')
        try:
            shutil.copyfile(auth, Path(self.clean_home.name) / 'auth.json')
        except BaseException:
            self.clean_home.cleanup()
            raise
        env = {k: v for k, v in os.environ.items() if not k.startswith(
            ('CODEX_', 'RELIC_', 'CLAUDE_', 'MCP_', 'CHATGPT_'))}
        env['CODEX_HOME'] = self.clean_home.name
        temporary = Path(self.clean_home.name) / 'tmp'
        temporary.mkdir()
        env['TMP'] = env['TEMP'] = str(temporary)
        self.argv = [executable, 'app-server', '-c', 'model_provider="openai"',
            '-c', 'forced_login_method="chatgpt"', '-c', 'model_reasoning_effort="xhigh"',
            '-c', 'project_doc_max_bytes=0', '-c', 'features.memories=false', '-c', 'web_search="disabled"',
            '-c', 'features.plugins=false', '-c', 'features.apps=false',
            '-c', 'features.multi_agent=false', '-c', 'mcp_servers={}', '-c', 'plugins={}']
        if os.name == 'nt':
            self.argv += ['-c', 'windows.sandbox="elevated"']
        self.denied_paths = sorted({str(Path(p).resolve()) for p in [Path(__file__).resolve().parents[2],
            output, source_home, Path(os.getenv('RELIC_HOME', str(Path.home() / '.relic'))), *denied_paths]})
        files = {':root': 'read', ':workspace_roots': 'write', ':tmpdir': 'deny', ':slash_tmp': 'deny',
                 **{path: 'deny' for path in self.denied_paths}, str(Path(workspace).resolve()): 'write'}
        filesystem = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in files.items()) + '}'
        self.argv += ['-c', 'default_permissions="scope-product"',
            '-c', 'permissions.scope-product.extends=":workspace"',
            '-c', 'permissions.scope-product.filesystem=' + filesystem,
            '-c', 'permissions.scope-product.network.enabled=false']
        self.stderr = (Path(output) / 'stderr.log').open('w', encoding='utf-8')
        self._launch(workspace, env)

    def _launch(self, workspace, env):
        self._closed = False
        try:
            self.process = subprocess.Popen(self.argv, cwd=workspace, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except BaseException:
            self.stderr.close()
            self.clean_home.cleanup()
            raise
        self.messages = queue.Queue()
        def read():
            try:
                for line in self.process.stdout:
                    try:
                        self.messages.put(json.loads(line))
                    except ValueError:
                        self.messages.put({'method': 'transport/nonJson', 'params': {'line': line}})
            finally:
                self.process.stdout.close()
                self.messages.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def receive(self, timeout):
        try:
            message = self.messages.get(timeout=max(0, timeout))
        except queue.Empty:
            raise TimeoutError('app-server response deadline expired.') from None
        if message is None:
            raise EOFError('Official app-server closed.')
        return message

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.stderr):
            stream.close()
        self.clean_home.cleanup()


class DockerStdioTransport(StdioTransport):
    """Official Linux CLI; host grader/source/artifact trees are never mounted."""
    def __init__(self, workspace, output, image=None):
        self.host_identity = container_identity(image)
        for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'ACCESS_TOKEN', 'OPENAI_BASE_URL',
                     'OPENAI_API_BASE', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY',
                     'CODEX_MODEL_PROVIDER', 'OPENAI_MODEL_PROVIDER'):
            if os.environ.get(name):
                raise OrgError('Custom endpoint/API environment is forbidden: ' + name)
        source_home = Path(os.getenv('CODEX_HOME', str(Path.home() / '.codex')))
        if not (source_home / 'auth.json').is_file():
            raise OrgError('Existing official ChatGPT login auth.json is required.')
        self.clean_home = tempfile.TemporaryDirectory(prefix='scope-codex-container-')
        try:
            shutil.copyfile(source_home / 'auth.json', Path(self.clean_home.name) / 'auth.json')
        except BaseException:
            self.clean_home.cleanup()
            raise
        self.rpc_workspace = '/product'
        self.container_name = 'scope-episode-' + hashlib.sha256(str(output).encode()).hexdigest()[:24]
        self.mounts = [{'source': str(Path(workspace).resolve()), 'destination': '/product', 'read_write': True},
                       {'source': self.clean_home.name, 'destination': '/scope-home', 'read_write': True}]
        self.argv = ['docker', 'run', '--rm', '-i', '--init', '--name', self.container_name,
            '--security-opt', 'seccomp=unconfined', '--cap-add', 'SYS_ADMIN',
            '--mount', 'type=bind,source=' + str(Path(workspace).resolve()) + ',target=/product',
            '--mount', 'type=bind,source=' + self.clean_home.name + ',target=/scope-home',
            self.host_identity['image_id'], 'app-server', '-c', 'model_provider="openai"',
            '-c', 'forced_login_method="chatgpt"', '-c', 'model_reasoning_effort="xhigh"',
            '-c', 'project_doc_max_bytes=0', '-c', 'features.memories=false', '-c', 'web_search="disabled"',
            '-c', 'features.plugins=false', '-c', 'features.apps=false', '-c', 'features.multi_agent=false',
            '-c', 'mcp_servers={}', '-c', 'plugins={}', '-c', 'default_permissions="scope-product"',
            '-c', 'permissions.scope-product.extends=":workspace"',
            '-c', 'permissions.scope-product.filesystem={":root"="deny",":minimal"="read","/scope-home"="deny","/product"="write","/tmp"="write"}',
            '-c', 'permissions.scope-product.network.enabled=false']
        self.stderr = (Path(output) / 'stderr.log').open('w', encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('CODEX_', 'RELIC_', 'CLAUDE_', 'MCP_', 'CHATGPT_'))}
        self._launch(workspace, env)

    def close(self):
        if self._closed:
            return
        subprocess.run(['docker', 'rm', '-f', self.container_name], capture_output=True, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        super().close()

    def audit(self, client):
        metadata = json.loads(subprocess.run(['docker', 'inspect', self.container_name], capture_output=True,
            text=True, encoding='utf-8', check=True, timeout=30).stdout)[0]
        mounts = metadata['Mounts']
        if (metadata['Image'] != self.host_identity['image_id'] or len(mounts) != 2 or
                {m['Destination'] for m in mounts} != {'/product', '/scope-home'} or
                any(m['Type'] != 'bind' or m['RW'] is not True for m in mounts)):
            raise OrgError('Actual container image/mounts differ from the frozen solver isolation contract.')
        script = ('import pathlib,json; r={"cwd":str(pathlib.Path.cwd()),"product_write":False}; '
            'p=pathlib.Path(".scope-host-canary"); p.write_text("HOST ONLY"); '
            'r["product_write"]=p.read_text()=="HOST ONLY"; p.unlink(); '
            'print(json.dumps(r))')
        probe = client._request('command/exec', {'command': ['python', '-I', '-c', script],
            'cwd': '/product', 'permissionProfile': PERMISSION_PROFILE, 'timeoutMs': 20000}, timeout=30)
        try:
            checked = json.loads(probe['stdout'])
        except (ValueError, KeyError):
            checked = {}
        if probe.get('exitCode') != 0 or checked != {'cwd': '/product', 'product_write': True}:
            raise OrgError('Actual task sandbox canary failed; no inference is permitted.')
        credentials = credential_canary(client)
        network = network_canary(client)
        config = client._request('config/read', {'includeLayers': False, 'cwd': '/product'})['config']
        servers = client._request('mcpServerStatus/list', {}).get('data', [])
        if (config.get('forced_login_method') != 'chatgpt' or config.get('model_provider') != 'openai' or servers
                or config.get('web_search') != 'disabled'
                or any((config.get('features') or {}).get(k) is not False for k in ('memories', 'plugins', 'apps', 'multi_agent'))):
            raise OrgError('Child inherited an unapproved provider, project MCP, plugin or memory configuration.')
        return {'mounts': mounts, 'container_image_id': metadata['Image'], 'sandbox_probe': probe,
                'network_canary': network, 'credential_canary': credentials,
                'mcp_servers': [], 'forced_login_method': 'chatgpt', 'model_provider': 'openai',
                'web_search': 'disabled',
                'model_turns_submitted': 0}


def container_identity(image=None):
    image = image or os.getenv('SCOPE_CODEX_IMAGE', 'scope-natural-solver:20261020')
    result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True,
                            timeout=30, check=True, encoding='utf-8')
    metadata = json.loads(result.stdout)[0]
    # No opaque old project image: this image's build provenance is part of P0.
    expected = {'scope.natural-solver': 'official-cli-only', 'scope.codex-version': '0.163.0-alpha.10.2'}
    if any((metadata['Config'].get('Labels') or {}).get(k) != v for k, v in expected.items()):
        raise OrgError('Use the clean scripts/scope_solver.Dockerfile image, not an unrelated project image.')
    version = subprocess.run(['docker', 'run', '--rm', metadata['Id'], '--version'], capture_output=True,
                             text=True, timeout=30, check=True, encoding='utf-8').stdout.strip()
    return {'transport': 'official_codex_app_server_container', 'image': image, 'image_id': metadata['Id'],
            'cli_version': version, 'dockerfile_sha256': hashlib.sha256(
                (Path(__file__).resolve().parents[2] / 'scripts' / 'scope_solver.Dockerfile').read_bytes()).hexdigest()}


def execution_contract():
    """P0 identity of the actual official-CLI container, without model inference."""
    contract = container_identity()
    contract['implementation_sha256'] = {name: hashlib.sha256(
        Path(__file__).with_name(name).read_bytes()).hexdigest() for name in
        ('codex_episode.py', 'episode_binding.py', 'natural_driver.py', 'natural_recovery.py')}
    contract['isolation'] = {'mounts': ['product:rw', 'clean_login_home:rw'],
        'unmounted': ['grader_source', 'run_outputs', 'coordination_store', 'parent_home'],
        'permission_profile': PERMISSION_PROFILE, 'inner_filesystem': 'root_deny_minimal_read_product_write',
        'task_network': False, 'provider_network': 'official_openai_chatgpt_only',
        'web_search': 'disabled', 'task_tools': ['local_shell', 'local_file_edit'],
        'approval_policy': 'never', 'capabilities': ['SYS_ADMIN'], 'seccomp': 'unconfined',
        'reason': 'Linux bubblewrap requires namespaces inside the isolated container',
        'inherited_project_docs': False, 'inherited_plugins_mcp_memory': False}
    contract['network_canary'] = {'schema': 'scope-network-canary-v2', 'permission_profile': PERMISSION_PROFILE,
        'probes': ['DNS github.com', 'TCP github.com:443 numeric IPv4', 'TCP pypi.org:443 numeric IPv4'],
        'required': 'preflight and postflight same container/profile/targets; TCP must fail with EPERM/EACCES',
        'timeout': 'unknown; gate fails; never counted as denied',
        'postflight_unknown': 'stop ungraded, nonretryable; retain execution status without claiming contamination'}
    contract['credential_canary'] = {'schema': 'scope-credential-canary-v1', 'permission_profile': PERMISSION_PROFILE,
        'probes': ['literal /scope-home/auth.json', 'env CODEX_HOME/auth.json'],
        'required': 'preflight and postflight same container/profile; open rb and close with zero reads',
        'blocked': 'EPERM/EACCES or ENOENT (sandbox-hidden file); both paths required',
        'openable': 'failed isolation; contaminated, ungraded, nonretryable',
        'unknown': 'stop ungraded, nonretryable', 'output': 'target labels and error types/errno only; no credential or environment values'}
    contract['postflight_isolation'] = {'schema': 'scope-postflight-isolation-v1',
        'artifact': 'postflight-isolation.json', 'components': ['network_canary', 'credential_canary'],
        'status': 'failed if either failed; passed only if both passed; otherwise unknown',
        'raw_artifacts': ['network-canary-postflight.json', 'credential-canary-postflight.json']}
    contract['contamination_rules'] = copy_json(CONTAMINATION_RULES)
    contract['error_mapping'] = dict(ERROR_MAPPING)
    contract['error_mapping_unknown'] = 'deterministic_error; stop; never retry with reserve'
    contract['budget'] = {'wall_seconds': 1800, 'tool_actions': 80, 'token_usage': 'report_only'}
    return contract


class CodexExecutor:
    def __init__(self, transport, output):
        self.transport, self.output = transport, Path(output)
        self.seq = 0
        self.pending = []
        self._facts = None
        self._verified = None
        self._used = False
        self._lock = threading.Lock()
        self.events_path = self.output / 'rpc-events.jsonl'

    @property
    def facts(self):
        if self._verified is not _VERIFIED:
            raise OrgError('Executor has no verified thread/start response.')
        return copy_json(self._facts)

    @property
    def thread_id(self):
        return self.facts['thread_id']

    def _event(self, direction, message):
        with self.events_path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'at': now(), 'direction': direction, 'message': message},
                                    ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()

    def _send(self, message):
        self._event('out', message)
        self.transport.send(message)

    def _receive(self, timeout):
        message = self.transport.receive(timeout)
        self._event('in', message)
        return message

    def _request(self, method, params, timeout=30):
        self.seq += 1
        request_id = self.seq
        self._send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while True:
            message = self._receive(max(0, deadline - time.monotonic()))
            if message.get('id') == request_id and 'method' not in message:
                if 'error' in message:
                    raise RpcError(method + ': ' + json.dumps(message['error']))
                return message.get('result', {})
            if 'id' in message and 'method' in message:
                self._answer(message)
            else:
                self.pending.append(message)

    def _answer(self, message):
        # Same runner policy: only the member's own non-URL Relic elicitation is accepted.
        params = message.get('params') or {}
        if (message.get('method') == 'mcpServer/elicitation/request'
                and params.get('serverName') == 'relic_org' and params.get('mode') != 'url'):
            content = {}
            for name, spec in (params.get('requestedSchema') or {}).get('properties', {}).items():
                if not isinstance(spec, dict):
                    continue
                if spec.get('default') is not None:
                    value = spec['default']
                elif spec.get('type') == 'boolean':
                    value = True
                elif spec.get('enum'):
                    value = spec['enum'][0]
                elif spec.get('oneOf') and isinstance(spec['oneOf'][0], dict):
                    value = spec['oneOf'][0].get('const')
                elif spec.get('type') in ('number', 'integer'):
                    value = spec.get('minimum', 0)
                else:
                    value = [] if spec.get('type') == 'array' else ''
                content[name] = value
            reply = {'result': {'action': 'accept', 'content': content}}
        else:
            reply = {'error': {'code': -32000, 'message': 'Declined by background runner policy.'}}
        self._send({'jsonrpc': '2.0', 'id': message['id'], **reply})

    def postflight_isolation(self):
        """Run the actual same-profile probes after a turn, before container close."""
        if isinstance(self.transport, DockerStdioTransport):
            probes = self.facts['isolation_audit']['network_canary']['probes']
            network = network_canary(self, phase='postflight', probes=probes, raise_on_failure=False)
            credentials = credential_canary(self, phase='postflight', raise_on_failure=False)
            statuses = (network['status'], credentials['status'])
            status = 'failed' if 'failed' in statuses else 'passed' if statuses == ('passed', 'passed') else 'unknown'
            result = {'schema': 'scope-postflight-isolation-v1', 'phase': 'postflight',
                'status': status, 'passed': status == 'passed', 'permission_profile': PERMISSION_PROFILE,
                'container_name': self.transport.container_name, 'network_canary': network,
                'credential_canary': credentials, 'model_turns_submitted_by_probe': 0}
        else:
            # The explicitly supplied transport seam is reserved for isolated tests.
            probe = getattr(self.transport, 'postflight_isolation', None)
            result = probe(self) if callable(probe) else {
                'schema': 'scope-postflight-isolation-v1', 'phase': 'postflight', 'status': 'unknown',
                'passed': False, 'error': 'Actual postflight probe unavailable.'}
        result = {**result, 'artifact': str(self.output / 'postflight-isolation.json')}
        write_json(result['artifact'], result)
        return result

    def run(self, input_items, budget=None):
        """Submit once. The binding persists intent before calling this method."""
        limits = {'wall_seconds': 1800, 'tool_actions': 80}
        limits.update(budget or {})
        if set(limits) != {'wall_seconds', 'tool_actions'} or any(
                type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in limits.values()):
            raise OrgError('Positive wall_seconds and tool_actions limits required; token usage is report-only.')
        with self._lock:
            if self._used:
                raise OrgError('A fresh executor admits exactly one turn; never retry an uncertain submission.')
            self._used = True
        facts = self.facts
        started = time.monotonic()
        deadline = started + limits['wall_seconds']
        turn_id, terminal, expiry = None, None, None
        tools, tokens, text_parts, echoes = set(), None, [], []
        interrupt_sent = False
        acknowledged = False
        echo_verified = False
        receipt = {'thread_id': facts['thread_id'], 'session_id': facts['session_id'],
            'facts': facts, 'budget': limits, 'submitted_input': copy_json(input_items),
            'rpc_events': str(self.events_path), 'status': 'submission_unknown', 'scoreable': False,
            'retryable': False, 'stop_required': True, 'failure_code': None, 'failure_kind': None,
            'result_flags': [], 'token_policy': 'report_only'}
        try:
            self.seq += 1
            start_request = self.seq
            self._send({'jsonrpc': '2.0', 'id': start_request, 'method': 'turn/start',
                'params': {'threadId': facts['thread_id'], 'input': input_items,
                           'model': facts['effective_model'], 'effort': facts['effective_effort']}})
            while terminal is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 and expiry is None:
                    expiry = 'wall_seconds'
                if expiry and turn_id and not interrupt_sent:
                    self.seq += 1
                    self._send({'jsonrpc': '2.0', 'id': self.seq, 'method': 'turn/interrupt',
                                'params': {'threadId': facts['thread_id'], 'turnId': turn_id}})
                    interrupt_sent = True
                    deadline = time.monotonic() + 30
                if expiry and (not turn_id or (interrupt_sent and time.monotonic() >= deadline)):
                    self.close()
                    raise TimeoutError('Task deadline reached without a confirmed interrupted terminal event.')
                try:
                    message = self.pending.pop(0) if self.pending else self._receive(max(0, deadline - time.monotonic()))
                except TimeoutError:
                    continue
                if 'id' in message and 'method' in message:
                    self._answer(message)
                    continue
                if message.get('id') == start_request and 'method' not in message:
                    if 'error' in message:
                        receipt.update(**classify_error(message['error']), error=message['error'], submission='rejected')
                        break
                    returned_turn = message.get('result', {}).get('turn', {})
                    acknowledged = True
                    actual_id = returned_turn.get('id')
                    if not actual_id or (turn_id and actual_id != turn_id):
                        raise OrgError('turn/start response identity disagrees with the owned turn.')
                    turn_id = actual_id
                    if returned_turn.get('status') in ('completed', 'failed', 'interrupted'):
                        terminal = returned_turn
                    continue
                params = message.get('params') or {}
                if params.get('threadId') != facts['thread_id']:
                    continue
                event_turn = params.get('turnId') or (params.get('turn') or {}).get('id')
                if event_turn and turn_id and event_turn != turn_id:
                    raise OrgError('Event turn identity disagrees with the owned turn.')
                if message.get('method') == 'turn/started':
                    turn_id = event_turn
                elif message.get('method') == 'thread/tokenUsage/updated':
                    usage = params.get('tokenUsage') or {}
                    tokens = copy_json(usage)
                elif message.get('method') == 'item/completed':
                    item = params.get('item') or {}
                    if item.get('type') in TOOL_ITEMS and item.get('id'):
                        tools.add(item['id'])
                        if len(tools) >= limits['tool_actions']:
                            expiry = expiry or 'tool_actions'
                    if item.get('type') == 'agentMessage' and isinstance(item.get('text'), str):
                        text_parts.append(item['text'])
                    if item.get('type') == 'userMessage':
                        echoes.append(copy_json(item))
                elif message.get('method') == 'turn/completed':
                    terminal = params.get('turn')
            if terminal is not None:
                if not turn_id or terminal.get('id') != turn_id:
                    raise OrgError('Terminal event must identify the actual turn.')
                if terminal.get('status') == 'failed':
                    error = terminal.get('error') or {}
                    receipt.update(**classify_error(error), error=error)
                elif expiry and terminal.get('status') in ('interrupted', 'completed'):
                    receipt.update(status='task_budget_expired', scoreable=True, retryable=False, stop_required=False,
                        failure_kind='task_budget_expired', failure_code=expiry, result_flags=[expiry])
                elif terminal.get('status') == 'completed':
                    receipt.update(status='completed', scoreable=True, stop_required=False)
                else:
                    receipt.update(status='deterministic_error', failure_code='unexpectedInterruption',
                        failure_kind='deterministic_error', error='Turn interrupted outside task budget.')
            for echo in echoes:
                content = echo.get('content') or []
                if [(i.get('type'), i.get('text')) for i in content] != [
                        (i.get('type'), i.get('text')) for i in input_items]:
                    raise OrgError('Host userMessage differs from the exact approved input.')
            echo_verified = bool(echoes)
        except Exception as error:
            receipt.update(status='submission_unknown', scoreable=False,
                           retryable=False, stop_required=True, failure_kind='submission_unknown',
                           error=str(error), error_type=type(error).__name__)
        receipt.update(turn_id=turn_id, terminal=terminal, budget_expiry=expiry,
            interrupt_sent=interrupt_sent, tool_actions=len(tools), token_usage=tokens,
            token_usage_report=token_usage_report(tokens),
            output_text='\n'.join(text_parts), input_echoes=echoes,
            input_evidence='matching_user_message' if echo_verified else
                'turn_start_acknowledged' if acknowledged else 'unconfirmed',
            elapsed_seconds=time.monotonic() - started)
        try:
            postflight = self.postflight_isolation()
        except Exception as error:
            postflight = {'schema': 'scope-postflight-isolation-v1', 'phase': 'postflight', 'status': 'unknown',
                'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                'artifact': str(self.output / 'postflight-isolation.json')}
            write_json(postflight['artifact'], postflight)
        receipt['postflight_isolation'] = postflight
        try:
            with self.events_path.open(encoding='utf-8') as stream:
                contamination = scan_contamination((json.loads(line) for line in stream),
                    thread_id=facts['thread_id'], turn_id=turn_id, postflight=postflight)
        except (OSError, ValueError, TypeError) as error:
            contamination = {'schema': CONTAMINATION_RULES['schema'], 'status': 'unverified',
                'invalid': False, 'counts': {}, 'findings': [{'kind': 'audit_error', 'error': str(error)}]}
        receipt['contamination'] = contamination
        write_json(self.output / 'contamination.json', contamination)
        if contamination['invalid']:
            receipt.update(execution_status=receipt['status'], status='contaminated', scoreable=False,
                retryable=False, stop_required=True, failure_code='informationContamination',
                failure_kind='contaminated', result_flags=receipt['result_flags'] + ['information_contamination'])
        elif contamination['status'] == 'unverified':
            receipt['execution_status'] = receipt['status']
            if receipt['scoreable'] or receipt['retryable']:
                receipt.update(status='deterministic_error', failure_code='postflightIsolationUnverified',
                               failure_kind='deterministic_error')
            receipt.update(scoreable=False, retryable=False, stop_required=True,
                           result_flags=receipt['result_flags'] + ['postflight_unverified'])
        write_json(self.output / 'terminal.json', receipt)
        return receipt

    def close(self):
        self.transport.close()


def create_executor(workspace, output, *, model='gpt-6.1-sol', effort='xhigh',
                    transport=None, command=None, denied_paths=()):
    """Create an ephemeral thread and audit host facts, with no model turn."""
    workspace, output = str(Path(workspace).resolve()), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'created.json').exists() or (output / 'rpc-events.jsonl').exists():
        raise OrgError('Executor output already exists; recover its receipt rather than recreate a thread.')
    selected_transport = transport or (StdioTransport(workspace, output, command, denied_paths) if command else
                                       DockerStdioTransport(workspace, output))
    client = CodexExecutor(selected_transport, output)
    try:
        init = client._request('initialize', {'clientInfo': {'name': 'scope_episode', 'version': '1.0'},
                                            'capabilities': {'experimentalApi': True}})
        client._send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
        account = client._request('account/read', {'refreshToken': False})
        if (account.get('account') or {}).get('type') != 'chatgpt':
            raise OrgError('SCOPE requires the existing managed ChatGPT account; API keys are not accepted.')
        requested = {'model': model, 'effort': effort, 'workspace': workspace}
        # ThreadStartParams has config, not an effort field; TurnStartParams has effort.
        # Pass both the documented config override and explicit turn effort, audit the response.
        rpc_workspace = getattr(client.transport, 'rpc_workspace', workspace)
        response = client._request('thread/start', {'model': model, 'modelProvider': 'openai',
            'cwd': rpc_workspace, 'ephemeral': True, 'allowProviderModelFallback': False,
            'approvalPolicy': 'never', 'approvalsReviewer': 'auto_review', 'permissions': PERMISSION_PROFILE,
            'config': {'model_reasoning_effort': effort, 'project_doc_max_bytes': 0,
                       'web_search': 'disabled',
                       'features.memories': False, 'features.plugins': False,
                       'features.apps': False, 'features.multi_agent': False}})
        thread = response.get('thread') or {}
        facts = {'thread_id': thread.get('id'), 'session_id': thread.get('sessionId'),
            'requested': requested, 'effective_model': response.get('model'),
            'effective_effort': response.get('reasoningEffort'), 'workspace': workspace,
            'rpc_workspace': response.get('cwd'),
            'account': account, 'initialize': init, 'thread_start': response, 'created_at': now(),
            'transport': getattr(client.transport, 'host_identity', {}).get('transport', 'official_codex_app_server'),
            'host_identity': getattr(client.transport, 'host_identity', None),
            'mounts': getattr(client.transport, 'mounts', None), 'argv': getattr(client.transport, 'argv', None)}
        if not isinstance(facts['thread_id'], str) or not facts['thread_id']:
            raise OrgError('thread/start did not return an actual child thread ID.')
        if (facts['effective_model'] != model or facts['effective_effort'] != effort
                or not response.get('cwd') or response['cwd'] != rpc_workspace
                or response.get('modelProvider') != 'openai' or thread.get('ephemeral') is not True):
            raise OrgError('Host model/effort/workspace/provider/ephemeral facts differ from the request.')
        if response.get('instructionSources'):
            raise OrgError('Unapproved inherited instruction sources loaded into the task child.')
        if rpc_workspace not in response.get('runtimeWorkspaceRoots', []):
            raise OrgError('Default local environment is not attached to the actual product workspace; no inference permitted.')
        if (response.get('activePermissionProfile') or {}).get('id') != PERMISSION_PROFILE:
            raise OrgError('Host did not select the restricted product-only permission profile.')
        if isinstance(client.transport, DockerStdioTransport):
            facts['isolation_audit'] = client.transport.audit(client)
            write_json(output / 'isolation-audit.json', facts['isolation_audit'])
        elif transport is None:
            raise OrgError('Native task isolation is unverified; use the official clean solver container.')
        write_json(output / 'created.json', facts)
        client._facts, client._verified = copy_json(facts), _VERIFIED
        return client
    except BaseException:
        client.close()
        raise
