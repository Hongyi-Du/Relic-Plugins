"""Export the exact shipped tool schemas without starting a host or touching live data."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/relic'))
from relic_core.process import creation_flags
result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c',
                         'from relic_core.api import TOOLS; import json; print(json.dumps(TOOLS, ensure_ascii=False))'],
                        cwd=ROOT / 'plugins' / 'relic', capture_output=True, check=True, text=True, encoding='utf-8',
                        creationflags=creation_flags())
tools = json.loads(result.stdout)
target = ROOT / 'docs/api/relic.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(tools, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('relic', len(tools), 'tools')
