import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.quiet import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, type=Path)
    run(parser.parse_args().store)
