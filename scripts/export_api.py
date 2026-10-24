"""Export the exact shipped tool schemas without starting a host or touching live data."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for edition, directory, module in [
    ('claude','relic','server'), ('codex','relic-organization','relic_org.service'),
    ('bridge','relic','relic_core.api')]:
    result = subprocess.run([sys.executable,'-B','-X','utf8','-c',
        f'from {module} import TOOLS; import json; print(json.dumps(TOOLS, ensure_ascii=False))'],
        cwd=ROOT/'editions'/edition/'plugins'/directory, capture_output=True, check=True,
        text=True, encoding='utf-8')
    tools = json.loads(result.stdout)
    target = ROOT/'docs/api'/f'{edition}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(tools,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(edition, len(tools), 'tools')
