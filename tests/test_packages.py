import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_the_package_for_each_platform_extracts_and_configures_without_host_installation(self):
        launch_files = [ROOT/'plugins/relic'/name for name in
                        ('codex.mcp.json', '.claude-plugin/plugin.json', 'hooks/hooks.json', 'hooks/claude-extra.json')]
        originals = {path: path.read_bytes() for path in launch_files}
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'archives'
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/package.py'),'--output',str(target),
                            '--macos-format', 'both'],
                           check=True,capture_output=True)
            self.assertEqual({path: path.read_bytes() for path in launch_files}, originals)
            manifest=json.loads((target/'release-manifest.json').read_text())
            self.assertEqual(sorted(a['platform'] for a in manifest['assets']),['macos','macos','windows'])
            sums=(target/'SHA256SUMS.txt').read_bytes()
            self.assertNotIn(b'\r',sums)  # `sha256sum -c` reads a CR as part of the file name
            for line in sums.decode('ascii').splitlines():
                digest,name=line.split('  ')
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest)
            plugin_sources = []
            for item in manifest['assets']:
                with self.subTest(asset=item['name']):
                    if item['platform'] == 'macos':
                        self.assertEqual(item['supported_architectures'], ['arm64'])
                    self.assertTrue(item['name'].startswith('relic-'+item['platform']+'-v'))
                    archive=target/item['name']
                    dest=Path(temp)/'Unpacked 空格'/item['name']
                    dest.mkdir(parents=True)
                    if archive.suffix=='.zip':
                        with zipfile.ZipFile(archive) as package:
                            self.assertTrue(all('..' not in Path(n).parts for n in package.namelist()))
                            launcher=next(m for m in package.infolist() if m.filename.endswith('/install.command'))
                            self.assertEqual(launcher.create_system, 3)
                            self.assertEqual((launcher.external_attr >> 16) & 0o777, 0o755)
                            package.extractall(dest)
                    else:
                        with tarfile.open(archive) as package:
                            self.assertTrue(all(not m.issym() and not m.islnk() for m in package.getmembers()))
                            self.assertTrue(all('..' not in Path(m.name).parts for m in package.getmembers()))
                            launcher=next(m for m in package.getmembers() if m.name.endswith('/install.command'))
                            self.assertEqual(launcher.mode,0o755)
                            package.extractall(dest,filter='data')
                    extracted=next(dest.iterdir())
                    plugin=extracted/'plugins/relic'
                    codex=json.loads((plugin/'codex.mcp.json').read_text(encoding='utf-8'))
                    for server in codex['mcpServers'].values():
                        self.assertEqual(server['command'], 'python3')
                        self.assertEqual(server['args'], ['-X', 'utf8', './server.py'])
                        self.assertNotIn('env', server)
                    claude=json.loads((plugin/'.claude-plugin/plugin.json').read_text(encoding='utf-8'))
                    interpreter = 'python3' if item['platform'] == 'macos' else 'python'
                    self.assertEqual(claude['mcpServers']['org'],
                                     {'command': interpreter, 'args': ['-X', 'utf8', '${CLAUDE_PLUGIN_ROOT}/server.py']})
                    for hooks_file in (plugin/'hooks').glob('*.json'):
                        hooks=json.loads(hooks_file.read_text(encoding='utf-8'))
                        for groups in hooks.get('hooks', {}).values():
                            for group in groups:
                                for hook in group.get('hooks', []):
                                    if hook.get('type') == 'command':
                                        self.assertTrue(hook['command'].startswith(interpreter + ' -X utf8 -c '))
                                        self.assertNotIn(str(ROOT), hook['command'])
                                        self.assertNotIn('args', hook)
                    platform_templates = {'.claude-plugin/plugin.json', 'hooks/hooks.json', 'hooks/claude-extra.json',
                                          'hooks/codex-hooks.json'}
                    plugin_sources.append({p.relative_to(plugin).as_posix(): p.read_bytes()
                                           for p in plugin.rglob('*') if p.is_file()
                                           and p.relative_to(plugin).as_posix() not in platform_templates})
                    command=[sys.executable,'-X','utf8',str(extracted/'scripts/install.py'),'--configure-only']
                    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=20)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('No plugin was installed',result.stdout)
                    codex=json.loads((plugin/'codex.mcp.json').read_text(encoding='utf-8'))
                    for server in codex['mcpServers'].values():
                        self.assertEqual(server['command'], str(Path(sys.executable).resolve()))
                        self.assertEqual(server['args'], ['-X', 'utf8', str((plugin/'server.py').resolve())])
                    self.assertTrue((extracted/'scripts/open_app.py').is_file())
                    self.assertEqual((extracted/'scripts/macos_app.py').is_file(), item['platform'] == 'macos')
                    readme = (extracted/'README.md').read_text(encoding='utf-8')
                    self.assertIn(manifest['release'], readme)
                    self.assertIn('activity.paths', readme)
                    self.assertNotIn('maintained separately', readme)
                    if item['platform'] == 'macos':
                        self.assertIn('Finder', readme)
                        self.assertIn('HaochenGu', readme)
                    self.assertTrue((extracted/'plugins/relic/app/static/index.html').is_file())
                    self.assertTrue((extracted/'.claude-plugin/marketplace.json').is_file())
                    self.assertFalse((extracted/'scripts/open_panel.py').exists())
                    self.assertNotIn(b'\r', (extracted/'install.command').read_bytes())
            self.assertEqual(plugin_sources[0], plugin_sources[1])
            self.assertEqual(plugin_sources[0], plugin_sources[2])


if __name__=='__main__':
    unittest.main()
