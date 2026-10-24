"""Export saved pilot receipts and POSTHOC AST descriptions without execution.

Only --output-dir writes: it must name a new directory with an existing parent.
--self-check validates actual saved rows and a CSV round trip entirely in memory.
No product is imported or executed; no chooser, evaluator or model is invoked.
"""

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.scope_evolution.metric_sensitivity import count_grade


class ExportError(ValueError):
    pass


SUBSETS = ("inherited", "new", "in_file_regression")
SUBSET_FIELDS = ("collected", "executed", "passed", "failed", "skipped", "pass_rate")
FIELDS = (
    "job_id", "split", "family", "replicate", "patch", "deployment_arm", "task_id", "checkpoint",
    "episode_status", "execution_status", "score_status", "evaluator_timeout", "product_unchanged",
    "collected", "executed", "passed", "failed", "errors", "skipped", "observed_nodes", "not_run",
    "missing_node_count", "counts_complete", "primary", "original_pass_rate", "secondary_fixed_collected",
    "wall_seconds", "tool_actions", "token_usage_status", "total_tokens", "input_tokens",
    "cached_input_tokens", "cache_write_input_tokens", "noncached_input_tokens", "output_tokens",
    "reasoning_output_tokens", "nonreasoning_output_tokens", "output_accounting",
    "postflight_status", "contamination_status", "failure_code", "result_flags", "historical_kind",
    "inherited_applicability",
) + tuple(s + "_" + f for s in SUBSETS for f in SUBSET_FIELDS) + (
    "outcome_ref", "primary_grade_ref", "historical_ref", "product_snapshot_sha256",
)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def inventory_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.hashes = {}

    def path(self, path):
        path = Path(path)
        path = (path if path.is_absolute() else self.root / path).resolve()
        if not path.is_relative_to(self.root):
            raise ExportError("Input reference leaves the specified run: " + str(path))
        return path

    def raw(self, path):
        path = self.path(path)
        raw = path.read_bytes()
        name = path.relative_to(self.root).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        if name in self.hashes and self.hashes[name] != sha:
            raise ExportError("Input changed during export: " + name)
        self.hashes[name] = sha
        return raw

    def json(self, path):
        return json.loads(self.raw(path))


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def usage_columns(episode):
    raw = (episode.get("token_usage") or {}).get("total") or {}
    report = episode.get("token_usage_report") or {}
    result = {"wall_seconds": episode.get("elapsed_seconds"), "tool_actions": episode.get("tool_actions"),
        "token_usage_status": "reported" if raw else "unavailable",
        "input_tokens": raw.get("inputTokens"), "cached_input_tokens": raw.get("cachedInputTokens"),
        "cache_write_input_tokens": raw.get("cacheWriteInputTokens"),
        "output_accounting": "output_tokens includes reasoning_output_tokens; reasoning is a subset, never added twice"}
    for target, source in (("total_tokens", "totalTokens"), ("output_tokens", "outputTokens"),
                           ("reasoning_output_tokens", "reasoningOutputTokens")):
        result[target] = raw.get(source)
        if target in report and report[target] != result[target]:
            raise ExportError("Saved token report disagrees with episode token_usage: " + target)
    inp, cached = result["input_tokens"], result["cached_input_tokens"]
    out, reasoning = result["output_tokens"], result["reasoning_output_tokens"]
    result["noncached_input_tokens"] = inp - cached if inp is not None and cached is not None else None
    result["nonreasoning_output_tokens"] = out - reasoning if out is not None and reasoning is not None and out >= reasoning else None
    for field in ("noncached_input_tokens", "nonreasoning_output_tokens"):
        if field in report and report[field] != result[field]:
            raise ExportError("Saved token subset disagrees with raw token_usage: " + field)
    return result


