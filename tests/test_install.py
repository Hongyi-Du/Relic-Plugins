import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def copy_release(dest):
    for top in ('.claude-plugin', '.agents', 'plugins', 'scripts'):
        shutil.copytree(ROOT / top, dest / top, ignore=shutil.ignore_patterns('__pycache__'))


class InstallerTests(unittest.TestCase):
    def test_unsupported_runtime_stops_before_configuring_or_installing(self):
        with mock.patch.object(installer.platform_support, 'require_supported_python',
                               side_effect=RuntimeError('arm64 Python required')), \
                mock.patch.object(installer, 'configure') as configure, mock.patch.object(installer, 'run') as run:
            self.assertEqual(installer.main(['--host', 'none']), 1)
            configure.assert_not_called()
            run.assert_not_called()

    def test_configures_a_unicode_path_and_starts_the_mcp_server_and_hooks(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'Relic 空格 release'
            copy_release(dest)
            plugin = installer.configure(dest)
            data = installer.read_json(plugin / 'codex.mcp.json')
            server = next(iter(data['mcpServers'].values()))
            self.assertEqual(Path(server['command']).resolve(), Path(sys.executable).resolve())
            self.assertEqual(server['args'][2], str(plugin / 'server.py'))
            manifest = installer.read_json(plugin / '.claude-plugin/plugin.json')
            self.assertEqual(Path(manifest['mcpServers']['org']['command']).resolve(), Path(sys.executable).resolve())
            env = dict(os.environ, RELIC_HOME=str(Path(temp) / 'relic-data'), CODEX_HOME=str(Path(temp) / 'codex-home'),
                       CLAUDE_CONFIG_DIR=str(Path(temp) / 'claude-home'))
            payload = '\n'.join(json.dumps(x) for x in [
                {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}]) + '\n'
            proc = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(plugin / 'server.py')], input=payload,
                                  capture_output=True, text=True, encoding='utf-8', env=env, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            replies = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertGreater(len(next(x for x in replies if x.get('id') == 2)['result']['tools']), 0)
            hooks = installer.read_json(plugin / 'hooks/hooks.json')['hooks']
            for groups in hooks.values():
                for group in groups:
                    for hook in group['hooks']:
                        self.assertNotIn('args', hook)
                        self.assertIn(Path(sys.executable).resolve().as_posix(), hook['command'])
            hook_env = dict(env, PLUGIN_ROOT=str(plugin), CLAUDE_PLUGIN_ROOT=str(plugin))
            event = json.dumps({'hook_event_name': 'SessionStart', 'session_id': 'release-fixture', 'cwd': str(Path(temp))})
            hook_run = subprocess.run(hooks['SessionStart'][0]['hooks'][0]['command'], shell=True, input=event,
                                      capture_output=True, text=True, encoding='utf-8', env=hook_env, timeout=20,
                                      creationflags=installer.platform_support.creation_flags())
            self.assertEqual(hook_run.returncode, 0, hook_run.stderr)
            codex_manifest = installer.read_json(plugin / '.codex-plugin/plugin.json')
            codex_hooks = installer.read_json(plugin / codex_manifest['hooks'])['hooks']
            for name in ('SessionStart', 'UserPromptSubmit', 'SubagentStart', 'PostToolUse'):
                self.assertEqual(codex_hooks[name][0]['hooks'][0]['additionalContextLimit'], 0)
            if os.name == 'nt':
                # CI-only real PowerShell check: stdin reaches the hook, with a
                # private store and no seat, member turn, App, or native window.
                command = codex_hooks['PostToolUse'][0]['hooks'][0]['commandWindows']
                self.assertTrue(command.startswith("& '"))
                event = json.dumps({'hook_event_name': 'PostToolUse', 'session_id': 'release-fixture',
                                    'tool_name': 'Read', 'tool_input': {}})
                result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                        input=event, capture_output=True, text=True, encoding='utf-8', env=hook_env,
                                        timeout=20, creationflags=installer.platform_support.creation_flags())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {})

    def test_installs_into_the_hosts_it_finds_and_turns_off_earlier_claude_editions(self):
        commands = []
        found = {'claude': 'claude.exe', 'codex': None}
        with mock.patch.object(installer, 'configure', lambda root: ROOT / 'plugins' / 'relic'), \
                mock.patch.object(installer, 'cli', lambda name: found[name]), \
                mock.patch.object(installer, 'run', lambda command, check=True: commands.append(command) or 0), \
                mock.patch.object(installer, 'shortcut', lambda python: None):
            self.assertEqual(installer.main(['--no-shortcut']), 0)  # auto: Codex is not installed, Claude Code is
            self.assertIn(['claude.exe', 'plugin', 'disable', 'relic@relic-claude'], commands)
            add = commands.index(['claude.exe', 'plugin', 'marketplace', 'add', str(installer.ROOT)])
            # an earlier registration of the marketplace (another folder) goes first, then this folder's plugin
            self.assertEqual(commands[add - 1], ['claude.exe', 'plugin', 'marketplace', 'remove', 'relic-bridge'])
            self.assertEqual(commands[add + 1], ['claude.exe', 'plugin', 'install', 'relic@relic-bridge'])
            self.assertFalse(any('codex' in c[0] for c in commands))
            self.assertEqual(installer.main(['--host', 'codex']), 1)  # asked for a host that is not there

    def test_the_relic_app_alone_needs_no_host(self):
        with mock.patch.object(installer, 'configure', lambda root: ROOT / 'plugins' / 'relic'), \
                mock.patch.object(installer, 'cli', lambda name: (_ for _ in ()).throw(AssertionError('no host'))), \
                mock.patch.object(installer, 'shortcut', lambda python: None):
            self.assertEqual(installer.main(['--host', 'none', '--no-shortcut']), 0)


if __name__ == '__main__':
    unittest.main()
