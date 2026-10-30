"""Decode existing SKP bytes in CI; scene/trace failures stay separate and intact."""
from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import time

from contract import (archive_build_compatibility, browser_binding, inventory_pictures, read_json, require_ci,
                      require_archive_batch, require_existing_batch, select_picture, write_json)


def retain_original_receipts(case: Path, output: Path) -> None:
    original = output / "original"
    original.mkdir()
    for name in ("browser.json", "pictures.json", "trace.json", "trace-diagnostics.json", "trace-complete.json",
                 "trace-markers.json", "layer-snapshots.json", "layer-events.json", "layer-boundaries.json",
                 "layer-document.json", "trace-config.json", "target.json", "layout-metrics.json", "scene.png",
                 "producer-smb-request.json", "producer-smb-receipt.json", "trace-category-selection.json",
                 "diagnostic.json", "progress.json"):
        path = case / name
        if path.exists():
            shutil.copyfile(path, original / name)
    if (case / "layer-snapshots").is_dir():
        shutil.copytree(case / "layer-snapshots", original / "layer-snapshots")


def decode_one(executable: Path, picture: Path, output: Path, *, require_text: bool) -> dict:
    """One bounded attempt; caller continues after failure and keeps raw output."""
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"status": "started", "started_unix": time.time(), "errors": [], "canonical_output": False,
               "final_png_attribution": None, "dom_source_attribution": None}
    try:
        if (output / "raw.json").exists() or (output / "decode.json").exists():
            raise RuntimeError("Unique output contains an earlier decode; no stale result can be accepted")
        command = [str(executable.resolve()), str(picture.resolve()), str(output.resolve())]
        receipt["argv"] = command
        write_json(output / "decode.json", receipt)
        with (output / "stdout.log").open("w", encoding="utf-8") as stdout, \
                (output / "stderr.log").open("w", encoding="utf-8") as stderr:
            receipt["subprocess_run_attempted"] = True
            write_json(output / "decode.json", receipt)
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120, check=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        receipt["exit_code"] = result.returncode
        raw = read_json(output / "raw.json")
        receipt["raw_status"] = raw.get("status")
        receipt["raw_errors"] = raw.get("errors")
        receipt["blob_count"] = len(raw.get("draw_text_blobs", []))
        receipt["font_count"] = len(raw.get("typefaces", []))
        if result.returncode or raw.get("status") != "decoded" or raw.get("errors"):
            raise RuntimeError("Actual SKP decode failed; original raw evidence remains in this unique output")
        if require_text and not receipt["blob_count"]:
            raise RuntimeError("This explicitly selected one-picture diagnostic yielded no actual text blob records")
        receipt["status"] = "decoded-diagnostic-only"
        receipt["text_result"] = "actual-text-blobs-recorded" if receipt["blob_count"] else "decoded-no-text-blobs"
    except Exception as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["status"] = "failed"
    finally:
        receipt["finished_unix"] = time.time()
        write_json(output / "decode.json", receipt)
    return receipt


