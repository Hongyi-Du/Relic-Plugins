"""CLI fallback for existing chats whose MCP tool catalog predates org_benchmark."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from relic_org.benchmark import Benchmarks
from relic_org.store import Store

p=argparse.ArgumentParser()
p.add_argument('--org',required=True)
p.add_argument('--actor',default=os.getenv('CODEX_THREAD_ID'))
p.add_argument('--operation',required=True)
p.add_argument('--data',help='Path to JSON arguments; avoids shell quoting problems.')
a=p.parse_args()
if not a.actor:p.error('Current chat identity is required.')
data=json.loads(Path(a.data).read_text(encoding='utf-8-sig')) if a.data else {}
bench=Benchmarks(Store())
upstream=a.operation in {'catalog','events','invoke','upstream_status','export'}
result=(bench.upstream if upstream else bench.call)(a.org,a.actor,a.operation,data)
print(json.dumps(result,ensure_ascii=False,indent=2))
