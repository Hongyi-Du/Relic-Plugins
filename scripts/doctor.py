"""Read-only installation diagnostics; does not read conversation contents or start model turns."""
import json
import os
from pathlib import Path
import platform
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import cli, plugin_dir, read_json  # noqa: E402

plugin = plugin_dir()
acp = Path(os.environ.get('RELIC_ACP_HOME') or Path(os.environ.get('RELIC_HOME') or Path.home() / '.relic') / 'acp')
report = {'version': read_json(plugin / '.claude-plugin/plugin.json')['version'], 'system': platform.system(),
          'python': platform.python_version(), 'python_executable': sys.executable,
          'python_supported': sys.version_info >= (3, 11), 'claude_cli': bool(cli('claude')), 'codex_cli': bool(cli('codex')),
          'node': bool(shutil.which('node')),
          'acp_adapters': {name: (acp / 'node_modules' / '@agentclientprotocol' / name / 'dist' / 'index.js').is_file()
                           for name in ('claude-agent-acp', 'codex-acp')},
          'desktop_context_present': bool(os.environ.get('CODEX_APP_TOOLS_PIPE_PATH'))}
data = read_json(plugin / 'codex.mcp.json')
report['mcp_servers'] = {key: {'interpreter_exists': Path(value['command']).is_file(),
                               'script_exists': Path(value['args'][2]).is_file()}
                         for key, value in data['mcpServers'].items()}
report['desktop_transport'] = 'Windows only'
print(json.dumps(report, ensure_ascii=False, indent=2))