def load_outcome(reader, manifest, relative):
    outcome = reader.json(relative)
    directory = relative.parent
    split, family = outcome["split"], outcome["family"]
    task = manifest["tasks"][family]["evaluation" if split == "evaluation" else "train"]
    if outcome["task_id"] != task["task_id"] or outcome["checkpoint"] != task["checkpoint"]:
        raise ExportError("Outcome task/checkpoint differs from P0: " + outcome["job_id"])
    primary_path = reader.path(outcome["primary_grade"])
    if primary_path.parent != reader.path(directory) or primary_path.name not in ("main.json", "main-retry.json"):
        raise ExportError("Primary grade must be this outcome's saved main/main-retry.json")
    original = reader.json(directory / "main.json")
    attempts = outcome["grader_attempts"]
    expected_attempts = 2 if original.get("infrastructure_error") else 1
    if len(attempts) != expected_attempts:
        raise ExportError("Grader attempt count differs from original main.json")
    for attempt, name in zip(attempts, ("main.json", "main-retry.json")):
        if attempt["result"] != reader.json(directory / name):
            raise ExportError("Embedded grader attempt differs from its raw file")
    main = reader.json(primary_path)
    if main != outcome["main"] or main != attempts[-1]["result"]:
        raise ExportError("Outcome main differs from effective original grader receipt")
    if primary_path.name != ("main-retry.json" if expected_attempts == 2 else "main.json"):
        raise ExportError("Effective primary grade is not the final saved attempt")
    for key in ("source_commit", "image_id"):
        if main[key] != manifest["task_adapter"][key]:
            raise ExportError("Grader identity differs from P0: " + key)
    if main["problem"] != family or main["checkpoint"] != task["checkpoint"]:
        raise ExportError("Raw grade task identity differs from outcome")
    timeout = outcome.get("evaluator_timeout") is True
    if timeout and (expected_attempts != 2 or not all(a["result"].get("timed_out") is True and
            a["result"].get("infrastructure_error") is True for a in attempts)):
        raise ExportError("Repeated timeout requires both saved timed-out grader attempts")
    counts = count_grade(main, task["nodes"], evaluator_timeout=timeout)
    if outcome["score"] != counts["primary"]:
        raise ExportError("CSV primary would differ from saved outcome score")
    historical = reader.json(directory / "historical.json")
    if historical != outcome["historical"] or historical["extra_grader_executions"] != 0:
        raise ExportError("Historical export must use the saved same-primary breakdown")
    if historical.get("tests") != main["tests"]:
        raise ExportError("Historical breakdown does not refer to the same original test rows")
    snapshot = reader.json(directory / "snapshot.json")
    if snapshot != outcome["parent"] or inventory_digest(snapshot["files"]) != snapshot["digest"]:
        raise ExportError("Frozen product snapshot differs from outcome")
    if main["submission_files"] != snapshot["files"] or main["submission_digest"] != snapshot["digest"]:
        raise ExportError("Frozen product is not the graded submission")
    episode = outcome["episode"]
    row = {key: outcome.get(key) for key in ("job_id", "split", "family", "replicate", "patch", "deployment_arm",
        "task_id", "checkpoint", "score_status", "evaluator_timeout", "product_unchanged")}
    row.update({key: counts[key] for key in ("collected", "executed", "passed", "failed", "errors", "skipped",
        "observed_nodes", "not_run", "counts_complete", "primary", "original_pass_rate")})
    row.update(secondary_fixed_collected=counts["secondary"], missing_node_count=len(counts["missing_nodes"]),
        episode_status=episode["status"], execution_status=episode.get("execution_status"),
        postflight_status=(episode.get("postflight_isolation") or {}).get("status"),
        contamination_status=(episode.get("contamination") or {}).get("status"),
        failure_code=episode.get("failure_code"), result_flags=json.dumps(episode.get("result_flags", []), separators=(",", ":")),
        historical_kind=historical["kind"], inherited_applicability=historical["inherited_applicability"],
        outcome_ref=relative.as_posix(), primary_grade_ref=primary_path.relative_to(reader.root).as_posix(),
        historical_ref=(directory / "historical.json").as_posix(), product_snapshot_sha256=snapshot["digest"],
        **usage_columns(episode))
    for subset in SUBSETS:
        part = historical[subset]
        for field in SUBSET_FIELDS:
            value = None if part is None else part["executed"] - part["passed"] if field == "failed" else part[field]
            row[subset + "_" + field] = value
    return row, outcome, snapshot


