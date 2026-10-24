import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_each_edition_configures_a_unicode_path_and_starts_mcp(self):
        for edition in installer.EDITIONS:
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as temp:
                dest = Path(temp) / 'Relic 空格 release'
                shutil.copytree(ROOT / 'editions' / edition, dest)
                plugin = installer.configure(dest, edition)
                if edition in ('codex', 'bridge'):
                    data = installer.read_json(plugin / ('.mcp.json' if edition == 'codex' else 'codex.mcp.json'))
                    server = next(iter(data['mcpServers'].values()))
                    self.assertEqual(Path(server['command']).resolve(), Path(sys.executable).resolve())
                    self.assertEqual(server['args'][2], str(plugin / 'server.py'))
                env = dict(__import__('os').environ, RELIC_HOME=str(Path(temp)/'bridge-data'),
                           RELIC_ORG_HOME=str(Path(temp)/'codex-data'),
                           CODEX_HOME=str(Path(temp)/'codex-home'), CLAUDE_CONFIG_DIR=str(Path(temp)/'claude-home'))
                payload = '\n'.join(json.dumps(x) for x in [
                    {'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                    {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]) + '\n'
                proc = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(plugin / 'server.py')],
                                      input=payload, capture_output=True, text=True, encoding='utf-8',
                                      env=env, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                replies = [json.loads(line) for line in proc.stdout.splitlines()]
                self.assertGreater(len(next(x for x in replies if x.get('id') == 2)['result']['tools']), 0)
                hooks = installer.read_json(plugin/'hooks/hooks.json')['hooks']
                for groups in hooks.values():
                    for group in groups:
                        for hook in group['hooks']:
                            self.assertNotIn('args', hook)
                            self.assertIn(Path(sys.executable).resolve().as_posix(), hook['command'])
                hook_env = dict(env, PLUGIN_ROOT=str(plugin), CLAUDE_PLUGIN_ROOT=str(plugin))
                event = json.dumps({'hook_event_name':'SessionStart','session_id':'release-fixture',
                                    'cwd':str(Path(temp))})
                hook_run = subprocess.run(hooks['SessionStart'][0]['hooks'][0]['command'],
                    shell=True,input=event,capture_output=True,text=True,encoding='utf-8',
                    env=hook_env,timeout=20)
                self.assertEqual(hook_run.returncode,0,hook_run.stderr)

    def test_archive_cannot_install_another_edition(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'edition.json').write_text('{"edition":"bridge"}')
            self.assertEqual(installer.locate(root), (root, 'bridge'))
            with self.assertRaises(ValueError):
                installer.locate(root, 'claude')

    def test_repository_requires_explicit_edition(self):
        with self.assertRaises(ValueError):
            installer.locate(ROOT)


if __name__ == '__main__':
    unittest.main()
