"""Fresh local entry point for authorized member tools while old MCP connections drain."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', required=True, choices=['org_context', 'org_work', 'org_protocol', 'org_review', 'org_message', 'org_call', 'org_scope_evolution'])
    parser.add_argument('--arguments-file', type=Path, required=True)
    args = parser.parse_args()
    actor = os.getenv('CODEX_THREAD_ID')
    if not actor:
        parser.error('The actual member executor CODEX_THREAD_ID is required; no actor override is accepted.')
    payload = json.loads(args.arguments_file.read_text(encoding='utf-8-sig'))
    if not isinstance(payload, dict) or not payload.get('org_id'):
        parser.error('Tool arguments must include org_id.')
    service = Service(actor=actor)
    try:
        service.selected(payload['org_id'], actor)
        result = service.call(args.tool, payload)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error), 'error_type': type(error).__name__}, ensure_ascii=False))
        return 1
    finally:
        service.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
