"""Delayed auto-wake retry for one organization (started by wake.schedule_retry).

A seat that could not be woken yet (busy, its chat in use, woken too recently, hourly cap) is tried again here once it
is due, so a message is not stranded when every member happens to be idle.
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
    parser.add_argument("--org", required=True)
    parser.add_argument("--after", type=float, default=0)
    a = parser.parse_args()
    time.sleep(max(0.0, a.after))
    marker = runner.runs_dir() / ("%s.retry" % a.org)
    try:
        marker.unlink()
    except OSError:
        pass
    wake.dispatch(Store(), a.org)


if __name__ == "__main__":
    main()
