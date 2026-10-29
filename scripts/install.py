"""Install Relic: configure this folder, add the Relic plugin to Claude Code and Codex where they are installed, and
make a shortcut that opens the Relic App.

One product: the Relic App runs members on Claude Code and Codex and brings Relic into their sessions itself; the
plugin added to each host lets your own Claude Code and Codex sessions join organizations too. No dependencies,
downloads, model calls, global hook trust or database changes.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'plugins' / 'relic'))
from relic_core import platform_support  # noqa: E402
MARKETPLACE = 'relic-bridge'  # keeps its earlier name, so Bridge installs upgrade in place
SELECTOR = 'relic@' + MARKETPLACE
# Earlier Relic editions that register the same Claude Code tool names: switched off so tools and hooks run once.
CLAUDE_EARLIER = ('relic@relic-claude', 'relic@relic-local')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def plugin_dir(root=ROOT):
    plugin = root / 'plugins' / 'relic'
    if not (plugin / 'server.py').is_file():
        raise ValueError(f'Incomplete package: {plugin / "server.py"}')
    return plugin


def configure(root=ROOT, python=None):
    """Point the plugin's MCP server and hooks at this Python and this folder."""
    python = str(Path(python or sys.executable).resolve())
    plugin = plugin_dir(root)
    data = read_json(plugin / 'codex.mcp.json')
    for server in data['mcpServers'].values():
        server['command'] = python
        server['args'] = ['-X', 'utf8', str(plugin / 'server.py')]
    write_json(plugin / 'codex.mcp.json', data)
    manifest = plugin / '.claude-plugin/plugin.json'
    data = read_json(manifest)
    data['mcpServers'] = {'org': {'command': python, 'args': ['-X', 'utf8', '${CLAUDE_PLUGIN_ROOT}/server.py']}}
    write_json(manifest, data)
    # Shell command hooks need a real command, not an unsupported separate args list.
    # Use the installing interpreter so macOS does not need a `python` alias.
    interpreter = '"' + Path(python).as_posix() + '"' if os.name == 'nt' else shlex.quote(python)
    code = ("import os,runpy;runpy.run_path(os.path.join("
            "os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ['PLUGIN_ROOT'],"
            "'hooks','relic_hook.py'),run_name='__main__')")
    command = interpreter + ' -X utf8 -c "' + code + '"'
    for path in (plugin / 'hooks').glob('*.json'):
        data = read_json(path)
        for groups in data.get('hooks', {}).values():
            for group in groups:
                for hook in group.get('hooks', []):
                    if hook.get('type') == 'command':
                        hook['command'] = command
                        hook.pop('args', None)
                        # Codex executes Windows hooks as PowerShell commands.
                        # A quoted executable without & is a string expression,
                        # so the old command failed before Python received stdin.
                        if path.name == 'codex-hooks.json' and os.name == 'nt':
                            quote = lambda value: "'" + value.replace("'", "''") + "'"
                            hook['commandWindows'] = '& ' + quote(Path(python).as_posix()) + ' -X utf8 -c ' + quote(code)
                        else:
                            hook.pop('commandWindows', None)
        write_json(path, data)
    return plugin


def cli(name):
    """The host's CLI, or None when it is not installed."""
    return platform_support.find_executable(name)


def run(command, check=True):
    print('> ' + subprocess.list2cmdline(command), flush=True)
    env = platform_support.runtime_env(executables=[platform_support.find_executable('node'), command[0]])
    return subprocess.run(command, check=check, env=env, creationflags=platform_support.creation_flags()).returncode


