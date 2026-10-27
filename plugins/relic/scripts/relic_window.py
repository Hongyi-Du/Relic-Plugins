"""Open the Relic App. The Relic window this script used to open is now part of the App; older shortcuts that run
this script open the App instead (scripts/relic_app.py)."""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.argv[0] = str(Path(__file__).with_name("relic_app.py"))
    runpy.run_path(sys.argv[0], run_name="__main__")
