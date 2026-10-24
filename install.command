#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
exec python3 -X utf8 "$TASK_ROOT/scripts/install.py" "$@"