def decode_all_unique(case: Path, executable: Path, output: Path, inventory: dict) -> dict:
    """Attempt every verified unique byte sequence, including failures/no-text.

    main() validates the fixed original or explicit archive inventory first.
    Pure tests supply explicit synthetic inventories and mock subprocess.run.
    """
    result = {"status": "started", "started_unix": time.time(), "completed": False,
              "canonical_output": False, "dom_source_attribution": None, "final_png_attribution": None,
              "inventory_file": "inventory.json", "original_trace_file": "original/trace.json",
              "trace_completeness_proven": False, "original_input_counts": copy.deepcopy(inventory["counts"]),
              "original_picture_extraction_errors": copy.deepcopy(inventory["original_picture_extraction_errors"]),
              "trace_diagnostics": copy.deepcopy(inventory["trace_diagnostics"]), "unique_results": [], "errors": []}
    for item in inventory["unique_inputs"]:
        relative = f"unique/{item['unique_index']:04d}-{item['sha256']}"
        result["unique_results"].append({**copy.deepcopy(item), "output_directory": relative,
                                         "retained_input": relative + "/input.skp", "status": "not-attempted"})
    write_json(output / "batch.json", result)
    for item in result["unique_results"]:
        item["status"] = "started"
        write_json(output / "batch.json", result)
        directory = output / item["output_directory"]
        try:
            directory.mkdir(parents=True)
            picture = case / item["representative_file"]
            retained = directory / "input.skp"
            shutil.copyfile(picture, retained)
            data = retained.read_bytes()
            if len(data) != item["byte_count"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("Actual input changed between inventory binding and retained decode input")
            decode = decode_one(executable, retained, directory, require_text=False)
            item.update(status=decode["status"], decode=decode)
            if decode["status"] != "decoded-diagnostic-only":
                result["errors"].append({"unique_index": item["unique_index"], "errors": copy.deepcopy(decode["errors"])})
        except Exception as exc:
            item.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            result["errors"].append({"unique_index": item["unique_index"], "error": item["error"]})
        write_json(output / "batch.json", result)
    result["attempted_count"] = len(result["unique_results"])
    result["decoder_call_attempt_count"] = sum(item.get("decode", {}).get("subprocess_run_attempted") is True
                                                for item in result["unique_results"])
    result["decoded_count"] = sum(item["status"] == "decoded-diagnostic-only" for item in result["unique_results"])
    result["failed_count"] = sum(item["status"] == "failed" for item in result["unique_results"])
    result["decoded_no_text_count"] = sum(item.get("decode", {}).get("text_result") == "decoded-no-text-blobs"
                                            for item in result["unique_results"])
    result["completed"] = True
    result["status"] = "completed-diagnostic-only" if not result["errors"] else "completed-with-decode-failures"
    result["finished_unix"] = time.time()
    write_json(output / "batch.json", result)
    return result


def main() -> int:
    require_ci()
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--picture", help="Exact original pictures.json file field")
    selection.add_argument("--all-unique", action="store_true", help="All 118 unique byte sequences in the existing 81e93ac/group capture")
    selection.add_argument("--archive-all-unique", action="store_true",
                           help="All original trace payloads in this explicitly supplied archived case; no fixed historical counts")
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("This diagnostic only supports Windows capture factory decoding")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("raw.json", "diagnostic.json", "batch.json", "inventory.json", "original", "unique")):
        raise RuntimeError("Output contains an earlier attempt; keep it unchanged and use a new output directory")
    receipt = {"status": "started", "started_unix": time.time(), "errors": [],
               "original_case_path": str(args.case.resolve()),
               "selection_mode": "archive-all-unique" if args.archive_all_unique else "historical-fixed-or-single",
               "canonical_output": False, "final_png_attribution": None, "dom_source_attribution": None}
    try:
        # Preserve the actual archived receipts even if compatibility fails.
        retain_original_receipts(args.case, output)
        build = read_json(args.build / "build.json")
        binding = browser_binding(read_json(args.case / "browser.json"),
                                  (args.build / "chromium.DEPS").read_text(encoding="utf-8"))
        if args.archive_all_unique:
            compatibility = archive_build_compatibility(build, binding, args.build, Path(__file__).parent)
            receipt["build_compatibility"] = compatibility
            write_json(output / "build-compatibility.json", compatibility)
            if compatibility["status"] != "compatible-decoder-build":
                raise ValueError("Actual archived capture and decoder build are not proven compatible")
        elif build.get("status") != "built" or build.get("source_binding") != binding:
            raise ValueError("Build and actual capture source bindings disagree")
        receipt["source_binding"] = binding
        # These are original receipts, not interpreted as final-frame ownership proof.
        write_json(output / "diagnostic.json", receipt)
        executable = (args.build / build["executable"]).resolve()
        if args.all_unique or args.archive_all_unique:
            inventory = inventory_pictures(args.case)
            write_json(output / "inventory.json", inventory)
            if args.archive_all_unique:
                require_archive_batch(inventory)
            else:
                require_existing_batch(inventory)
            batch = decode_all_unique(args.case, executable, output, inventory)
            receipt["batch_file"] = "batch.json"
            receipt["batch_status"] = batch["status"]
            receipt["decoded_count"] = batch["decoded_count"]
            receipt["failed_count"] = batch["failed_count"]
            if batch["errors"]:
                raise RuntimeError("One or more unique SKPs failed; every unique attempt and all original aliases were retained")
        else:
            picture, picture_receipt = select_picture(args.case, args.picture)
            receipt["picture"] = picture_receipt
            shutil.copyfile(picture, output / "original" / picture.name)
            decode = decode_one(executable, picture, output, require_text=True)
            receipt["decode"] = decode
            if decode["status"] != "decoded-diagnostic-only":
                raise RuntimeError("Actual selected SKP decode failed; inspect its preserved decode.json/raw.json")
        receipt["status"] = "decoded-diagnostic-only"
    except Exception as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["status"] = "failed"
    finally:
        receipt["finished_unix"] = time.time()
        write_json(output / "diagnostic.json", receipt)
    return 0 if receipt["status"] == "decoded-diagnostic-only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
