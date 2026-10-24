"""Read frozen natural pilot results; create one new diagnostic report."""

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.scope_evolution.metric_sensitivity import analyze_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New explicit file; parent must already exist")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; immutable inputs and reports cannot be overwritten")
    try:
        result = analyze_run(args.run)
        encoded = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, "Metric analysis failed: " + str(error) + "\n")
    print(str(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
