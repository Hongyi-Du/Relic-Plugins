"""CI macOS viewport processes and fail-closed aggregation of native receipts.

This module never starts an app itself. The caller supplies the existing owned
process runner, with its unchanged timeouts, progress monitor and cleanup.
"""
from collections import Counter
import json
import os
from pathlib import Path
import traceback


def viewport_shards(manifest):
    """Keep each original case and the first-occurrence viewport order."""
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("macOS capture manifest has no cases")
    groups, seen = {}, set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("macOS capture requires unique nonempty case IDs")
        if "/" in case_id or "\\" in case_id or case.get("file") != case_id + ".png":
            raise ValueError("macOS capture case filename must retain its original case ID")
        size = case.get("width"), case.get("height")
        if any(type(value) is not int or value <= 0 for value in size):
            raise ValueError("macOS capture viewport must have positive integer dimensions")
        seen.add(case_id)
        groups.setdefault(size, []).append(case)
    return [(size, cases) for size, cases in groups.items()]


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read(path, errors, label):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        errors.append(label + ": " + str(error))
        return None


def _collect_shard(directory, cases, output, launched, returned, execution_error):
    expected = {case["id"]: case for case in cases}
    errors, attempted = [], set()
    source = _read(directory / "complete.json", errors, "Invalid native complete receipt") if launched else None
    progress = _read(directory / "progress-observations.json", errors, "Invalid native progress receipt") if launched else None
    last = directory / "current-case.txt"
    last_progress = last.read_text(encoding="utf-8-sig").strip() if launched and last.is_file() else None
    if last_progress in expected:
        attempted.add(last_progress)
    if progress is not None:
        if not isinstance(progress, list):
            errors.append("Native progress observations are not an array")
        else:
            for row in progress:
                if isinstance(row, dict) and isinstance(row.get("case_id"), str) and row["case_id"] in expected and row.get("text") == row["case_id"]:
                    attempted.add(row["case_id"])
    if execution_error:
        errors.append(execution_error)
    if source is None:
        errors.append("Missing native complete receipt; partial files are diagnostic only")
    elif not isinstance(source, dict):
        errors.append("Native complete receipt is not an object")
        source = {"invalid_source": source}
    if returned is not None and returned != source:
        errors.append("Returned native receipt differs from the process's complete.json")
    rows = source.get("cases") if source else None
    source_errors = source.get("errors") if source else None
    if source:
        if not isinstance(source_errors, list) or any(not isinstance(error, str) for error in source_errors):
            errors.append("Native complete errors must be an array of strings")
            source_errors = []
        errors.extend("Native error: " + error for error in source_errors)
        if not isinstance(rows, list):
            errors.append("Native complete cases must be an array")
            rows = []
        if type(source.get("count")) is not int or source["count"] != len(rows):
            errors.append("Native complete count differs from its actual results array")
    else:
        rows, source_errors = [], []
    counts = Counter(row.get("id") for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str))
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            errors.append("Invalid case row in native complete receipt")
            continue
        case_id = row["id"]
        if case_id not in expected:
            errors.append("Unexpected case ID in native complete receipt: " + case_id)
            continue
        attempted.add(case_id)
        by_id.setdefault(case_id, []).append(row)
    actual_order = [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] in expected]
    expected_order = [case["id"] for case in cases if case["id"] in actual_order]
    if actual_order != expected_order:
        errors.append("Native complete case IDs are duplicated or out of manifest order")
    result = []
    for case in cases:
        case_id = case["id"]
        evidence_files = {"png": (output / case["file"]).is_file(),
                          "elements": (output / (case_id + ".elements.json")).is_file()}
        failure = _read(output / (case_id + ".capture-error.json"), errors, case_id + " invalid error receipt") if launched else None
        if isinstance(failure, dict) and isinstance(failure.get("error"), str) and failure["error"].startswith(case_id + ": "):
            attempted.add(case_id)
        if any(error.startswith(case_id + ": ") for error in source_errors):
            attempted.add(case_id)
        case_sources = by_id.get(case_id, [])
        entry = {"case_id": case_id, "file": case["file"], "status": "not-attempted",
                 "source_results": case_sources, "artifacts_present": evidence_files,
                 "capture_error_receipt": failure, "errors": []}
        if counts.get(case_id, 0) != 1:
            entry["errors"].append("Missing case result" if not case_sources else "Duplicate case results")
        else:
            row = case_sources[0]
            entry["source_status"] = row.get("status")
            if row.get("file") != case["file"]:
                entry["errors"].append("Native result filename differs from original manifest")
            if row.get("status") != "captured":
                entry["errors"].append("Native status is not captured: " + str(row.get("status")))
            if row.get("error") or failure or any(error.startswith(case_id + ": ") for error in source_errors):
                entry["errors"].append("Native case has an explicit failure receipt")
            if not all(evidence_files.values()):
                entry["errors"].append("Native captured result is missing PNG or elements")
            if not entry["errors"]:
                entry["status"] = "captured"
        entry["attempted"] = case_id in attempted
        if entry["status"] != "captured" and entry["attempted"]:
            entry["status"] = "failed-state-captured" if entry.get("source_status") == "failed-state-captured" else "failed"
        errors.extend(case_id + ": " + error for error in entry["errors"])
        result.append(entry)
    return {"native_receipt": source, "returned_receipt": returned, "last_progress": last_progress,
            "progress_observations": progress, "cases": result, "errors": errors,
            "count": sum(row["status"] == "captured" for row in result),
            "attempted_count": sum(row["attempted"] for row in result)}


