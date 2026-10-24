"""Run the full suite; isolate each macOS Tk fixture in its own process.

Cocoa Tk can stall while updating a second withdrawn Tk interpreter in one
process. Production panels have one interpreter per process. Keep all GUI
assertions and match that lifecycle, rather than skipping the panel tests.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import unittest


def cases(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from cases(case)
        else:
            yield case


class IsolatedTkFixture(unittest.TestCase):
    def __init__(self, test_id):
        super().__init__()
        self.test_id = test_id

    def id(self):
        return self.test_id

    def __str__(self):
        return self.test_id + ' [isolated Tk process]'

    def runTest(self):
        proc = subprocess.run(
            [sys.executable, '-B', '-X', 'utf8', str(Path(__file__).resolve()),
             '--test-id', self.test_id],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        detail = proc.stdout + proc.stderr
        if proc.returncode == 77:
            self.skipTest(detail.strip())
        self.assertEqual(proc.returncode, 0, detail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-id')
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    loader = unittest.TestLoader()
    discovered = list(cases(loader.discover('tests', pattern='test_*.py')))
    if args.test_id:
        selected = [case for case in discovered if case.id() == args.test_id]
        if len(selected) != 1:
            raise SystemExit(f'Expected one test named {args.test_id}; found {len(selected)}')
    else:
        selected = []
        for case in discovered:
            gui = (case.__class__.__name__ == 'NativeWindowTests' and case.__module__ == 'test_desktop'
                   or case.__class__.__name__ == 'DiscussionRoom' and case.__module__ == 'test_window')
            selected.append(IsolatedTkFixture(case.id()) if sys.platform == 'darwin' and gui else case)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    if not result.wasSuccessful():
        return 1
    return 77 if args.test_id and result.skipped else 0


if __name__ == '__main__':
    raise SystemExit(main())
