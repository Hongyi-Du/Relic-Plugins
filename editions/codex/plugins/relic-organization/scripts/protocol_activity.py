"""Read protocol execution evidence for the current authorized member session."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.store import Store

parser = argparse.ArgumentParser()
parser.add_argument('--org-id', required=True)
parser.add_argument('--after-event', type=int, default=0)
parser.add_argument('--recent', type=int, default=12)
args = parser.parse_args()
actor = os.getenv('CODEX_THREAD_ID')
if not actor:
    parser.error('Current Codex session identity is required.')
print(json.dumps(Store().protocol_activity(args.org_id, actor, after=args.after_event, recent_limit=args.recent), ensure_ascii=False, indent=2))
