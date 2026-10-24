"""Open the selected edition's Tk panel after installation."""
from pathlib import Path
import argparse
import runpy
import sys

from install import locate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--edition', choices=('codex', 'bridge'))
args = parser.parse_args()
root, edition = locate(Path(__file__).resolve().parents[1], args.edition)
if edition == 'claude':
    parser.error('Claude edition is used in Claude Code and has no standalone panel.')
plugin = root / 'plugins' / ('relic-organization' if edition == 'codex' else 'relic')
entry = plugin / 'scripts' / ('desktop.py' if edition == 'codex' else 'relic_window.py')
sys.argv = [str(entry)]
runpy.run_path(str(entry), run_name='__main__')
