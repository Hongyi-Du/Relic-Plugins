"""Open the Relic App: the desktop chat for your Relic organizations, where members on Claude Code and Codex run."""
from pathlib import Path
import argparse
import runpy
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--no-window', action='store_true', help='Only start the local server and print its address')
operation = parser.add_mutually_exclusive_group()
operation.add_argument('--stop', action='store_true', help='Gracefully stop the authenticated local server')
operation.add_argument('--restart', action='store_true', help='Restart the local server, reusing its port when available')
operation.add_argument('--status', action='store_true', help='Print local server status as JSON without starting it')
parser.add_argument('--port', type=int, default=0, help='Preferred server port (0 reuses the previous port)')
args = parser.parse_args()
entry = Path(__file__).resolve().parents[1] / 'plugins' / 'relic' / 'scripts' / 'relic_app.py'
if not entry.is_file():
    parser.error(f'Incomplete package: {entry}')
sys.argv = [str(entry)] + (['--no-window'] if args.no_window else [])
sys.argv += ['--' + key for key in ('stop', 'restart', 'status') if getattr(args, key)]
if args.port:
    sys.argv += ['--port', str(args.port)]
runpy.run_path(str(entry), run_name='__main__')