def shortcut(python):
    """A desktop shortcut named Relic that opens the Relic App (Windows)."""
    pythonw = Path(python).with_name('pythonw.exe')
    target = pythonw if pythonw.is_file() else Path(python)
    script = ROOT / 'plugins' / 'relic' / 'scripts' / 'relic_app.py'
    ps = ("$s=New-Object -ComObject WScript.Shell;"
          "$d=[Environment]::GetFolderPath('Desktop');"
          "$l=$s.CreateShortcut((Join-Path $d 'Relic.lnk'));"
          "$l.TargetPath=$env:RELIC_LINK_TARGET;$l.Arguments=$env:RELIC_LINK_ARGS;"
          "$l.WorkingDirectory=$env:RELIC_LINK_DIR;$l.Description='Relic: organizations of Claude Code and Codex members';"
          "$l.Save()")
    env = dict(os.environ, RELIC_LINK_TARGET=str(target), RELIC_LINK_ARGS='-X utf8 "%s"' % script,
               RELIC_LINK_DIR=str(ROOT / 'plugins' / 'relic'))
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], check=True, env=env,
                   stdout=subprocess.DEVNULL, creationflags=platform_support.creation_flags())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('auto', 'claude', 'codex', 'both', 'none'), default='auto',
                        help='Which hosts get the plugin: every installed one (auto, the default), one, both, or none '
                             '(the Relic App alone).')
    parser.add_argument('--configure-only', action='store_true',
                        help='Prepare this extracted folder without changing any host or making a shortcut.')
    parser.add_argument('--no-shortcut', action='store_true', help='Do not make the Relic shortcut on the desktop.')
    parser.add_argument('--remove-launcher', action='store_true',
                        help='Remove only the managed macOS Finder launcher; keep plugins and all organization data.')
    parser.add_argument('--open', action='store_true', help='Open the Relic App when the installation is done.')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or newer is required.')
    try:
        platform_support.require_supported_python()
        if args.remove_launcher:
            if sys.platform != 'darwin':
                raise RuntimeError('--remove-launcher applies to the macOS Finder launcher.')
            import macos_app
            print('Removed Finder launcher.' if macos_app.remove() else 'No Finder launcher was installed.')
            return 0
        plugin = configure(ROOT)
        print(f'Configured Relic: {plugin}')
        if args.configure_only:
            print('Configuration only. No plugin was installed and no host settings were changed.')
            return 0
        wanted = {'auto': ('claude', 'codex'), 'both': ('claude', 'codex'), 'none': ()}.get(args.host, (args.host,))
        found = {name: cli(name) for name in wanted}
        missing = [name for name, path in found.items() if not path]
        if missing and args.host not in ('auto',):
            raise RuntimeError(f'{" and ".join(missing)} CLI not found. Install it, sign in, and ensure it is on PATH.')
        installed = []
        for host, exe in found.items():
            if not exe:
                continue
            if host == 'claude':
                for earlier in CLAUDE_EARLIER:  # best effort: absent ones only print an error
                    run([exe, 'plugin', 'disable', earlier], check=False)
            # An earlier install registered the marketplace at its own folder: drop that registration (absent on a
            # first install, which only prints an error) so this folder is the one registered.
            run([exe, 'plugin', 'marketplace', 'remove', MARKETPLACE], check=False)
            run([exe, 'plugin', 'marketplace', 'add', str(ROOT)])
            run([exe, 'plugin', 'add' if host == 'codex' else 'install', SELECTOR])
            installed.append({'claude': 'Claude Code', 'codex': 'Codex'}[host])
        if os.name == 'nt' and not args.no_shortcut:
            try:
                shortcut(sys.executable)
                print('Desktop shortcut: Relic (opens the Relic App).')
            except (OSError, subprocess.CalledProcessError) as error:
                print(f'The desktop shortcut was not made ({error}). Open the App with scripts/open_app.py.')
        elif sys.platform == 'darwin' and not args.no_shortcut:
            print('Open the native Relic.app from Finder. Install the SwiftUI package if it is not present.')
        print()
        print('Installed Relic ' + read_json(plugin / '.claude-plugin/plugin.json')['version'] + '.'
              + (' Plugin added to: ' + ', '.join(installed) + '.' if installed else ' No host CLI was found: the plugin '
                 'was not added to Claude Code or Codex. The Relic App still runs members once either is installed.'))
        print('Keep this folder in place. Open the Relic App: ' + ('python3' if sys.platform == 'darwin' else 'python')
              + ' -X utf8 scripts/open_app.py'
              + (' (or the Relic shortcut on the desktop)' if os.name == 'nt' and not args.no_shortcut else '') + '.')
        print('Members you add in the App get Relic from the App. For your own Claude Code and Codex sessions, restart '
              'the host and review and trust the plugin hooks in its settings before relying on protocol enforcement.')
        print('The earlier Relic Codex edition (relic-organization) keeps its own tools and data; remove it in Codex '
              'if you no longer use it.')
        if sys.platform == 'darwin':
            print('macOS: desktop delivery requires a verified, authorized host connection. '
                  'Check Settings > Harness connections or scripts/doctor.py --probe-desktop. '
                  'CLI, App-managed members and manual inbox work independently.')
        if args.open:
            subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / 'open_app.py')],
                             creationflags=platform_support.creation_flags())
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Installation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
