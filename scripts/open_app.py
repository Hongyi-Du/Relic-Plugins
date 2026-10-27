"""Open the Relic App: the desktop chat for your Relic organizations, where members on Claude Code and Codex run."""
from pathlib import Path
import argparse
import runpy
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--no-window', action='store_true', help='Only start the local server and print its address')
args = parser.parse_args()
entry = Path(__file__).resolve().parents[1] / 'plugins' / 'relic' / 'scripts' / 'relic_app.py'
if not entry.is_file():
    parser.error(f'Incomplete package: {entry}')
sys.argv = [str(entry)] + (['--no-window'] if args.no_window else [])
runpy.run_path(str(entry), run_name='__main__')
