"""Fake transports and isolated Stores only; no natural-task model calls."""
import json
import contextlib
import io
import os
import posixpath
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from relic_org.store import Store, OrgError
from relic_org.scope_evolution.codex_episode import (create_executor, StdioTransport,
    CodexExecutor, DockerStdioTransport, classify_error, ERROR_MAPPING, network_canary,
    credential_canary, execution_contract, scan_contamination, token_usage_report)
from relic_org.scope_evolution.episode_binding import EpisodeBinding
from relic_org.scope_evolution.runtime import ScopeRuntime


class FakeTransport:
    def __init__(self, workspace, *, mode='complete', **overrides):
        self.workspace, self.mode, self.overrides = str(workspace), mode, overrides
        self.sent, self.messages, self.closed = [], [], False

    def event(self, method, **params):
        self.messages.append({'method': method, 'params': {'threadId': 'fake-child', 'turnId': 'fake-turn', **params}})

    def send(self, message):
        self.sent.append(message)
        method, rid = message.get('method'), message.get('id')
        if method == 'initialize':
            result = {'userAgent': 'test-only'}
        elif method == 'account/read':
            result = {'account': {'type': self.overrides.get('account_type', 'chatgpt'), 'planType': 'test-only'}}
        elif method == 'thread/start':
            result = {'thread': {'id': 'fake-child', 'sessionId': 'fake-session', 'ephemeral': True},
                'model': 'gpt-6.1-sol', 'modelProvider': 'openai', 'reasoningEffort': 'xhigh',
                'cwd': self.workspace, 'activePermissionProfile': {'id': 'scope-product', 'extends': ':workspace'},
                'runtimeWorkspaceRoots': [self.workspace],
                **{k: v for k, v in self.overrides.items() if k not in
                   ('account_type', 'failure_info', 'tool_items', 'postflight_status', 'credential_status')}}
        elif method == 'turn/start':
            if self.mode == 'lost_ack':
                raise BrokenPipeError('Test-only ambiguous send after remote acceptance.')
            result = {'turn': {'id': 'fake-turn', 'status': 'inProgress'}}
            self.messages.append({'id': rid, 'result': result})
            self.event('turn/started', turn={'id': 'fake-turn', 'status': 'inProgress'})
            content = message['params']['input'] if self.mode != 'wrong_input' else [{'type': 'text', 'text': 'changed'}]
            self.event('item/completed', item={'id': 'user', 'type': 'userMessage', 'content': content})
            if self.mode == 'tool_cap':
                for index in range(80):
                    self.event('item/completed', item={'id': str(index), 'type': 'commandExecution'})
                return
            if self.mode == 'token_cap':
                self.event('thread/tokenUsage/updated', tokenUsage={'total': {'totalTokens': 18000000}})
            if self.mode == 'wall_cap':
                return
            if self.mode == 'approvals':
                for key, server in [('own', 'relic_org'), ('foreign', 'other')]:
                    self.messages.append({'id': key, 'method': 'mcpServer/elicitation/request',
                        'params': {'serverName': server, 'mode': 'form',
                                   'requestedSchema': {'properties': {'ok': {'type': 'boolean'}}}}})
            if self.mode == 'web_contamination':
                self.event('item/completed', item={'id': 'web', 'type': 'webSearch', 'query': 'test-only-query'})
            for item in self.overrides.get('tool_items', []):
                self.event('item/completed', item=item)
            if self.mode in ('network_contamination', 'network_denied', 'file_denied', 'local_network', 'home_contamination'):
                self.event('item/completed', item={'id': 'command', 'type': 'commandExecution',
                    'command': 'cat /scope-home/auth.json' if self.mode in ('file_denied', 'home_contamination') else
                        'curl http://localhost:8000/status' if self.mode == 'local_network' else 'curl https://github.com/test-only',
                    'exitCode': 1 if self.mode in ('network_denied', 'file_denied') else 0,
                    'aggregatedOutput': 'Permission denied' if self.mode in ('network_denied', 'file_denied') else
                        'Connected to github.com (140.82.112.3) port 443\nHTTP/2 200\nTEST ONLY RESPONSE'
                        if self.mode == 'network_contamination' else 'test-only-output'})
            self.event('item/completed', item={'id': 'answer', 'type': 'agentMessage', 'text': 'Test-only product retained.'})
            error = {'codexErrorInfo': 'unauthorized'} if self.mode == 'auth_error' else (
                {'codexErrorInfo': self.overrides['failure_info']} if self.mode == 'failed' else None)
            self.event('turn/completed', turn={'id': 'other-turn' if self.mode == 'wrong_turn' else 'fake-turn',
                'status': 'failed' if error else 'completed', 'error': error})
            return
        elif method == 'turn/interrupt':
            self.messages.append({'id': rid, 'result': {}})
            self.event('turn/completed', turn={'id': 'fake-turn', 'status': 'interrupted'})
            return
        else:
            return
        self.messages.append({'id': rid, 'result': result})

    def receive(self, timeout):
        if self.messages:
            return self.messages.pop(0)
        if self.mode == 'wall_cap':
            time.sleep(min(timeout + .001, .03))
            raise TimeoutError('Test-only wall clock.')
        raise EOFError('Test-only transport ended.')

    def close(self):
        self.closed = True

    def postflight_isolation(self, client):
        network, credential = (self.overrides.get(k, 'passed') for k in ('postflight_status', 'credential_status'))
        status = 'failed' if 'failed' in (network, credential) else 'passed' if (network, credential) == ('passed', 'passed') else 'unknown'
        return {'schema': 'scope-postflight-isolation-v1', 'phase': 'postflight',
            'status': status, 'passed': status == 'passed',
            'network_canary': {'status': network}, 'credential_canary': {'status': credential},
            'test_only': True, 'probe_calls': 1}


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.executors = []
        self.store = Store(self.root / 'test-only.db')
        self.org = self.store.create('Test-only actual-child lifecycle',
            [{'thread_id': 'fake-lead'}, {'thread_id': 'fake-peer'}], 'fake-lead')
        self.oid = self.org['id']
        self.binding = EpisodeBinding(self.store, self.oid, 'fake-lead')
        self.rt = ScopeRuntime(self.store)

    def tearDown(self):
        for executor in self.executors:
            executor.close()
        self.temporary.cleanup()

    def executor(self, **options):
        transport = FakeTransport(self.root, **options)
        executor = create_executor(self.root, self.root / ('executor-' + str(len(self.executors))), transport=transport)
        self.executors.append(executor)
        return executor

    def enroll(self, executor=None):
        executor = executor or self.executor()
        return executor, self.binding.enroll_created_thread(executor,
            {'task_id': 'unchanged-task', 'task_family': 'test-family', 'environment_version': 'test-cp2',
             'phase': 'train', 'replicate': 0}, 'enroll-0')

    def prompt(self):
        patch = self.rt.call(self.oid, 'fake-lead', 'register_patch', {'expected_revision': 0,
            'request_id': 'test-prompt', 'spec': {'patch_id': 'test-prompt', 'kind': 'prompt',
                                              'payload': {'text': 'EXACT TEST PATCH'}}})
        scope = self.rt.call(self.oid, 'fake-lead', 'register_scope', {'expected_revision': 0,
            'request_id': 'test-scope', 'spec': {'scope_id': 'test-scope',
                'include': {'field': 'member_id', 'op': 'eq', 'value': 'fake-child'}, 'exclude': {'const': False}}})
        pref = {'patch_id': patch['patch_id'], 'revision': patch['revision']}
        proposal = self.rt.call(self.oid, 'fake-lead', 'propose', {'expected_revision': 0,
            'bindings': [{'patch_ref': pref, 'scope_ref': {'scope_id': scope['scope_id'], 'revision': scope['revision']}}],
            'evidence': ['test-only transport evidence']})
        return pref, proposal

    def adopt(self, proposal):
        for actor in ('fake-lead', 'fake-peer'):
            self.rt.call(self.oid, actor, 'approve', {'proposal_id': proposal['proposal_id'], 'note': 'TEST ONLY'})
        return self.rt.call(self.oid, 'fake-lead', 'deploy', {'proposal_id': proposal['proposal_id']})['deployments'][0]

    def test_factory_has_child_identity_and_no_turn_before_enrollment_and_approval(self):
        executor, binding = self.enroll()
        self.assertEqual(executor.thread_id, 'fake-child')
        self.assertEqual(executor.facts['session_id'], 'fake-session')
        self.assertNotIn('turn/start', [m.get('method') for m in executor.transport.sent])
        self.assertNotEqual(binding['launcher_actor'], binding['executor_thread_id'])
        pref, proposal = self.prompt()
        with self.assertRaises(OrgError):
            self.binding.prepare_turn(binding['binding_id'], 'BASE', [pref], 'before-approval')
        self.adopt(proposal)
        prepared = self.binding.prepare_turn(binding['binding_id'], 'BASE', [pref], 'prepare-1')
        receipt = self.binding.dispatch_turn(prepared['prepared_id'], executor, 'dispatch-1')
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(receipt['result']['input_evidence'], 'matching_user_message')
        request = next(m for m in executor.transport.sent if m.get('method') == 'turn/start')
        self.assertEqual(request['params']['input'], [{'type': 'text', 'text': 'BASE\n\nEXACT TEST PATCH'}])
        self.assertEqual(json.loads(Path(prepared['input_receipt']).read_text())['input'], request['params']['input'])
        again = self.binding.dispatch_turn(prepared['prepared_id'], executor, 'dispatch-1')
        self.assertTrue(again['replayed'])
        self.assertEqual(sum(m.get('method') == 'turn/start' for m in executor.transport.sent), 1)

    def test_factory_rejects_key_auth_and_host_model_effort_workspace_drift(self):
        for options in ({'account_type': 'apiKey'}, {'model': 'different'}, {'reasoningEffort': 'low'},
                        {'cwd': 'elsewhere'}, {'instructionSources': ['unrelated/AGENTS.md']},
                        {'activePermissionProfile': {'id': ':workspace'}},
                        {'runtimeWorkspaceRoots': []}):
            with self.subTest(options=options):
                transport = FakeTransport(self.root, **options)
                with tempfile.TemporaryDirectory(dir=self.root) as output:
                    with self.assertRaises(OrgError):
                        create_executor(self.root, output, transport=transport)
                self.assertTrue(transport.closed)
                self.assertFalse(any(m.get('method') == 'turn/start' for m in transport.sent))

    def test_custom_endpoint_and_api_environment_rejected_before_start(self):
        for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE',
                     'ACCESS_TOKEN', 'AZURE_OPENAI_ENDPOINT'):
            with self.subTest(name=name), patch.dict(os.environ, {name: 'test-only-forbidden'}):
                with patch('relic_org.scope_evolution.codex_episode.subprocess.Popen') as launch:
                    with self.assertRaisesRegex(OrgError, 'Custom endpoint/API environment'):
                        StdioTransport(self.root, self.root, command='test-only-codex')
                    launch.assert_not_called()

    def test_thread_config_and_turn_effort_follow_actual_cli_shapes(self):
        executor = self.executor()
        executor.run([{'type': 'text', 'text': 'TEST ONLY'}])
        start = next(m['params'] for m in executor.transport.sent if m.get('method') == 'thread/start')
        turn = next(m['params'] for m in executor.transport.sent if m.get('method') == 'turn/start')
        self.assertNotIn('effort', start)
        self.assertEqual(start['config']['model_reasoning_effort'], 'xhigh')
        self.assertEqual(start['config']['web_search'], 'disabled')
        self.assertNotIn('developerInstructions', start)
        self.assertNotIn('selectedCapabilityRoots', start)
        self.assertNotIn('environments', start)
        self.assertEqual(start['permissions'], 'scope-product')
        self.assertNotIn('sandbox', start)
        self.assertEqual(start['approvalPolicy'], 'never')
        self.assertEqual(turn['effort'], 'xhigh')
        self.assertEqual(turn['model'], 'gpt-6.1-sol')

    def test_raw_identity_and_changed_enrollment_are_refused(self):
        with self.assertRaises(OrgError):
            self.binding.enroll_created_thread({'thread_id': 'fake-child'}, {}, 'forged')
        executor, binding = self.enroll()
        spec = binding['request']['spec']
        self.assertEqual(self.binding.enroll_created_thread(executor, spec, 'enroll-0')['binding_id'], binding['binding_id'])
        with self.assertRaises(OrgError):
            self.binding.enroll_created_thread(executor, {**spec, 'replicate': 1}, 'enroll-0')
        with self.assertRaises(OrgError):
            EpisodeBinding(self.store, self.oid, 'fake-peer').enroll_created_thread(executor, spec, 'unauthorized')

    def test_withdrawal_or_roster_drift_refuses_dispatch_before_inference(self):
        executor, binding = self.enroll()
        pref, proposal = self.prompt()
        deployment = self.adopt(proposal)
        prepared = self.binding.prepare_turn(binding['binding_id'], 'BASE', [pref], 'prepare')
        self.rt.call(self.oid, 'fake-lead', 'withdraw', {'deployment_id': deployment['deployment_id'], 'reason': 'TEST ONLY'})
        with self.assertRaises(OrgError):
            self.binding.dispatch_turn(prepared['prepared_id'], executor, 'withdrawn')
        with self.store.transaction(self.oid, 'fake-lead', 'test.only', {}) as (org, db):
            org['members']['fake-child']['scope_context']['task_family'] = 'changed'
        with self.assertRaises(OrgError):
            self.binding.prepare_turn(binding['binding_id'], 'BASE', [], 'drift')
        self.assertFalse(any(m.get('method') == 'turn/start' for m in executor.transport.sent))

    def test_lost_ack_has_durable_unknown_intent_and_never_retries(self):
        executor, binding = self.enroll(self.executor(mode='lost_ack'))
        prepared = self.binding.prepare_turn(binding['binding_id'], 'BASE', [], 'prepare')
        result = self.binding.dispatch_turn(prepared['prepared_id'], executor, 'submit')
        self.assertEqual(result['status'], 'submission_unknown')
        self.assertFalse(result['result']['scoreable'])
        self.assertTrue(self.binding.dispatch_turn(prepared['prepared_id'], executor, 'submit')['replayed'])
        with self.assertRaises(OrgError):
            self.binding.dispatch_turn(prepared['prepared_id'], executor, 'different-key')
        self.assertEqual(sum(m.get('method') == 'turn/start' for m in executor.transport.sent), 1)

    def test_task_caps_interrupt_owned_actual_turn_and_keep_product_scoreable(self):
        for mode in ('tool_cap', 'wall_cap'):
            with self.subTest(mode=mode):
                executor = self.executor(mode=mode)
                result = executor.run([{'type': 'text', 'text': 'TEST'}], {'wall_seconds': .02} if mode == 'wall_cap' else None)
                self.assertEqual(result['status'], 'task_budget_expired')
                self.assertTrue(result['scoreable'])
                interruption = next(m for m in executor.transport.sent if m.get('method') == 'turn/interrupt')
                self.assertEqual(interruption['params'], {'threadId': 'fake-child', 'turnId': 'fake-turn'})
                self.assertEqual(result['terminal']['status'], 'interrupted')

    def test_cumulative_total_tokens_are_reported_without_interrupting(self):
        executor = self.executor(mode='token_cap')
        result = executor.run([{'type': 'text', 'text': 'TEST ONLY'}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['token_usage']['total']['totalTokens'], 18000000)
        self.assertEqual(result['budget'], {'wall_seconds': 1800, 'tool_actions': 80})
        self.assertEqual(result['token_policy'], 'report_only')
        self.assertFalse(any(m.get('method') == 'turn/interrupt' for m in executor.transport.sent))
        with self.assertRaisesRegex(OrgError, 'report-only'):
            self.executor().run([{'type': 'text', 'text': 'TEST'}], {'total_tokens': 180000})

    def test_all_schema_error_variants_have_explicit_nonselective_outcomes(self):
        for code, expected in ERROR_MAPPING.items():
            with self.subTest(code=code):
                info = {code: {'httpStatusCode': 503}} if code.startswith(('http', 'response')) else code
                result = self.executor(mode='failed', failure_info=info).run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['failure_code'], code)
                self.assertEqual(result['retryable'], expected == 'infrastructure_error')
                self.assertEqual(result['scoreable'], expected in ('task_budget_expired', 'task_policy_failure'))
                self.assertEqual(result['stop_required'], expected in ('quota_exhausted', 'auth_error', 'deterministic_error'))
                if result['scoreable']:
                    self.assertIn(code, result['result_flags'])
        for code in ('unknownFutureCode', None, {'unrecognizedVariant': {}}):
            result = classify_error({'codexErrorInfo': code})
            self.assertEqual(result['status'], 'deterministic_error')
            self.assertTrue(result['stop_required'])
            self.assertFalse(result['retryable'])

    def test_http_auth_quota_and_bad_request_never_become_retryable_infra(self):
        for status, expected in ((401, 'auth_error'), (403, 'auth_error'), (429, 'quota_exhausted'), (400, 'deterministic_error')):
            with self.subTest(status=status):
                result = classify_error({'codexErrorInfo': {'httpConnectionFailed': {'httpStatusCode': status}}})
                self.assertEqual(result['status'], expected)
                self.assertTrue(result['stop_required'])
                self.assertFalse(result['retryable'])
        self.assertEqual(classify_error({'code': -32602, 'message': 'test-only invalid params'})['status'], 'deterministic_error')

    def test_episode_contamination_is_counted_preserved_and_never_retryable(self):
        for mode, invalid in (('web_contamination', True), ('network_contamination', True),
                              ('network_denied', False), ('file_denied', False), ('local_network', False),
                              ('home_contamination', True)):
            with self.subTest(mode=mode):
                executor = self.executor(mode=mode)
                result = executor.run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['contamination']['invalid'], invalid)
                self.assertEqual(result['status'], 'contaminated' if invalid else 'completed')
                self.assertEqual(json.loads((executor.output / 'contamination.json').read_text()), result['contamination'])
                if invalid:
                    self.assertFalse(result['scoreable'])
                    self.assertFalse(result['retryable'])
                    self.assertTrue(result['stop_required'])
                    self.assertEqual(result['execution_status'], 'completed')
                if mode == 'network_denied':
                    self.assertEqual(result['contamination']['counts']['network_commands'], 1)
                    self.assertEqual(result['contamination']['counts']['denied_access_commands'], 1)
                if mode == 'local_network':
                    self.assertEqual(result['contamination']['counts']['network_commands'], 1)

    def test_claude262_local_http_variables_loopback_tmp_and_library_reads_are_flags_only(self):
        cases = [
            ('httpx_variable', 'python - <<EOF\nimport httpx\nhost="127.0.0.1"\nbase=f"http://{host}:8000"\nprint(httpx.get(f"{base}/x"))\nEOF',
             'HTTP/1.1 200 OK\nlocal product response with documentation https://github.com/public', 1, 0),
            ('curl_variable', 'curl "$URL"', 'HTTP/1.1 200 OK\n{"local":true}', 1, 0),
            ('loopback_socket', 'python -c \'import socket; socket.create_connection(("127.0.0.1", p))\'',
             'connected to local product', 1, 0),
            ('tmp_log', 'python app.py > /tmp/log 2>&1 & sleep 1; tail /tmp/log', 'server started', 0, 1),
            ('image_library', 'grep -rn request /usr/local/lib/python3.12/site-packages/httpx',
             'client.py:10:request', 0, 1),
        ]
        for name, command, output, network, outside in cases:
            with self.subTest(case=name):
                item = {'id': name, 'type': 'commandExecution', 'command': command,
                        'cwd': '/product', 'exitCode': 0, 'aggregatedOutput': output}
                result = self.executor(tool_items=[item]).run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['status'], 'completed')
                self.assertTrue(result['scoreable'])
                self.assertFalse(result['stop_required'])
                self.assertFalse(result['contamination']['invalid'])
                self.assertEqual(result['contamination']['counts']['network_commands'], network)
                self.assertEqual(result['contamination']['counts']['outside_product_read_commands'], outside)
                self.assertTrue(all(f['disposition'] == 'flag' for f in result['contamination']['findings']))
                self.assertEqual(result['postflight_isolation']['status'], 'passed')

    def test_postflight_failure_or_unknown_stops_without_infrastructure_retry(self):
        for state, status, invalid in (('failed', 'contaminated', True), ('unknown', 'deterministic_error', False)):
            with self.subTest(state=state):
                executor = self.executor(postflight_status=state)
                result = executor.run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['status'], status)
                self.assertEqual(result['execution_status'], 'completed')
                self.assertFalse(result['scoreable'])
                self.assertFalse(result['retryable'])
                self.assertTrue(result['stop_required'])
                self.assertEqual(result['contamination']['invalid'], invalid)
                self.assertEqual(json.loads((executor.output / 'postflight-isolation.json').read_text())['status'], state)

    def test_public_response_requires_endpoint_provenance_not_a_url_in_local_body(self):
        for output, invalid in (
            ('HTTP/1.1 200 OK\n{"docs":"https://github.com/public"}', False),
            ('Connected to localhost (127.0.0.1) port 8000\nHTTP/1.1 200 OK', False),
            ('Connected to github.com (140.82.112.3) port 443\nHTTP/2 200', True),
            ('* Connected to github.com (140.82.112.3) port 443\n< HTTP/2 200', True),
            ('Connected to github.com (github.com) port 443\nHTTP/2 200', False),
            ('Connected to localhost (192.168.1.2) port 8000\nHTTP/1.1 200 OK', False),
            ('HTTP Request: GET https://github.com/public "HTTP/1.1 200 OK"', False)):
            with self.subTest(output=output):
                item = {'id': 'response', 'type': 'commandExecution', 'command': 'curl "$URL"',
                        'exitCode': 0, 'aggregatedOutput': output}
                result = self.executor(tool_items=[item]).run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['contamination']['invalid'], invalid)

    def test_claude276_mocked_httpx_logs_are_flags_and_require_verified_postflight(self):
        cases = [
            ('mocktransport', 'python -c \'import httpx; c=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))); c.get("https://api.example.com/x")\''),
            ('respx', 'python -m pytest test_respx_routes.py'),
        ]
        for name, command in cases:
            for postflight, expected in (('passed', 'completed'), ('failed', 'contaminated'), ('unknown', 'deterministic_error')):
                with self.subTest(case=name, postflight=postflight):
                    item = {'id': name, 'type': 'commandExecution', 'command': command, 'exitCode': 0,
                        'aggregatedOutput': 'INFO:httpx:HTTP Request: GET https://api.example.com/x "HTTP/1.1 200 OK"'}
                    result = self.executor(tool_items=[item], postflight_status=postflight).run([{'type': 'text', 'text': 'TEST ONLY'}])
                    self.assertEqual(result['status'], expected)
                    self.assertEqual(result['contamination']['counts']['http_request_log_commands'], 1)
                    self.assertEqual(result['contamination']['counts']['public_response_commands'], 0)
                    logs = [f for f in result['contamination']['findings'] if f['kind'] == 'http_request_log']
                    self.assertEqual([f['disposition'] for f in logs], ['flag'])
                    self.assertEqual(result['scoreable'], postflight == 'passed')
                    self.assertFalse(result['retryable'])

    def test_credential_postflight_failure_or_unknown_gates_env_read_without_literal_path(self):
        item = {'id': 'env-read', 'type': 'commandExecution', 'command': 'cat "$CODEX_HOME/auth.json"',
            'exitCode': 0, 'aggregatedOutput': 'TEST ONLY: no literal path in command'}
        for credential, expected, invalid in (('passed', 'completed', False),
                ('failed', 'contaminated', True), ('unknown', 'deterministic_error', False)):
            with self.subTest(credential=credential):
                executor = self.executor(tool_items=[item], credential_status=credential)
                result = executor.run([{'type': 'text', 'text': 'TEST ONLY'}])
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['contamination']['invalid'], invalid)
                self.assertEqual(result['contamination']['counts']['network_isolation_failures'], 0)
                self.assertEqual(result['contamination']['counts']['credential_isolation_failures'], int(invalid))
                self.assertEqual(result['postflight_isolation']['network_canary']['status'], 'passed')
                if credential != 'passed':
                    self.assertFalse(result['scoreable'])
                    self.assertFalse(result['retryable'])
                    self.assertTrue(result['stop_required'])
                    self.assertEqual(result['execution_status'], 'completed')

    def test_contamination_ignores_host_audits_foreign_turns_and_deduplicates_items(self):
        def row(method, thread='test-thread', turn='test-turn', **item):
            return {'direction': 'in', 'message': {'method': method, 'params': {
                'threadId': thread, 'turnId': turn, 'item': {'id': 'same-web', 'type': 'webSearch', **item}}}}
        events = [row('command/exec'), row('item/completed', thread='foreign'),
                  row('item/completed', turn='foreign'), row('item/started'), row('item/completed')]
        scan = scan_contamination(events, thread_id='test-thread', turn_id='test-turn')
        self.assertEqual(scan['counts']['web_search_items'], 1)
        self.assertTrue(scan['invalid'])

    def test_outside_product_read_and_parent_traversal_cannot_pass_as_clean(self):
        for command, actions, expected in (
            ('cat /scope-home/auth.json', [], True),
            ('python -c "open(\'/scope-home/auth.json\').read()"', [], True),
            ('cat ../scope-home/auth.json', [], True),
            ('read-command', [{'type': 'read', 'path': '/scope-home/auth.json'}], True),
            ('cat /product/src/file.py', [], False),
            ('cat src/file.py', [{'type': 'read', 'path': 'src/file.py'}], False)):
            with self.subTest(command=command):
                item = {'id': 'read', 'type': 'commandExecution', 'command': command, 'commandActions': actions,
                        'cwd': '/product', 'exitCode': 0, 'aggregatedOutput': 'test-only-data'}
                scan = scan_contamination([{'direction': 'in', 'message': {'method': 'item/completed',
                    'params': {'threadId': 'test', 'turnId': 'turn', 'item': item}}}], thread_id='test', turn_id='turn')
                self.assertEqual(scan['invalid'], expected)
                self.assertEqual(scan['counts']['outside_product_read_commands'], int(expected))

    def test_reported_token_views_keep_cumulative_and_component_counters(self):
        usage = {'total': {'totalTokens': 1150, 'inputTokens': 1000, 'cachedInputTokens': 900,
                           'outputTokens': 150, 'reasoningOutputTokens': 50}}
        result = token_usage_report(usage)
        self.assertEqual(result['total_tokens'], 1150)
        self.assertEqual(result['noncached_input_tokens'], 100)
        self.assertEqual(result['output_plus_reasoning_tokens'], 150)
        self.assertEqual(result['nonreasoning_output_tokens'], 100)
        self.assertEqual(result['raw'], usage)
        self.assertEqual(result['policy'], 'report_only')
        self.assertIsNone(token_usage_report(None)['noncached_input_tokens'])

    def test_compound_command_denial_does_not_hide_an_earlier_successful_external_read(self):
        item = {'id': 'compound', 'type': 'commandExecution', 'command': 'curl https://github.com; cat /scope-home/auth.json',
                'cwd': '/product', 'exitCode': 1,
                'aggregatedOutput': 'Connected to github.com (140.82.112.3) port 443\nHTTP/2 200\nPermission denied'}
        scan = scan_contamination([{'direction': 'in', 'message': {'method': 'item/completed',
            'params': {'threadId': 'test', 'turnId': 'turn', 'item': item}}}], thread_id='test', turn_id='turn')
        self.assertTrue(scan['invalid'])
        self.assertEqual(scan['counts']['denied_access_commands'], 1)
        self.assertEqual(scan['counts']['network_commands'], 1)

    def test_same_profile_network_canary_uses_numeric_tcp_targets_and_requires_all_denied(self):
        class Client:
            output = self.root
            def _request(inner, method, params, timeout):
                inner.params = params
                probes = json.loads(params['command'][4])
                return {'exitCode': 0, 'stdout': json.dumps([{**p, 'status': 'error', 'errno': 1,
                    'error_type': 'PermissionError'} for p in probes]), 'stderr': ''}
        client = Client()
        with patch('relic_org.scope_evolution.codex_episode.socket.getaddrinfo', return_value=[(None, None, None, None, ('1.1.1.1', 443))]):
            receipt = network_canary(client)
        self.assertTrue(receipt['passed'])
        self.assertEqual(client.params['permissionProfile'], 'scope-product')
        self.assertEqual([(p['kind'], p['host']) for p in receipt['probes']],
                         [('dns', 'github.com'), ('tcp', 'github.com'), ('tcp', 'pypi.org')])
        self.assertTrue(all(p['address'] == '1.1.1.1' for p in receipt['probes'][1:]))
        class LeakingClient(Client):
            def _request(inner, *args, **kwargs):
                response = super()._request(*args, **kwargs)
                probes = json.loads(response['stdout']); probes[-1].update(status='reachable', errno=None, error_type=None)
                return {**response, 'stdout': json.dumps(probes)}
        with patch('relic_org.scope_evolution.codex_episode.socket.getaddrinfo', return_value=[(None, None, None, None, ('1.1.1.1', 443))]):
            with self.assertRaisesRegex(OrgError, 'network canary failed'):
                network_canary(LeakingClient())
        self.assertFalse(json.loads((self.root / 'network-canary.json').read_text())['passed'])

    def test_canary_timeout_and_nonpermission_tcp_errors_cannot_pass(self):
        class Client:
            output = self.root
            def __init__(inner, error_type, code):
                inner.error_type, inner.code = error_type, code
            def _request(inner, method, params, timeout):
                probes = json.loads(params['command'][4])
                rows = [{**p, 'status': 'error', 'error_type': 'PermissionError', 'errno': 1} for p in probes]
                rows[-1].update(error_type=inner.error_type, errno=inner.code)
                return {'exitCode': 0, 'stdout': json.dumps(rows), 'stderr': ''}
        for error_type, code in (('TimeoutExpired', None), ('TimeoutError', None), ('OSError', 101), ('ConnectionRefusedError', 111)):
            with self.subTest(error_type=error_type), patch('relic_org.scope_evolution.codex_episode.socket.getaddrinfo',
                    return_value=[(None, None, None, None, ('1.1.1.1', 443))]):
                with self.assertRaisesRegex(OrgError, 'unknown'):
                    network_canary(Client(error_type, code))
                receipt = json.loads((self.root / 'network-canary.json').read_text())
                self.assertEqual(receipt['status'], 'unknown')
                self.assertFalse(receipt['probes'][-1]['blocked'])

    def test_postflight_reuses_preflight_targets_without_new_dns_resolution(self):
        class Client:
            output = self.root
            def _request(inner, method, params, timeout):
                inner.probes = json.loads(params['command'][4])
                return {'exitCode': 0, 'stdout': json.dumps([{**p, 'status': 'error',
                    'error_type': 'PermissionError', 'errno': 13} for p in inner.probes]), 'stderr': ''}
        client = Client()
        with patch('relic_org.scope_evolution.codex_episode.socket.getaddrinfo', return_value=[(None, None, None, None, ('1.1.1.1', 443))]):
            before = network_canary(client)
        with patch('relic_org.scope_evolution.codex_episode.socket.getaddrinfo', side_effect=AssertionError('Postflight must reuse targets')):
            after = network_canary(client, phase='postflight', probes=before['probes'], raise_on_failure=False)
        self.assertTrue(after['passed'])
        self.assertEqual(after['phase'], 'postflight')
        self.assertEqual([(p['kind'], p['host'], p.get('address')) for p in before['probes']],
                         [(p['kind'], p['host'], p.get('address')) for p in after['probes']])
        self.assertTrue((self.root / 'network-canary.json').is_file())
        self.assertTrue((self.root / 'network-canary-postflight.json').is_file())

    def test_credential_canary_executes_both_opens_without_reading_or_exposing_values(self):
        class Handle:
            def __enter__(inner):
                return inner
            def __exit__(inner, *args):
                pass
            def read(inner, *args):
                raise AssertionError('Credential content must never be read, even when open succeeds')
        class Client:
            output = self.root
            def __init__(inner, errors):
                inner.errors, inner.paths = iter(errors), []
            def _request(inner, method, params, timeout):
                inner.params = params
                def opened(path, mode):
                    inner.paths.append((path, mode))
                    error = next(inner.errors)
                    if error is not None:
                        raise error
                    return Handle()
                stdout = io.StringIO()
                with patch.dict(os.environ, {'CODEX_HOME': '/test-only-private-home'}), patch('os.path', posixpath), patch('builtins.open', side_effect=opened), contextlib.redirect_stdout(stdout):
                    exec(params['command'][3], {})
                return {'exitCode': 0, 'stdout': stdout.getvalue(), 'stderr': ''}
        for errors, status in (([PermissionError(1, 'test-only'), PermissionError(13, 'test-only')], 'passed'),
                ([FileNotFoundError(2, 'test-only'), PermissionError(13, 'test-only')], 'passed'),
                ([PermissionError(13, 'test-only'), None], 'failed'),
                ([None, PermissionError(13, 'test-only')], 'failed'),
                ([PermissionError(13, 'test-only'), OSError(5, 'test-only')], 'unknown')):
            with self.subTest(status=status):
                client = Client(errors)
                result = credential_canary(client, phase='postflight', raise_on_failure=False)
                self.assertEqual(result['status'], status)
                self.assertEqual(client.paths, [('/scope-home/auth.json', 'rb'), ('/test-only-private-home/auth.json', 'rb')])
                self.assertEqual(client.params['cwd'], '/product')
                self.assertEqual(client.params['permissionProfile'], 'scope-product')
                self.assertNotIn('turn/start', json.dumps(client.params))
                self.assertNotIn('/test-only-private-home', json.dumps(result))
                self.assertNotIn('test-only', json.dumps(result['probes']))
                self.assertEqual([p['target'] for p in result['probes']], ['literal', 'env'])
                self.assertEqual(result['model_turns_submitted_by_probe'], 0)
        with self.assertRaisesRegex(OrgError, 'credential-open canary failed'):
            credential_canary(Client([PermissionError(13, 'test-only'), None]))

    def test_credential_canary_missing_env_or_malformed_result_is_unknown(self):
        class Client:
            output = self.root
            def _request(inner, method, params, timeout):
                stdout = io.StringIO()
                with patch.dict(os.environ, {}, clear=True), patch('builtins.open', side_effect=PermissionError(13, 'denied')), contextlib.redirect_stdout(stdout):
                    exec(params['command'][3], {})
                return {'exitCode': 0, 'stdout': stdout.getvalue(), 'stderr': ''}
        result = credential_canary(Client(), phase='postflight', raise_on_failure=False)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['probes'][1]['error_type'], 'MissingAbsoluteCodexHome')
        with patch.object(Client, '_request', return_value={'exitCode': 0, 'stdout': '[{"target":"literal","status":"error","errno":13}]'}):
            result = credential_canary(Client(), phase='postflight', raise_on_failure=False)
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['passed'])

    def test_real_postflight_method_combines_network_and_credentials_and_keeps_raw_artifacts(self):
        # Isolated RPC fixtures exercise the production composition, never launch a container/model.
        probes = [{'kind': 'dns', 'host': 'github.com'},
                  {'kind': 'tcp', 'host': 'github.com', 'address': '1.1.1.1', 'port': 443},
                  {'kind': 'tcp', 'host': 'pypi.org', 'address': '8.8.8.8', 'port': 443}]
        transport = object.__new__(DockerStdioTransport)
        transport.container_name = 'test-only-container'
        executor = CodexExecutor(transport, self.root)
        for network_state, credential_state, expected in (
                ('denied', 'denied', 'passed'), ('denied', 'openable', 'failed'),
                ('reachable', 'denied', 'failed'), ('unknown', 'denied', 'unknown'),
                ('denied', 'unknown', 'unknown'), ('reachable', 'unknown', 'failed')):
            with self.subTest(network=network_state, credential=credential_state):
                def request(method, params, timeout):
                    if len(params['command']) == 6:
                        rows = [{**p, 'status': 'error', 'error_type': 'PermissionError', 'errno': 1} for p in probes]
                        if network_state != 'denied':
                            rows[-1].update(status=network_state, errno=None, error_type=None)
                    else:
                        rows = [{'target': target, 'status': 'error', 'error_type': 'PermissionError', 'errno': 13} for target in ('literal', 'env')]
                        if credential_state != 'denied':
                            rows[-1].update(status=credential_state, errno=None, error_type=None)
                    self.assertEqual(method, 'command/exec')
                    self.assertEqual(params['permissionProfile'], 'scope-product')
                    return {'exitCode': 0, 'stdout': json.dumps(rows), 'stderr': ''}
                with patch.object(CodexExecutor, 'facts', new_callable=unittest.mock.PropertyMock,
                        return_value={'isolation_audit': {'network_canary': {'probes': probes}}}), patch.object(executor, '_request', side_effect=request):
                    result = executor.postflight_isolation()
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['passed'], expected == 'passed')
                for key, name in (('network_canary', 'network-canary-postflight.json'),
                                  ('credential_canary', 'credential-canary-postflight.json')):
                    self.assertEqual(json.loads((self.root / name).read_text()), result[key])
                    self.assertEqual(result[key]['container_name'], transport.container_name)
                self.assertEqual(json.loads((self.root / 'postflight-isolation.json').read_text()), result)

    def test_execution_contract_freezes_both_canaries_static_policies_and_current_source(self):
        import hashlib
        import relic_org.scope_evolution.codex_episode as source
        with patch.object(source, 'container_identity', return_value={'image_id': 'test-only-image'}):
            contract = execution_contract()
        self.assertEqual(contract['implementation_sha256']['codex_episode.py'], hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        self.assertEqual(contract['budget'], {'wall_seconds': 1800, 'tool_actions': 80, 'token_usage': 'report_only'})
        self.assertEqual(contract['credential_canary']['probes'], ['literal /scope-home/auth.json', 'env CODEX_HOME/auth.json'])
        self.assertIn('zero reads', contract['credential_canary']['required'])
        self.assertIn('HTTP Request logs are flags', contract['contamination_rules']['external_network'])
        self.assertEqual(contract['postflight_isolation']['artifact'], 'postflight-isolation.json')
        self.assertEqual(contract['error_mapping'], ERROR_MAPPING)

    def test_identity_input_mismatch_auth_failure_and_runner_approval_semantics(self):
        for mode, status in [('wrong_turn', 'submission_unknown'), ('wrong_input', 'submission_unknown'),
                             ('auth_error', 'auth_error'), ('approvals', 'completed')]:
            with self.subTest(mode=mode):
                executor = self.executor(mode=mode)
                result = executor.run([{'type': 'text', 'text': 'TEST'}])
                self.assertEqual(result['status'], status)
                if mode == 'approvals':
                    own = next(m for m in executor.transport.sent if m.get('id') == 'own')
                    foreign = next(m for m in executor.transport.sent if m.get('id') == 'foreign')
                    self.assertEqual(own['result'], {'action': 'accept', 'content': {'ok': True}})
                    self.assertIn('error', foreign)
                else:
                    self.assertFalse(result['scoreable'])
                if mode == 'wrong_input':
                    self.assertNotEqual(result['input_evidence'], 'matching_user_message')


if __name__ == '__main__':
    unittest.main()