def module_inventory(files):
    modules, packages = {}, set()
    for name in files:
        path = PurePosixPath(name)
        if path.suffix != ".py":
            continue
        parts = list(path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts and all(p.isidentifier() for p in parts):
            modules[".".join(parts)] = name
        for length in range(1, len(path.parts)):
            prefix = path.parts[:length]
            if all(p.isidentifier() for p in prefix):
                packages.add(".".join(prefix))
    return modules, packages


def import_description(node, source_name, modules, packages):
    package = source_name if modules.get(source_name, "").endswith("/__init__.py") else source_name.rpartition(".")[0]
    if isinstance(node, ast.Import):
        requests = [(alias.name, 0, []) for alias in node.names]
    else:
        base = node.module or ""
        if node.level:
            parts = package.split(".") if package else []
            if not parts or node.level > len(parts):
                return [{"line": node.lineno, "statement": "from", "level": node.level, "module": base,
                    "names": [a.name for a in node.names], "resolution": "relative_level_outside_inventory"}]
            base = ".".join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
        requests = [(base, node.level, [a.name for a in node.names])]
    descriptions = []
    local_roots = {name.split(".", 1)[0] for name in set(modules) | packages}
    for module, level, names in requests:
        present = module in modules or module in packages
        resolution = "local_target_present" if present else "relative_target_not_in_snapshot" if level else (
            "local_prefix_present_target_not_in_snapshot" if module.split(".", 1)[0] in local_roots else
            "stdlib_name" if module.split(".", 1)[0] in sys.stdlib_module_names else "nonlocal_or_unresolved_static")
        descriptions.append({"line": node.lineno, "statement": "from" if isinstance(node, ast.ImportFrom) else "import",
            "module": module, "level": level, "names": names, "resolution": resolution,
            "module_file": modules.get(module), "package_directory_present": module in packages,
            "member_module_files": {name: modules.get(module + "." + name) for name in names if name != "*"},
            "member_note": "An imported name can be an attribute; absent member files are not import failures."})
    return descriptions


def describe_product(reader, manifest, job, snapshot):
    job_id, family, split = job["job_id"], job["family"], job["split"]
    preparation = reader.json(Path("products") / job_id / "preparation.json")
    if preparation["digest"] != job["initial_state_id"] or inventory_digest(preparation["files"]) != preparation["digest"]:
        raise ExportError("Initial product metadata disagrees with outcome: " + job_id)
    p0 = manifest["tasks"][family][split]["starter"]["files"]
    product = Path("outcomes") / job_id / "product"
    if reader.path(snapshot["path"]) != reader.path(product):
        raise ExportError("Product snapshot path differs from its outcome directory")
    files = snapshot["files"]
    modules, packages = module_inventory(files)
    names = {path: name for name, path in modules.items()}
    descriptions = []
    for filename, sha in sorted(files.items()):
        relative = PurePosixPath(filename)
        if relative.is_absolute() or ".." in relative.parts or "\\" in filename:
            raise ExportError("Invalid frozen product file path")
        if relative.suffix != ".py":
            continue
        raw = reader.raw(product / filename)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ExportError("Python source changed after grading: " + job_id + "/" + filename)
        description = {"path": filename, "module": names.get(filename), "sha256": sha,
            "new_since_phase_initial": filename not in preparation["files"],
            "new_since_P0_starter": filename not in p0,
            "changed_since_phase_initial": preparation["files"].get(filename) != sha,
            "role": "self_test_path" if "tests" in relative.parts or relative.name.startswith("test_") else "product_path"}
        try:
            tree = ast.parse(raw, filename=filename)
        except (SyntaxError, ValueError, UnicodeError) as error:
            description.update(ast_status="parse_error", parse_error=str(error))
        else:
            doc = ast.get_docstring(tree)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.extend(import_description(node, names.get(filename, ""), modules, packages))
            description.update(ast_status="parsed", docstring_first_line=doc.splitlines()[0][:240] if doc else None,
                top_level_functions=[n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                top_level_classes=[n.name for n in tree.body if isinstance(n, ast.ClassDef)],
                imports=sorted(imports, key=lambda i: (i["line"], i["module"])))
        descriptions.append(description)
    return {"job_id": job_id, "split": split, "family": family, "replicate": job["replicate"], "patch": job["patch"],
        "status": "described", "analysis": "POSTHOC_STATIC_AST_ONLY", "snapshot_sha256": snapshot["digest"],
        "phase_initial_sha256": preparation["digest"], "phase_initial_ref": "products/" + job_id + "/preparation.json",
        "added_python_paths": [d["path"] for d in descriptions if d["new_since_phase_initial"]],
        "removed_python_paths": sorted(f for f in preparation["files"] if f.endswith(".py") and f not in files),
        "modules": descriptions}


def collect_exports(run_dir):
    """Return (summary, CSV rows, 36 product descriptions) without any writes."""
    reader = Reader(run_dir)
    envelope = reader.json("manifest.json")
    manifest = envelope["manifest"]
    families = manifest["families"]
    if canonical_digest(manifest) != envelope["sha256"] or len(set(families)) != 3 or manifest["n_tasks"] != 3 or manifest["replicates"] != 3:
        raise ExportError("Expected the hashed P0 contract for three families and three replicates")
    expected_jobs = []
    for split in ("train", "evaluation"):
        jobs = manifest["condition_order"][split]
        if (len(jobs) != 18 or {(j["family"], j["replicate"], j["patch"]) for j in jobs} !=
                {(f, r, p) for f in families for r in (1, 2, 3) for p in (False, True)}
                or any(j["split"] != split for j in jobs)):
            raise ExportError("P0 does not contain the fixed 36 condition jobs")
        expected_jobs.extend(jobs)
        for family in families:
            task = manifest["tasks"][family][split]
            nodes = task["nodes"]
            ids = [t["id"] for t in task["collection"]["tests"]]
            if len(nodes) != len(set(nodes)) or len(ids) != len(nodes) or set(ids) != set(nodes):
                raise ExportError("P0 nodes disagree with its saved collection")
    expected = {j["job_id"]: j for j in expected_jobs}
    if len(expected) != 36:
        raise ExportError("P0 job IDs are not unique")
    for f in families:
        expected["discovery-" + f] = {"job_id": "discovery-" + f, "split": "discovery", "family": f, "replicate": 1, "patch": False}
    rows, products, present = [], {}, set()
    for path in sorted((reader.root / "outcomes").glob("*/outcome.json")):
        relative = path.relative_to(reader.root)
        raw = reader.json(relative)
        job_id = raw["job_id"]
        spec = expected.get(job_id)
        if (spec is None or job_id != path.parent.name or job_id in present
                or any(type(raw.get(k)) is not type(v) or raw[k] != v for k, v in spec.items())):
            raise ExportError("Unexpected or duplicate outcome job: " + job_id)
        row, outcome, snapshot = load_outcome(reader, manifest, relative)
        rows.append(row)
        present.add(job_id)
        if raw["split"] in ("train", "evaluation"):
            products[job_id] = describe_product(reader, manifest, outcome, snapshot)
    product_list = [products[j["job_id"]] if j["job_id"] in products else dict(j, status="missing_outcome", modules=[])
        for j in expected_jobs]
    counts = Counter(r["split"] for r in rows)
    missing = [j["job_id"] for j in expected_jobs if j["job_id"] not in present]
    summary = {"schema": "scope-pilot-posthoc-exports-v1", "at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if missing or counts["discovery"] != 3 else "complete",
        "manifest_sha256": envelope["sha256"], "n_tasks": 3, "families": families, "replicates_per_condition": 3,
        "csv_rows": len(rows), "saved_outcomes_by_split": {s: counts[s] for s in ("discovery", "train", "evaluation")},
        "expected_train_evaluation_products": 36, "described_products": len(products), "missing_product_job_ids": missing,
        "missing_discovery_job_ids": ["discovery-" + f for f in families if "discovery-" + f not in present],
        "planned_research_turns": 40, "research_turn_definition": "3 discovery + 1 generator + 36 train/evaluation condition turns; NOT 40 underlying API/model requests",
        "underlying_api_request_count": None, "development_export_cli_is_research_turn": False,
        "secondary_definition": "passed / frozen P0 collected; skipped are nonpasses; repeated evaluator timeout retains zero",
        "historical_definition": "saved same-primary breakdown, not new grading; N/A and unavailable fields stay empty in CSV",
        "reasoning_definition": "reasoning_output_tokens is a subset of output_tokens, not an additional token charge",
        "ast_interpretation": "POSTHOC descriptive only. Static import flags and parse errors are neither product failure verdicts nor causal evidence. Products are never imported/executed. Imports may be conditional; dynamic imports, attributes and runtime sys.path are not resolved.",
        "input_read_boundary": ["manifest.json", "outcomes/*/{outcome,main,main-retry,historical,snapshot}.json (only existing declared attempts)",
            "outcomes/<train-or-evaluation-job>/product/*.py recursively, only snapshot-listed Python sources",
            "products/<existing-train-or-evaluation-job>/preparation.json"],
        "input_sha256": reader.hashes, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return summary, rows, product_list


def self_check(run_dir, sample_job=None):
    """Check real producer receipts and one actual CSV row, entirely in memory."""
    summary, rows, products = collect_exports(run_dir)
    decoded = list(csv.DictReader(io.StringIO(csv_text(rows))))
    if len(decoded) != len(rows) or len(products) != 36:
        raise ExportError("CSV round trip or fixed product roster differs")
    if not rows:
        raise ExportError("Self-check needs at least one actual saved outcome")
    sample = next((r for r in rows if r["job_id"] == sample_job), None) if sample_job else next(
        (r for r in rows if r["family"] == "dynamic_config_service_api"), rows[0])
    if sample is None:
        raise ExportError("Requested sample job has no actual saved outcome")
    reader = Reader(run_dir)
    source = reader.json(sample["outcome_ref"])
    main = reader.json(sample["primary_grade_ref"])
    csv_row = next(r for r in decoded if r["job_id"] == sample["job_id"])
    for key in FIELDS:
        expected = "" if sample[key] is None else str(sample[key])
        if csv_row[key] != expected:
            raise ExportError("CSV round trip changed sample field: " + key)
    observed = Counter(t["status"] for t in main["tests"])
    if int(csv_row["passed"]) != observed["passed"] or int(csv_row["skipped"]) != observed["skipped"] or float(csv_row["primary"]) != source["score"]:
        raise ExportError("Single-row CSV disagrees with actual original grader/outcome")
    episode = source["episode"]
    if float(csv_row["wall_seconds"]) != episode["elapsed_seconds"] or int(csv_row["tool_actions"]) != episode["tool_actions"]:
        raise ExportError("Single-row CSV disagrees with actual episode resource receipt")
    if source["historical"]["inherited"] is None and csv_row["inherited_pass_rate"] != "":
        raise ExportError("Historical N/A was converted into a number")
    root = Path(run_dir).resolve()
    if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != sha for name, sha in summary["input_sha256"].items()):
        raise ExportError("An analyzed input changed during self-check")
    return {"self_check": "passed", "status": summary["status"], "saved_outcomes_by_split": summary["saved_outcomes_by_split"],
        "csv_rows": len(rows), "described_products": summary["described_products"], "expected_products": 36,
        "missing_products": len(summary["missing_product_job_ids"]), "inputs_unchanged": len(summary["input_sha256"]),
        "sample_job": sample["job_id"], "sample_csv": csv_text([sample]),
        "script_sha256": summary["script_sha256"]}


def export_run(run_dir, output_dir):
    root, target = Path(run_dir).resolve(), Path(output_dir).resolve()
    if target.exists() or Path(output_dir).is_symlink():
        raise ExportError("Output directory already exists; never overwrite inputs or earlier exports")
    if target == root or root.is_relative_to(target):
        raise ExportError("Output cannot contain the input run")
    if any(target.is_relative_to(root / name) for name in ("outcomes", "products", "p0", "driver", "private")):
        raise ExportError("Output cannot be inside a product or execution input directory")
    summary, rows, products = collect_exports(root)
    payloads = {"outcomes.csv": csv_text(rows),
        "posthoc_product_modules.json": json.dumps({"status": summary["status"], "interpretation": summary["ast_interpretation"],
            "expected_products": 36, "products": products}, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "README.md": "# Saved pilot exports\n\nStatus: " + summary["status"] + ".\n\n"
            + summary["research_turn_definition"] + ". The study has three task families; repetitions and test nodes are not new tasks.\n\n"
            + summary["secondary_definition"] + ".\n\n" + summary["reasoning_definition"] + ".\n\n"
            + summary["historical_definition"] + ".\n\n" + summary["ast_interpretation"] + "\n"}
    summary["output_sha256"] = {name: hashlib.sha256(value.encode("utf-8")).hexdigest() for name, value in payloads.items()}
    payloads["export_manifest.json"] = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    target.mkdir(exist_ok=False)
    for name, content in payloads.items():
        with (target / name).open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
    return {"output_dir": str(target), "status": summary["status"], "csv_rows": len(rows),
        "described_products": summary["described_products"], "missing_products": len(summary["missing_product_job_ids"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="Exclusively create this new directory; parent must exist")
    mode.add_argument("--self-check", action="store_true", help="Check real saved rows in memory; no output files")
    parser.add_argument("--sample-job", help="Actual saved job for the single-row self-check")
    args = parser.parse_args(argv)
    if args.sample_job and not args.self_check:
        parser.error("--sample-job is only for --self-check")
    try:
        result = self_check(args.run, args.sample_job) if args.self_check else export_run(args.run, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, "Read-only export failed: " + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
