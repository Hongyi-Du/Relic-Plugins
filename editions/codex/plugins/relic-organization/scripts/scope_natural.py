"""Explicit P0–P6 commands for the approved natural-task SCOPE protocol."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.scope_evolution.natural_pilot import NaturalPilot, PilotError, freeze_calibration_plan
from relic_org.store import OrgError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("calibration-plan", "init", "discover", "generate", "train", "freeze", "evaluate", "report"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="Pinned scb-problems checkout; required for init")
    parser.add_argument("--calibration", type=Path, help="Separate nonpilot calibration with raw RPC/product evidence; revalidated for P0 v2 init")
    parser.add_argument("--image", default="scope-checkpoint-evaluator:20261020")
    parser.add_argument("--scheduling-seed", type=int, default=20261020)
    parser.add_argument("--limit", type=int, help="Completed episodes; default 18 for train/evaluate, one for discovery")
    parser.add_argument("--retry-infrastructure", action="store_true", help="Explicit reserve retry of a definitely failed job")
    parser.add_argument("--regenerate", action="store_true", help="Single reserve regeneration after provenance rejection")
    args = parser.parse_args(argv)
    if args.limit is None:
        args.limit = 18 if args.command in {"train", "evaluate"} else 1
    if args.limit < 1:
        parser.error("--limit must be positive")
    episodes = None
    try:
        if args.command == "calibration-plan":
            result = freeze_calibration_plan(args.run)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        from relic_org.scope_evolution.natural_tasks import NaturalTasks
        if args.command == "init":
            if args.source is None:
                parser.error("--source is required for init")
            if args.calibration is None:
                parser.error("--calibration is required for P0 v2 init")
            source, image = args.source, args.image
        else:
            manifest = json.loads((args.run / "manifest.json").read_text(encoding="utf-8"))["manifest"]
            source, image = manifest["task_adapter"]["source"], manifest["task_adapter"]["image_id"]
        tasks = NaturalTasks(source, image)
        # The identity compares the original tag as well as its immutable image ID.
        if args.command != "init":
            tasks.image = manifest["task_adapter"]["image"]
        if args.command in {"discover", "generate", "train", "freeze", "evaluate"}:
            from relic_org.scope_evolution.natural_driver import NaturalEpisodeDriver
            episodes = NaturalEpisodeDriver(args.run)
        pilot = NaturalPilot(args.run, tasks, episodes)
        if args.command == "init":
            result = pilot.init(calibration=args.calibration, scheduling_seed=args.scheduling_seed)
        elif args.command in {"discover", "train", "evaluate"}:
            result = getattr(pilot, args.command)(limit=args.limit, retry_infrastructure=args.retry_infrastructure)
        elif args.command == "generate":
            result = pilot.generate(regenerate=args.regenerate, retry_infrastructure=args.retry_infrastructure)
        else:
            result = getattr(pilot, args.command)()
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 3 if result.get("status") == "awaiting_approval" else 0
    except (PilotError, OrgError, FileNotFoundError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "stopped", "reason": str(error)}, ensure_ascii=False))
        return 2
    finally:
        if episodes is not None:
            episodes.close()


if __name__ == "__main__":
    raise SystemExit(main())
