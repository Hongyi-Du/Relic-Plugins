"""Read-only, fixed-denominator diagnostics for frozen natural pilot receipts.

No evaluator, controller, executor or deployment is invoked here. The public
training chooser is reused only for a diagnostic comparison; evaluation arms
always come from the hashed primary P4 artifact. Replicates are not new tasks.
"""

from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from . import natural_learning as learning


class MetricError(ValueError):
    """An input receipt disagrees with its frozen producer contract."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _nodes(expected_nodes):
    nodes = list(expected_nodes)
    if not nodes or any(not isinstance(n, str) or not n for n in nodes) or len(set(nodes)) != len(nodes):
        raise MetricError("P0 nodes must be nonempty, unique node IDs.")
    return nodes


def _index(main, expected_nodes, *, partial=False):
    nodes = _nodes(expected_nodes)
    rows = main.get("tests")
    if not isinstance(rows, list):
        raise MetricError("Grade requires a tests list.")
    ids = [r.get("id") for r in rows]
    if any(not isinstance(n, str) for n in ids) or len(set(ids)) != len(ids):
        raise MetricError("Duplicate or invalid grade node ID.")
    if set(ids) - set(nodes) or (not partial and set(ids) != set(nodes)):
        raise MetricError("Grade node IDs differ from fixed P0 collection.")
    allowed = {"passed", "failed", "error", "skipped"} | ({"not_run"} if partial else set())
    if any(r.get("status") not in allowed for r in rows):
        raise MetricError("Unscored or unknown node status in grade.")
    return {r["id"]: r["status"] for r in rows}


def count_grade(main, expected_nodes, *, evaluator_timeout=False):
    """Independently count the original node rows; validate declared counters.

    A repeated evaluator timeout retains score zero and the fixed denominator.
    Observed counts remain observed counts: absent/not_run nodes are explicitly
    reported, never invented as failed or skipped. Its whole pair is excluded
    from the sensitivity comparison by analyze_run.
    """
    nodes = _nodes(expected_nodes)
    states = _index(main, nodes, partial=evaluator_timeout)
    counts = Counter(states.values())
    passed, failed, skipped = counts["passed"], counts["failed"] + counts["error"], counts["skipped"]
    executed = passed + failed
    if evaluator_timeout:
        if main.get("timed_out") is not True or main.get("infrastructure_error") is not True:
            raise MetricError("Evaluator timeout requires an actual timed-out infrastructure receipt.")
    else:
        if (main.get("infrastructure_error") is not False or main.get("timed_out") is not False
                or main.get("collect_only") is not False or main.get("collection_errors")):
            raise MetricError("Ordinary grade must be a completed non-infrastructure evaluation.")
        for field, value in (("test_count", len(nodes)), ("executed_count", executed), ("skipped_count", skipped)):
            if type(main.get(field)) is not int or main[field] != value:
                raise MetricError("Independent count differs from declared " + field + ".")
        if not executed:
            raise MetricError("Ordinary primary score has no executed nodes.")
        rate = passed / executed
        if main.get("pass_rate") != rate or main.get("score") != rate:
            raise MetricError("Independent count differs from original primary score/pass_rate.")
    return {"passed": passed, "failed": failed, "skipped": skipped,
        "collected": len(nodes), "executed": executed, "observed_nodes": len(states),
        "errors": counts["error"], "status_counts": dict(counts),
        "not_run": counts["not_run"], "missing_nodes": sorted(set(nodes) - set(states)),
        "counts_complete": len(states) == len(nodes) and not counts["not_run"],
        "original_pass_rate": main.get("pass_rate"),
        "primary": 0.0 if evaluator_timeout else passed / executed,
        "secondary": 0.0 if evaluator_timeout else passed / len(nodes),
        "evaluator_timeout": evaluator_timeout}


def compare_nodes(before, after, expected_nodes):
    """Return exact state transitions, including all formerly passed regressions."""
    count_grade(before, expected_nodes)
    count_grade(after, expected_nodes)
    left, right = _index(before, expected_nodes), _index(after, expected_nodes)
    matrix = {a + "->" + b: [] for a in ("passed", "failed", "error", "skipped") for b in ("passed", "failed", "error", "skipped")}
    for node in sorted(left):
        matrix[left[node] + "->" + right[node]].append(node)
    return {"counts": {k: len(v) for k, v in matrix.items()}, "nodes": matrix,
        "original_skipped": sum(v == "skipped" for v in left.values()),
        "persistent_skipped": len(matrix["skipped->skipped"]),
        "newly_skipped": len(matrix["failed->skipped"]) + len(matrix["error->skipped"]) + len(matrix["passed->skipped"]),
        "formerly_passed_regressed": sum(len(matrix["passed->" + s]) for s in ("failed", "error", "skipped"))}


def _summary(deltas):
    if not deltas:
        return {"deltas": [], "mean_delta": None, "mean_decimal": None, "sign": None}
    mean = sum(deltas, Decimal(0)) / len(deltas)
    return {"deltas": [float(d) for d in deltas], "mean_delta": float(mean),
        "mean_decimal": str(mean), "sign": "positive" if mean > 0 else "negative" if mean < 0 else "zero"}


def _delta(treatment, control, metric):
    return Decimal(str(treatment[metric])) - Decimal(str(control[metric]))


def _split_report(rows, family, split):
    lookup = {(r["replicate"], r["patch"]): r for r in rows if r["family"] == family and r["split"] == split}
    if len({r["initial_state_id"] for r in lookup.values()}) > 1:
        raise MetricError("Family replicates changed the frozen initial state.")
    pairs, missing, included, excluded = [], [], [], []
    for replicate in learning.REPLICATES:
        if any((replicate, patch) not in lookup for patch in (False, True)):
            missing.append(replicate)
            continue
        control, treatment = (lookup[(replicate, p)] for p in (False, True))
        if any(control[k] != treatment[k] for k in ("initial_state_id", "task_id", "checkpoint")):
            raise MetricError("Unmatched within-family replicate pair.")
        timeout = control["evaluator_timeout"] or treatment["evaluator_timeout"]
        pair = {"replicate": replicate, "control": control["job_id"], "treatment": treatment["job_id"],
            "primary_delta": float(_delta(treatment, control, "primary")),
            "secondary_delta": float(_delta(treatment, control, "secondary")),
            "evaluator_timeout": timeout, "node_transitions": None}
        if not timeout:
            pair["node_transitions"] = compare_nodes(control["_grade"], treatment["_grade"], control["_nodes"])
            included.append((control, treatment))
        else:
            excluded.append(replicate)
        pairs.append(pair)
    primary = _summary([_delta(t, c, "primary") for c, t in included])
    secondary = _summary([_delta(t, c, "secondary") for c, t in included])
    complete = not missing and not excluded
    return {"pairs": pairs, "missing_replicates": missing, "excluded_timeout_replicates": excluded,
        "included_replicates": [c["replicate"] for c, _ in included], "complete": complete,
        "comparison_rule": "exclude entire evaluator_timeout pair from both metrics; require all three for agreement",
        "primary": primary, "secondary": secondary,
        "mean_sign_differs": primary["sign"] != secondary["sign"] if complete else None}


def _environment(manifest, family, split):
    return ":".join((manifest["task_adapter"]["source_commit"], manifest["task_adapter"]["image_id"],
        manifest["tasks"][family][split]["checkpoint"]))


def _learning_pairs(rows, manifest, patch_ref, metric):
    grouped = {(r["family"], r["replicate"], r["patch"]): r for r in rows if r["split"] == "train"}
    pairs = []
    for family in manifest["families"]:
        for replicate in learning.REPLICATES:
            outcomes = []
            for patch in (False, True):
                row = grouped[(family, replicate, patch)]
                outcomes.append(learning.NaturalOutcome(trial_id=row["job_id"], task_id=row["task_id"],
                    task_family=family, checkpoint=int(row["checkpoint"].rsplit("_", 1)[1]),
                    environment_version=_environment(manifest, family, "train"),
                    initial_state_id=row["initial_state_id"], replicate=replicate, split="train", score=row[metric],
                    evaluator_version=_digest(manifest["task_adapter"]), evidence_refs=tuple(row["evidence_refs"]),
                    patch_ref=patch_ref if patch else None, model=manifest["model"],
                    status="task_budget_expired" if row["episode_status"] == "budget_expired" else "completed"))
            pairs.append(learning.NaturalPair("train-" + family + "-r" + str(replicate), *outcomes))
    return pairs


def _diagnostic_choices(rows, manifest, candidate):
    training = [r for r in rows if r["split"] == "train"]
    if not candidate or len(training) != 18 or any(r["evaluator_timeout"] for r in training):
        return {"status": "incomplete_or_timeout_excluded", "authority": "diagnostic_only_no_deployment"}
    mappings = [learning.FamilyMapping(f, manifest["tasks"][f]["train"]["task_id"],
        int(manifest["tasks"][f]["train"]["checkpoint"].rsplit("_", 1)[1]),
        int(manifest["tasks"][f]["evaluation"]["checkpoint"].rsplit("_", 1)[1]),
        _environment(manifest, f, "train"), _environment(manifest, f, "evaluation")) for f in manifest["families"]]
    result = {"status": "complete", "authority": "diagnostic_only_no_deployment"}
    for metric in ("primary", "secondary"):
        result[metric] = learning.choose_scopes(candidate["patch_ref"], candidate["origin"], mappings,
            _learning_pairs(rows, manifest, candidate["patch_ref"], metric),
            proposer_families=candidate["candidate"]["proposer_families"]).to_dict()
    return result


def _arm_report(rows, families, frozen):
    if frozen is None:
        return {"status": "awaiting_frozen_primary_P4", "arms": {}}
    arms = frozen["decisions"]["arms"]
    policies = frozen["decisions"]["policies"]
    if set(arms) != set(learning.POLICIES) or set(policies) != set(learning.POLICIES):
        raise MetricError("P4 must contain all six primary policy choices.")
    for policy, choices in arms.items():
        if (set(choices) != set(families) or any(type(v) is not bool for v in choices.values())
                or set(policies[policy]) - set(families)
                or choices != {f: f in policies[policy] for f in families}):
            raise MetricError("P4 arms disagree with frozen primary choices.")
    lookup = {(r["family"], r["replicate"], r["patch"]): r for r in rows if r["split"] == "evaluation"}
    reports = {}
    for policy, choices in arms.items():
        per_family = {}
        for family in families:
            values, missing, excluded = [], [], []
            deltas = {"primary": [], "secondary": []}
            for replicate in learning.REPLICATES:
                control = lookup.get((family, replicate, False))
                treatment = lookup.get((family, replicate, True))
                if control is None or treatment is None:
                    missing.append(replicate)
                    continue
                selected = treatment if choices[family] else control
                values.append({"replicate": replicate, "job_id": selected["job_id"],
                    "primary": selected["primary"], "secondary": selected["secondary"],
                    "primary_delta_vs_Static": float(_delta(selected, control, "primary")),
                    "secondary_delta_vs_Static": float(_delta(selected, control, "secondary")),
                    "excluded_timeout_pair": control["evaluator_timeout"] or treatment["evaluator_timeout"]})
                if values[-1]["excluded_timeout_pair"]:
                    excluded.append(replicate)
                else:
                    for metric in deltas:
                        deltas[metric].append(_delta(selected, control, metric))
            per_family[family] = {"patch": choices[family], "rows": values,
                "missing_replicates": missing, "excluded_timeout_replicates": excluded,
                "primary": _summary(deltas["primary"]), "secondary": _summary(deltas["secondary"])}
        complete = all(not f["missing_replicates"] and not f["excluded_timeout_replicates"] for f in per_family.values())
        reports[policy] = {"families": per_family, "complete": complete,
            "macro_primary_paired_delta": float(sum(Decimal(f["primary"]["mean_decimal"]) for f in per_family.values()) / len(families)) if complete else None,
            "macro_secondary_paired_delta": float(sum(Decimal(f["secondary"]["mean_decimal"]) for f in per_family.values()) / len(families)) if complete else None}
    return {"status": "frozen_primary_choices", "policy_sha256": frozen["sha256"],
        "selection_source": "primary P4 only; secondary diagnostic choices never used", "arms": reports}


def analyze_run(run_dir):
    """Read a real P0 manifest and existing outcome grades; write nothing.

    Partial runs are supported and explicitly pending. Invalid ordinary node
    inventories, counters, hashes or producer identities are rejected. Inputs
    are hashed from the bytes actually read; embedded grading attempts are
    cross-checked against their original main/main-retry files.
    """
    root = Path(run_dir).resolve()
    inputs = {}

    def read(path):
        path = Path(path)
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_relative_to(root):
            raise MetricError("Input reference leaves the specified run: " + str(path))
        raw = path.read_bytes()
        name = path.relative_to(root).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        if name in inputs and inputs[name] != sha:
            raise MetricError("Input changed while analyzing: " + name)
        inputs[name] = sha
        return json.loads(raw)

    envelope = read("manifest.json")
    manifest = envelope["manifest"]
    if _digest(manifest) != envelope["sha256"]:
        raise MetricError("P0 manifest hash differs.")
    families = manifest["families"]
    if (len(families) != 3 or len(set(families)) != 3 or manifest["n_tasks"] != 3
            or manifest["replicates"] != 3):
        raise MetricError("Expected three frozen tasks, each with three replicates.")
    chooser_sha = hashlib.sha256(Path(learning.__file__).read_bytes()).hexdigest()
    if chooser_sha != manifest["learning_contract"]["source_sha256"]:
        raise MetricError("Public choose_scopes producer differs from P0.")
    expected_jobs = {}
    for family in families:
        for split in ("train", "evaluation"):
            task = manifest["tasks"][family][split]
            nodes = _nodes(task["nodes"])
            collected = task["collection"]
            ids = [r["id"] for r in collected["tests"]]
            if (len(ids) != len(set(ids)) or set(ids) != set(nodes)
                    or collected["test_count"] != len(nodes) or collected["collect_only"] is not True
                    or collected["infrastructure_error"] is not False):
                raise MetricError("P0 node list disagrees with actual frozen collection.")
    for split in ("train", "evaluation"):
        jobs = manifest["condition_order"][split]
        expected = {(f, r, p) for f in families for r in learning.REPLICATES for p in (False, True)}
        if (len(jobs) != 18 or {(j["family"], j["replicate"], j["patch"]) for j in jobs} != expected):
            raise MetricError("P0 condition schedule is incomplete or duplicated.")
        for job in jobs:
            if job["split"] != split or job["job_id"] in expected_jobs:
                raise MetricError("P0 condition job identity differs.")
            expected_jobs[job["job_id"]] = job
    baselines, rows = {}, []

    def consume(row, directory, split):
        family = row["family"]
        task = manifest["tasks"][family]["evaluation" if split == "evaluation" else "train"]
        if row["checkpoint"] != task["checkpoint"] or row["task_id"] != task["task_id"]:
            raise MetricError("Outcome task/checkpoint disagrees with P0.")
        original = read(directory / "main.json")
        primary_path = Path(row["primary_grade"])
        primary_path = primary_path if primary_path.is_absolute() else root / primary_path
        if primary_path.resolve().parent != (root / directory).resolve() or primary_path.name not in {"main.json", "main-retry.json"}:
            raise MetricError("Primary grade is not this outcome's main/main-retry.json.")
        grade = read(primary_path)
        attempts = row["grader_attempts"]
        if (len(attempts) not in (1, 2) or attempts[0]["result"] != original
                or len(attempts) != (2 if original["infrastructure_error"] else 1)):
            raise MetricError("Grader attempts disagree with original main.json.")
        for attempt, name in zip(attempts, ("main.json", "main-retry.json")):
            if attempt["result"] != read(directory / name):
                raise MetricError("Embedded grader attempt disagrees with raw grade file.")
        if grade != attempts[-1]["result"] or primary_path.name != ("main-retry.json" if len(attempts) == 2 else "main.json"):
            raise MetricError("Effective main grade disagrees with final grader attempt.")
        timeout = row.get("evaluator_timeout") is True
        if timeout and (len(attempts) != 2 or not all(a["result"].get("timed_out") is True and
                a["result"].get("infrastructure_error") is True for a in attempts)):
            raise MetricError("Repeated evaluator timeout lacks two actual timed-out grader attempts.")
        if (grade["problem"] != family or grade["checkpoint"] != task["checkpoint"]
                or grade["source_commit"] != manifest["task_adapter"]["source_commit"]
                or grade["image_id"] != manifest["task_adapter"]["image_id"]):
            raise MetricError("Main grade producer/task identity differs from P0.")
        counts = count_grade(grade, task["nodes"], evaluator_timeout=timeout)
        if row["score"] != counts["primary"] or row.get("main") != grade:
            raise MetricError("Outcome primary score or embedded grade differs from actual main grade.")
        return {"job_id": row["job_id"], "split": split, "family": family,
            "replicate": row["replicate"], "patch": row["patch"], "task_id": row["task_id"],
            "checkpoint": row["checkpoint"], "initial_state_id": row["initial_state_id"],
            "episode_status": row.get("episode", {}).get("status"), **counts,
            "evidence_refs": ["manifest.json" if split == "baseline" else directory.as_posix() + "/outcome.json",
                primary_path.resolve().relative_to(root).as_posix()],
            "_grade": grade, "_nodes": task["nodes"]}

    for family in families:
        baseline = manifest["starter_acceptance_baselines"][family]
        task = manifest["tasks"][family]["train"]
        row = dict(baseline, family=family, checkpoint=task["checkpoint"], task_id=task["task_id"],
            job_id="starter-baseline-" + family, replicate=1, patch=False)
        baselines[family] = consume(row, Path("p0") / family / "starter-baseline", "baseline")
    seen = set()
    for path in sorted((root / "outcomes").glob("*/outcome.json")):
        row = read(path)
        if row["job_id"] != path.parent.name or row["family"] not in families:
            raise MetricError("Outcome path/job/family identity differs.")
        split = row["split"]
        if split == "discovery":
            expected = {"job_id": "discovery-" + row["family"], "split": "discovery",
                "family": row["family"], "replicate": 1, "patch": False}
        else:
            expected = expected_jobs.get(row["job_id"])
        if expected is None or any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items()):
            raise MetricError("Outcome is not an expected P0 job.")
        key = (split, row["family"], row["replicate"], row["patch"])
        if key in seen:
            raise MetricError("Duplicate outcome condition.")
        seen.add(key)
        result = consume(row, path.parent.relative_to(root), split)
        if split in ("discovery", "train") and result["initial_state_id"] != baselines[row["family"]]["initial_state_id"]:
            raise MetricError("Original starter identity changed.")
        rows.append(result)
    for split, filename in (("train", "train.json"), ("evaluation", "evaluation.json")):
        if (root / filename).exists():
            table = read(filename)
            if _digest(table["rows"]) != table["sha256"]:
                raise MetricError("Frozen " + split + " table hash differs.")
            source_rows = [read(Path("outcomes") / r["job_id"] / "outcome.json") for r in table["rows"]]
            if source_rows != table["rows"] or len(source_rows) != 18 or len({r["job_id"] for r in source_rows}) != 18:
                raise MetricError("Frozen condition table differs from original outcomes.")
    candidate = read("candidate.json") if (root / "candidate.json").exists() else None
    diagnostic = _diagnostic_choices(rows, manifest, candidate)
    frozen = read("policies.json") if (root / "policies.json").exists() else None
    if frozen is not None:
        if _digest(frozen["decisions"]) != frozen["sha256"]:
            raise MetricError("Frozen primary P4 hash differs.")
        if frozen["decisions"]["patch_ref"] != candidate["patch_ref"]:
            raise MetricError("Frozen primary P4 candidate differs.")
        if diagnostic["status"] == "complete":
            primary = diagnostic["primary"]
            if any(frozen["decisions"].get(k) != v for k, v in primary.items()):
                raise MetricError("Frozen primary choices differ from public chooser on the actual training rows.")
    family_reports = {}
    for family in families:
        splits = {split: _split_report(rows, family, split) for split in ("train", "evaluation")}
        comparison = {"classification_differs": None, "adaptive_choice_differs": None}
        if diagnostic["status"] == "complete":
            for metric in ("primary", "secondary"):
                record = diagnostic[metric]
                comparison[metric + "_classification"] = next(s["decision"] for s in record["statistics"] if s["task_family"] == family)
                comparison[metric + "_adaptive"] = family in record["policies"]["Adaptive"]
            comparison["classification_differs"] = comparison["primary_classification"] != comparison["secondary_classification"]
            comparison["adaptive_choice_differs"] = comparison["primary_adaptive"] != comparison["secondary_adaptive"]
        criteria = {"train_mean_sign_differs": splits["train"]["mean_sign_differs"],
            "evaluation_mean_sign_differs": splits["evaluation"]["mean_sign_differs"],
            "training_classification_differs": comparison["classification_differs"],
            "training_adaptive_choice_differs": comparison["adaptive_choice_differs"]}
        verdict = True if any(v is True for v in criteria.values()) else False if all(v is False for v in criteria.values()) else None
        family_reports[family] = {**splits, "training_choice_comparison": comparison,
            "skipped_in_train_or_evaluation": any(r["skipped"] > 0 for r in rows if r["family"] == family and r["split"] in splits),
            "criteria": criteria, "metric_sensitive_untrustworthy": verdict,
            "status": "metric_sensitive_untrustworthy" if verdict else "consistent" if verdict is False else "incomplete"}
    discovery = {}
    for row in rows:
        if row["split"] != "discovery":
            continue
        baseline = baselines[row["family"]]
        transitions = None if row["evaluator_timeout"] or baseline["evaluator_timeout"] else compare_nodes(baseline["_grade"], row["_grade"], row["_nodes"])
        discovery[row["family"]] = {"baseline_job_id": baseline["job_id"], "discovery_job_id": row["job_id"],
            "primary_delta": float(_delta(row, baseline, "primary")),
            "secondary_delta": float(_delta(row, baseline, "secondary")), "node_transitions": transitions,
            "authority": "starter-to-discovery description; not a treatment-control replicate pair"}
    public_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in [*baselines.values(), *rows]]
    return {"schema": "scope-readonly-metric-sensitivity-v1", "manifest_sha256": envelope["sha256"],
        "n_tasks": 3, "replicates": [1, 2, 3], "secondary_definition": "passed / fixed P0 collected; skipped count as nonpass",
        "authority": "read_only_diagnostic; never model input, policy deployment, or new grading",
        "sign_rule": "mean Decimal(str(score)) paired deltas; zero distinct; no epsilon",
        "rows": public_rows, "discovery": discovery, "families": family_reports,
        "training_diagnostic_choices": diagnostic, "frozen_primary_evaluation": _arm_report(rows, families, frozen),
        "input_sha256": inputs, "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "public_chooser_source_sha256": chooser_sha}
