"""Model-path evidence fixtures; no network, credential access, or inference."""
import copy
import json
import unittest

from relic_org.scope_evolution.calibration_probe import (
    SCRIPT_NAME, PROBE_SCHEMA, is_probe_command, model_isolation_evidence, probe_source)


PROBES = [{'kind': 'dns', 'host': 'github.com'},
          {'kind': 'tcp', 'host': 'github.com', 'address': '140.82.112.3', 'port': 443},
          {'kind': 'tcp', 'host': 'pypi.org', 'address': '151.101.0.223', 'port': 443}]


class ModelPathProbeTests(unittest.TestCase):
    def events(self, *, command=None, result=None, exit_code=0):
        result = result or {'schema': PROBE_SCHEMA,
            'tcp': [{**{k: p[k] for k in ('host', 'address', 'port')}, 'blocked': True, 'error_code': 1}
                    for p in PROBES[1:]],
            'credentials': [{'label': 'env', 'path': '/scope-home/auth.json', 'blocked': True,
                             'error_code': 2, 'environment_variable_present': True},
                            {'label': 'literal', 'path': '/scope-home/auth.json', 'blocked': True, 'error_code': 2}]}
        return [{'direction': 'in', 'message': {'method': 'item/completed', 'params': {
            'threadId': 'test-only-thread', 'turnId': 'test-only-turn', 'item': {
                'id': 'test-only-command', 'type': 'commandExecution', 'status': 'completed',
                'command': command or 'CODEX_HOME=/scope-home python ' + SCRIPT_NAME,
                'exitCode': exit_code, 'aggregatedOutput': json.dumps(result)}}}}]

    def proof(self, events, **kwargs):
        return model_isolation_evidence(events, thread_id='test-only-thread', turn_id='test-only-turn',
            probes=PROBES, script_unchanged=kwargs.get('script_unchanged', True))

    def test_exact_actual_tool_probe_passes_and_supplied_script_only_opens_no_content(self):
        self.assertTrue(self.proof(self.events())['passed'])
        self.assertTrue(is_probe_command('/bin/bash -lc "CODEX_HOME=/scope-home python calibration_sandbox_check.py"'))
        source = probe_source(PROBES)
        compile(source, 'test-only-generated-probe', 'exec')
        self.assertIn('os.open', source)
        self.assertNotIn('read_bytes', source)
        self.assertNotIn('os.read', source)

    def test_echo_inline_masked_and_extra_commands_do_not_prove_execution(self):
        for command in ('echo python ' + SCRIPT_NAME,
                        'echo python ' + SCRIPT_NAME + '; echo matching-json',
                        'python -c "print(1)" ' + SCRIPT_NAME,
                        'python ' + SCRIPT_NAME + ' || true',
                        'python ' + SCRIPT_NAME + '; echo matching-json',
                        'python ' + SCRIPT_NAME + ' | cat'):
            with self.subTest(command=command):
                self.assertFalse(is_probe_command(command))
                self.assertFalse(self.proof(self.events(command=command))['passed'])

    def test_timeout_wrong_target_readable_home_or_wrong_context_never_pass(self):
        original = self.events()
        for mutation in ('timeout', 'target', 'credential', 'missing_env', 'thread', 'turn'):
            events = copy.deepcopy(original)
            params = events[0]['message']['params']
            value = json.loads(params['item']['aggregatedOutput'])
            if mutation == 'timeout': value['tcp'][0]['error_code'] = None
            if mutation == 'target': value['tcp'][0]['address'] = '1.1.1.1'
            if mutation == 'credential': value['credentials'][0]['blocked'] = False
            if mutation == 'missing_env': value['credentials'][0]['environment_variable_present'] = False
            if mutation == 'thread': params['threadId'] = 'test-only-other'
            if mutation == 'turn': params['turnId'] = 'test-only-other'
            params['item']['aggregatedOutput'] = json.dumps(value)
            with self.subTest(mutation=mutation): self.assertFalse(self.proof(events)['passed'])

    def test_web_search_or_changed_probe_invalidates_a_successful_record(self):
        events = self.events()
        self.assertFalse(self.proof(events, script_unchanged=False)['passed'])
        events.append({'direction': 'in', 'message': {'method': 'item/started', 'params': {
            'threadId': 'test-only-thread', 'turnId': 'test-only-turn',
            'item': {'id': 'test-only-web', 'type': 'webSearch'}}}})
        self.assertFalse(self.proof(events)['passed'])