def capture_shards(manifest_path, manifest, exe, run_process):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("macOS viewport capture is CI-only; no local process is launched.")
    shards = viewport_shards(manifest)
    output = Path(manifest["output"])
    aggregate = {"client": "macos", "mode": "independent-viewport-processes", "expected_count": len(manifest["cases"]),
                 "attempted_count": 0, "count": 0, "shards": [], "cases": [], "errors": [],
                 "attempted_count_quantity": "Distinct expected case IDs witnessed in native results, progress or explicit error receipts; never inferred from PNG presence",
                 "count_quantity": "Unique native captured results with their original PNG and elements files; not element parity acceptance"}
    by_id = {}
    for size, cases in shards:
        name = f"{size[0]}x{size[1]}"
        directory = manifest_path.parent / "viewports" / name
        entry = {"viewport": {"width": size[0], "height": size[1]}, "directory": str(directory),
                 "case_ids": [case["id"] for case in cases], "expected_count": len(cases), "process_invoked": False}
        returned, execution_error, created = None, None, False
        try:
            # Never reuse an old manifest, complete, progress or output file.
            # Refuse it in place; it remains available for diagnosis.
            directory.mkdir(parents=True)
            created = True
            stale = [path.name for case in cases for path in output.glob(case["id"] + ".*")]
            if stale:
                raise RuntimeError("Refusing stale native viewport output: " + ", ".join(stale))
            per_shard = dict(manifest, cases=cases)
            path = directory / "manifest.json"
            _save(path, per_shard)
            print("macOS viewport capture: " + name + f" ({len(cases)} cases)", flush=True)
            entry["process_invoked"] = True
            returned = run_process(path, per_shard, exe)
        except Exception as error:
            execution_error = type(error).__name__ + ": " + str(error)
            if created:
                (directory / "capture-exception.log").write_text(traceback.format_exc(), encoding="utf-8")
            print("macOS viewport capture failed: " + name + ": " + execution_error, flush=True)
        collected = _collect_shard(directory, cases, output, entry["process_invoked"], returned, execution_error)
        entry.update(collected)
        if created:
            entry["cleanup_receipt"] = _read(directory / "process-exit.json", entry["errors"], "Invalid native cleanup receipt")
            if entry["process_invoked"] and entry["cleanup_receipt"] is None:
                entry["errors"].append("Missing owned native process cleanup receipt")
            elif isinstance(entry["cleanup_receipt"], dict) and entry["cleanup_receipt"].get("error"):
                entry["errors"].append("Owned native process cleanup failed: " + entry["cleanup_receipt"]["error"])
        entry["status"] = "failed" if entry["errors"] else "captured"
        aggregate["shards"].append(entry)
        aggregate["errors"].extend(name + ": " + error for error in entry["errors"])
        by_id.update({row["case_id"]: row for row in entry["cases"]})
        aggregate["cases"] = [by_id[case["id"]] for case in manifest["cases"] if case["id"] in by_id]
        aggregate["count"] = sum(row["status"] == "captured" for row in aggregate["cases"])
        aggregate["attempted_count"] = sum(row["attempted"] for row in aggregate["cases"])
        _save(manifest_path.parent / "complete.json", aggregate)
    return aggregate
