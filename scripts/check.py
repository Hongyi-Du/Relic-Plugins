"""Run fixture suites in separate processes, isolated from the invoking agent's identity and live stores."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--edition', choices=('all','claude','codex','bridge','packaging'), default='all')
parser.add_argument('--output', type=Path, default=ROOT/'test-results')
parser.add_argument('--timeout', type=int, default=300, help='Maximum seconds per isolated suite')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
roots = {'packaging':ROOT, 'claude':ROOT/'editions/claude/plugins/relic',
         'codex':ROOT/'editions/codex/plugins/relic-organization', 'bridge':ROOT/'editions/bridge/plugins/relic'}
results = []
for name, folder in roots.items():
    if args.edition not in ('all',name):
        continue
    with tempfile.TemporaryDirectory(prefix='relic-check-') as temp:
        env = {k:v for k,v in os.environ.items() if not k.startswith(('RELIC_', 'CODEX_'))}
        env.update(RELIC_HOME=str(Path(temp)/'relic'), RELIC_ORG_HOME=str(Path(temp)/'organization'),
                   CODEX_HOME=str(Path(temp)/'codex'), PYTHONDONTWRITEBYTECODE='1',
                   TEMP=temp, TMP=temp, TMPDIR=temp)
        start = time.monotonic()
        log_path = args.output/f'{name}.log'
        print(f'Starting {name}; timeout={args.timeout}s; log={log_path}', flush=True)
        timed_out = False
        with log_path.open('w', encoding='utf-8') as log:
            try:
                proc = subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'scripts/run_fixture_suite.py')],
                                      cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out, exit_code = True, 124
        result = {'edition':name, 'exit_code':exit_code, 'timed_out':timed_out, 'seconds':round(time.monotonic()-start,2)}
        results.append(result)
        print(json.dumps(result), flush=True)
        (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
        if exit_code:
            print(log_path.read_text(encoding='utf-8', errors='replace')[-12000:], flush=True)
(args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
raise SystemExit(any(r['exit_code'] for r in results))
