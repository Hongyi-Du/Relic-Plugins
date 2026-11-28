"""The native harness registrations use the existing App, MCP identity and lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import harness, hub, views
from relic_core.store import Store

FAKE = ROOT / 'tests/fake_acp_agent.py'
NATIVE = ('kimi-code', 'deepseek-harness')


def wait_for(check):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.03)
    raise AssertionError('ACP fixture did not finish')


class NativeIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {
            'RELIC_HOME': str(self.home/'relic'), 'RELIC_LANG': 'en-US',
            'CLAUDE_CONFIG_DIR': str(self.home/'claude'), 'CODEX_HOME': str(self.home/'codex'),
            'FAKE_ACP_LOG': str(self.home/'rpc.jsonl')})
        self.env.start()
        self.store = Store()
        self.oid = self.store.found('Native fixture', 'Check existing App integration')['id']
        self.app = hub.Hub(store=self.store)

    def tearDown(self):
        for member in NATIVE:
            self.app.stop(self.oid, member)
        self.env.stop()
        self.temp.cleanup()

    def test_native_registrations_get_distinct_real_mcp_seat_identities(self):
        for index, kind in enumerate(NATIVE):
            with self.subTest(harness=kind):
                sid = 'native-fixture-' + str(index)
                actor = harness.actor_for(kind, sid)
                self.assertEqual(actor, kind + ':' + sid)
                self.store.add_seat(self.oid, kind, '', {'harness': kind, 'surface': 'acp', 'seat_token': kind})
                self.store.join(actor, self.oid, kind)
                servers, meta = harness.relic_for(kind, self.oid, kind, kind)
                self.assertIsNone(meta)
                self.assertFalse(harness.has_hooks(kind))
                self.assertEqual(harness.default_mode(kind), '')
                self.assertEqual(len(servers), 1)
                server = servers[0]
                self.assertEqual(server['name'], 'relic_org')
                env = {item['name']: item['value'] for item in server['env']}
                requests = [
                    {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'status', 'arguments': {}}},
                ]
                proc = subprocess.run([server['command'], *server['args']],
                                      input=''.join(json.dumps(item)+'\n' for item in requests),
                                      text=True, encoding='utf-8', capture_output=True, env=env, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                reply = next(json.loads(line) for line in proc.stdout.splitlines() if json.loads(line).get('id') == 2)
                self.assertFalse(reply['result'].get('isError'), reply['result'])
                status = json.loads(reply['result']['content'][0]['text'].rsplit('\n\n', 1)[-1])
                self.assertEqual(status['member'], kind)
                self.assertEqual(self.store.get(self.oid)['members'][kind]['harness'], kind)

    def test_native_members_use_existing_resume_cancel_and_permission_workflow(self):
        for kind in NATIVE:
            with self.subTest(harness=kind):
                spec = dict(harness.HARNESSES[kind], command=lambda: sys.executable,
                            args=['-X', 'utf8', str(FAKE)])
                spec.pop('launch', None)
                with mock.patch.dict(harness.HARNESSES, {kind: spec}):
                    folder = self.home/kind
                    self.store.add_seat(self.oid, kind, '', {'harness': kind, 'surface': 'acp', 'folder': str(folder)})
                    live = self.app.ensure(self.oid, kind)
                    sid = live.session_id
                    old_token = self.store.get(self.oid)['members'][kind]['config']['seat_token']
                    self.app.prompt(self.oid, kind, 'needs permission', {'kind': 'human'})
                    wait_for(lambda: bool(self.app.permissions(self.oid)))
                    self.app.decide(self.app.permissions(self.oid)[0]['id'], 'reject')
                    wait_for(lambda: live.turn is None)
                    self.assertIn('permission: reject', ''.join(item.get('text', '') for item in live.items))
                    self.app.prompt(self.oid, kind, 'slow', {'kind': 'human'})
                    live.agent.cancel(sid)
                    wait_for(lambda: live.turn is None)
                    self.app.stop(self.oid, kind)
                    live = self.app.ensure(self.oid, kind)
                    self.assertEqual(live.session_id, sid)
                    token = self.store.get(self.oid)['members'][kind]['config']['seat_token']
                    self.assertNotEqual(old_token, token)
                    rows = [json.loads(line) for line in (self.home/'rpc.jsonl').read_text(encoding='utf-8').splitlines()]
                    restored = next(row for row in reversed(rows) if row['method'] == 'session/resume')
                    self.assertEqual(restored['params']['sessionId'], sid)
                    server = restored['params']['mcpServers'][0]
                    self.assertEqual({item['name']: item['value'] for item in server['env']}['RELIC_SEAT_TOKEN'], token)
                    self.app.prompt(self.oid, kind, 'after resume', {'kind': 'human'})
                    wait_for(lambda: live.turn is None)
                    self.app.stop(self.oid, kind)

    def test_native_catalog_and_model_controls_do_not_require_npm_or_other_vendor_models(self):
        with mock.patch.object(harness.native, 'find_kimi', return_value=sys.executable), \
             mock.patch.object(harness.native, 'find_deepseek', return_value=sys.executable), \
             mock.patch.object(harness.native, 'deepseek_launch', return_value=([sys.executable], {})), \
             mock.patch.object(harness, 'node', return_value=None):
            rows = {item['id']: item for item in harness.catalog()}
        for kind in NATIVE:
            self.assertTrue(rows[kind]['available'])
            self.assertEqual(rows[kind]['install'], '')
            self.assertEqual(rows[kind]['adapter'], '')
            with mock.patch.object(harness.shutil, 'which') as which:
                self.assertEqual(harness.install(kind, lambda text: None), 1)
                which.assert_not_called()
            harness.remember(kind, ['native-model'], ['max'])
            info = views.model_info(kind, 'acp', {}, None, False, 'en-US')
            self.assertEqual((info['models'], info['efforts']), (['native-model'], ['max']))
            self.assertTrue(info['editable'])
        self.assertNotIn('kimi', {item['id'] for item in harness.LATER})

    def test_bad_explicit_paths_are_reported_per_harness(self):
        with mock.patch.dict(os.environ, {'RELIC_KIMI_PATH': str(self.home/'missing-kimi'),
                                          'RELIC_DSH_PATH': str(self.home/'missing-dsh')}):
            rows = {item['id']: item for item in harness.catalog()}
        for kind in NATIVE:
            self.assertFalse(rows[kind]['available'])
            self.assertIn('existing executable', rows[kind]['problem'])


if __name__ == '__main__':
    unittest.main()
