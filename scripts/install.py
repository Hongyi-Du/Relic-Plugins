"""Configure a persistent local source, then use the hosts' plugin CLIs.

No dependencies, downloads, model calls, global hook trust, or database changes.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ('claude', 'codex', 'bridge')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def locate(root, edition=None):
    packaged = root / 'edition.json'
    if packaged.exists():
        selected = read_json(packaged)['edition']
        if edition and edition != selected:
            raise ValueError(f'This archive contains {selected}, not {edition}.')
        return root, selected
    if edition not in EDITIONS:
        raise ValueError('Choose --edition claude, codex, or bridge. See README.md.')
    return root / 'editions' / edition, edition


def configure(edition_root, edition, python=None):
    python = str(Path(python or sys.executable).resolve())
    plugin = edition_root / 'plugins' / ('relic-organization' if edition == 'codex' else 'relic')
    if not (plugin / 'server.py').is_file():
        raise ValueError(f'Incomplete package: {plugin / "server.py"}')
    if edition in ('codex', 'bridge'):
        mcp_file = plugin / ('.mcp.json' if edition == 'codex' else 'codex.mcp.json')
        data = read_json(mcp_file)
        for server in data['mcpServers'].values():
            server['command'] = python
            server['args'] = ['-X', 'utf8', str(plugin / 'server.py')]
        write_json(mcp_file, data)
    if edition in ('claude', 'bridge'):
        manifest = plugin / '.claude-plugin/plugin.json'
        data = read_json(manifest)
        data['mcpServers'] = {'org': {'command': python,
            'args': ['-X', 'utf8', '${CLAUDE_PLUGIN_ROOT}/server.py']}}
        write_json(manifest, data)
    # Shell command hooks need a real command, not an unsupported separate args list.
    # Use the installing interpreter so macOS does not need a `python` alias.
    hook_file = 'hook.py' if edition == 'codex' else 'relic_hook.py'
    interpreter = '"' + Path(python).as_posix() + '"' if os.name == 'nt' else shlex.quote(python)
    code = ("import os,runpy;runpy.run_path(os.path.join("
            "os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ['PLUGIN_ROOT'],"
            f"'hooks','{hook_file}'),run_name='__main__')")
    command = interpreter + ' -X utf8 -c "' + code + '"'
    for path in (plugin / 'hooks').glob('*.json'):
        data = read_json(path)
        for groups in data.get('hooks', {}).values():
            for group in groups:
                for hook in group.get('hooks', []):
                    if hook.get('type') == 'command':
                        hook['command'] = command
                        hook.pop('args', None)
        write_json(path, data)
    return plugin


def cli(name):
    found = os.environ.get('CODEX_CLI_PATH') if name == 'codex' else None
    found = found or shutil.which(name)
    if found:
        return found
    if os.name == 'nt':
        if name == 'codex':
            bundled = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI/Codex/bin'
            candidates = sorted(bundled.glob('**/codex.exe'), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                return str(candidates[0])
        else:
            candidate = Path.home() / '.local/bin/claude.exe'
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError(f'{name} CLI not found. Install it, sign in, and ensure it is on PATH.')


def run(command):
    print('> ' + subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edition', choices=EDITIONS)
    parser.add_argument('--host', choices=('claude', 'codex', 'both'),
                        help='Bridge host selection; default is both.')
    parser.add_argument('--configure-only', action='store_true',
                        help='Prepare this extracted directory without registering or installing it.')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or newer is required.')
    try:
        edition_root, edition = locate(ROOT, args.edition)
        target = args.host or ('both' if edition == 'bridge' else edition)
        if edition != 'bridge' and target != edition:
            raise ValueError('--host only selects hosts for the Bridge edition.')
        hosts = ('claude', 'codex') if target == 'both' else (target,)
        executables = {} if args.configure_only else {name: cli(name) for name in hosts}
        plugin = configure(edition_root, edition)
        print(f'Configured Relic {edition}: {plugin}')
        if args.configure_only:
            print('Configuration only. No plugin was installed and no host settings were changed.')
            return 0
        selector = ('relic-organization' if edition == 'codex' else 'relic') + '@relic-' + edition
        for host in hosts:
            run([executables[host], 'plugin', 'marketplace', 'add', str(edition_root)])
            run([executables[host], 'plugin', 'add' if host == 'codex' else 'install', selector])
        print('Installed. Keep this source directory in place. Restart the host or open a new session.')
        print('Review and trust plugin hooks in the host settings before relying on protocol enforcement.')
        print('Enable only one Relic edition in a given host. Existing plugins were not disabled automatically.')
        if sys.platform == 'darwin':
            print('macOS beta: Bridge desktop auto-wake/ChatGPT chat delivery is unavailable; use CLI peers or inbox.')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Installation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
