"""Read-only installation diagnostics; does not read conversation contents or start model turns."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import locate, read_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--edition', choices=('claude', 'codex', 'bridge'))
args = parser.parse_args()
root, edition = locate(Path(__file__).resolve().parents[1], args.edition)
plugin = root / 'plugins' / ('relic-organization' if edition == 'codex' else 'relic')
report = {'edition': edition, 'system': platform.system(), 'python': platform.python_version(),
          'python_executable': sys.executable, 'python_supported': sys.version_info >= (3, 11),
          'codex_on_path': bool(shutil.which('codex')), 'claude_on_path': bool(shutil.which('claude')),
          'desktop_context_present': bool(os.environ.get('CODEX_APP_TOOLS_PIPE_PATH'))}
try:
    import tkinter
    report['tkinter_importable'] = True
except ImportError:
    report['tkinter_importable'] = False
for name in ('.mcp.json', 'codex.mcp.json'):
    if (plugin / name).exists():
        report['mcp_servers'] = {key: {'interpreter_exists': Path(value['command']).is_file(),
            'script_exists': Path(value['args'][2]).is_file()}
            for key, value in read_json(plugin / name)['mcpServers'].items()}
report['bridge_desktop_transport'] = 'Windows only' if edition == 'bridge' else 'host dependent'
print(json.dumps(report, ensure_ascii=False, indent=2))
