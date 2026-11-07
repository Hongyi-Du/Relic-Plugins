"""Delayed auto-wake retry for one organization (started by wake.schedule_retry), or the delayed keep-going check
(--drive, started by wake.schedule_drive).

A seat that could not be woken yet (busy, its chat in use, woken too recently, hourly cap) is tried again here once it
is due, so a message is not stranded when every member happens to be idle. The keep-going check looks at the
organizations with keep-going on once their next check is due, and arms the next one.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org")
    parser.add_argument("--drive", action="store_true")
    parser.add_argument("--after", type=float, default=0)
    a = parser.parse_args()
    if not a.org and not a.drive:
        parser.error("--org or --drive")
    time.sleep(max(0.0, a.after))
    if a.drive:
        wake.drive_due(Store())
        return
    marker = runner.runs_dir() / ("%s.retry" % a.org)
    try:
        marker.unlink()
    except OSError:
        pass
    wake.dispatch(Store(), a.org)


if __name__ == "__main__":
    main()
