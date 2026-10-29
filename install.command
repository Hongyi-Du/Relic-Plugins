#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -n "${RELIC_PYTHON_PATH:-}" ]]; then
    exec "$RELIC_PYTHON_PATH" -X utf8 "$TASK_ROOT/scripts/install.py" "$@"
fi
for task_python in "$(command -v python3 || true)" /opt/homebrew/bin/python3 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.11; do
    [[ -x "$task_python" ]] || continue
    if "$task_python" -c 'import platform,sys; sys.exit(not (sys.version_info >= (3,11) and platform.machine() == "arm64"))'; then
        exec "$task_python" -X utf8 "$TASK_ROOT/scripts/install.py" "$@"
    fi
done
echo "Relic requires native arm64 Python 3.11+ on Apple silicon. Install it or set RELIC_PYTHON_PATH." >&2
exit 1
