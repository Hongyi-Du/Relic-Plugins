"""Copy the Relic plugin from the folder it is developed in into plugins/relic for a release.

    python scripts/sync_plugin.py <upstream plugin folder> [--suffix=-beta.1]

Write the suffix with "=": argparse reads a separate "-beta.1" as another option.

The copy leaves out the maintainer's working notes and caches, resets the machine paths that the maintainer's own
installer writes (codex.mcp.json, the Claude Code manifest's interpreter), and adds the release suffix to the version
in both manifests and relic_core. Not shipped in packages; package.py checks what this produces.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'plugins' / 'relic'
LEFT_OUT = {'README.md', 'GUI_TRANSPORT_CHECKPOINT.md'}  # the maintainer's notes at the plugin's top level
SKIP = {'__pycache__', '.pytest_cache', '.native-tmp', '.native-fixtures', '.git'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--suffix', default='-beta.1')
    args = parser.parse_args(argv)
    source = args.upstream.resolve()
    if not (source / 'server.py').is_file() or not (source / 'app').is_dir():
        parser.error('%s is not the Relic plugin folder' % source)
    if DEST.exists():
        shutil.rmtree(DEST)
    count = 0
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if not path.is_file() or set(rel.parts) & SKIP or path.suffix in ('.pyc', '.pyo'):
            continue
        if len(rel.parts) == 1 and rel.name in LEFT_OUT:
            continue
        target = DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    mcp = read_json(DEST / 'codex.mcp.json')
    for server in mcp['mcpServers'].values():
        server['command'] = 'python3'
        server['args'] = ['-X', 'utf8', './server.py']
    write_json(DEST / 'codex.mcp.json', mcp)
    version = None
    for manifest in ('.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        data = read_json(DEST / manifest)
        version = data['version'].split('-')[0] + args.suffix
        data['version'] = version
        if manifest.startswith('.claude'):
            for server in (data.get('mcpServers') or {}).values():
                server['command'] = 'python'
        write_json(DEST / manifest, data)
    init = DEST / 'relic_core' / '__init__.py'
    text = init.read_text(encoding='utf-8')
    init.write_text(re.sub(r'__version__ = "[^"]+"', '__version__ = "%s"' % version, text, count=1), encoding='utf-8')
    print('Copied %d files into %s; version %s' % (count, DEST, version))


if __name__ == '__main__':
    main()
