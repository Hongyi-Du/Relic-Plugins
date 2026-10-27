"""Open the Relic App, the Bridge edition's desktop chat for Relic organizations."""
from pathlib import Path
import argparse
import runpy
import sys

from install import locate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--edition', choices=('bridge',))
parser.add_argument('--no-window', action='store_true', help='Only start the local server and print its address')
args = parser.parse_args()
root, edition = locate(Path(__file__).resolve().parents[1], args.edition)
if edition != 'bridge':
    parser.error('The Relic App comes with the Bridge edition.')
entry = root / 'plugins' / 'relic' / 'scripts' / 'relic_app.py'
sys.argv = [str(entry)] + (['--no-window'] if args.no_window else [])
runpy.run_path(str(entry), run_name='__main__')
