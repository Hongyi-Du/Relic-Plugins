"""Reproducible fixed-Patch diagnostics and staged, subscription-only pilot."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.scope_evolution.evaluation import consume_pilot, finish_pilot, prepare_pilot, save_diagnostic, stage_pilot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    diagnostic = commands.add_parser("diagnostic")
    diagnostic.add_argument("--output", type=Path, required=True)
    diagnostic.add_argument("--seed", type=int, default=19)
    diagnostic.add_argument("--train-per-cell", type=int, default=64)
    diagnostic.add_argument("--evaluation-per-cell", type=int, default=12)
    pilot = commands.add_parser("pilot")
    pilot.add_argument("--phase", choices=("generate", "stage", "consume", "finish"), required=True)
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--review-evidence")
    pilot.add_argument("--roster", type=Path)
    pilot.add_argument("--leader")
    report = commands.add_parser("report")
    report.add_argument("--run", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "diagnostic":
        result = save_diagnostic(args.output, seed=args.seed, train_per_cell=args.train_per_cell,
                                 evaluation_per_cell=args.evaluation_per_cell)
        print(json.dumps({"output": str(args.output.resolve()), "replay_matches": result["deterministic_replay_matches"],
                          "methods": {name: {k: v for k, v in value.items() if k != "rows"}
                                      for name, value in result["methods"].items()}}, indent=2))
    elif args.command == "pilot":
        if args.phase == "generate":
            if not args.review_evidence:
                parser.error("--review-evidence is required before executing static pilot source")
            value = prepare_pilot(args.output, args.review_evidence)
        elif args.phase == "stage":
            if not args.roster or not args.leader:
                parser.error("--roster and --leader are required for the actual target organization")
            value = stage_pilot(args.output, args.roster, args.leader)
        else:
            value = (consume_pilot if args.phase == "consume" else finish_pilot)(args.output)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        path = args.run / "diagnostic.json"
        if not path.exists():
            path = args.run / "pilot-report.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({key: value[key] for key in value if key not in {"methods", "paired_training_evidence", "train_tasks", "evaluation_tasks", "recommendation", "calls"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
