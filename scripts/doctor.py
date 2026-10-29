"""Read-only installation diagnostics; does not read conversation contents or start model turns."""
import json
import argparse
import os
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import cli, plugin_dir, read_json  # noqa: E402
from relic_core import platform_support  # noqa: E402
from app import harness  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--probe-desktop', action='store_true',
                    help='Perform a bounded tools/list handshake and Claude CLI version check; never send a message.')
args = parser.parse_args()
plugin = plugin_dir()
capabilities = platform_support.capabilities(probe=args.probe_desktop)
node = platform_support.node_runtime()
acp = Path(os.environ.get('RELIC_ACP_HOME') or Path(os.environ.get('RELIC_HOME') or Path.home() / '.relic') / 'acp')
report = {'version': read_json(plugin / '.claude-plugin/plugin.json')['version'], 'system': platform.system(),
          'python': platform.python_version(), 'python_executable': sys.executable,
          'architecture': platform.machine(),
          'python_supported': sys.version_info >= (3, 11) and (sys.platform != 'darwin' or capabilities['macos_supported']),
          'claude_cli': bool(cli('claude')), 'codex_cli': bool(cli('codex')),
          'executables': {name: platform_support.find_executable(name) for name in ('claude', 'codex', 'node', 'npm', 'git')},
          'node': bool(node['path']), 'node_runtime': node, 'capabilities': capabilities,
          'acp_adapters': {'claude-agent-acp': harness.installed('claude-code'), 'codex-acp': harness.installed('codex')},
          'adapter_installation': {key: {'version': harness.adapter_version(key),
                                         'entry': str(harness._package_entry(spec['package'].rsplit('@', 1)[0]))}
                                   for key, spec in harness.HARNESSES.items() if spec.get('package')},
          'desktop_context_present': bool(os.environ.get('CODEX_APP_TOOLS_PIPE_PATH'))}
data = read_json(plugin / 'codex.mcp.json')
report['mcp_servers'] = {key: {'interpreter_exists': Path(value['command']).is_file(),
                               'script_exists': (plugin / value['args'][2]).is_file()}
                         for key, value in data['mcpServers'].items()}
report['desktop_transport'] = capabilities.get('desktop_transport') or (
    'Windows desktop bridge' if capabilities['codex_desktop_wake'] else 'No available desktop bridge')
print(json.dumps(report, ensure_ascii=False, indent=2))
