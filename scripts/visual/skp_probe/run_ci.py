"""Decode one existing SKP; the original scene/trace failures remain separate and intact."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

from contract import browser_binding, read_json, require_ci, select_picture, write_json


def main() -> int:
    require_ci()
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--picture", required=True, help="Exact original pictures.json file field")
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("This diagnostic only supports Windows capture factory decoding")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"status": "started", "started_unix": time.time(), "errors": [],
               "canonical_output": False, "final_png_attribution": None, "dom_source_attribution": None}
    try:
        if (output / "raw.json").exists():
            raise RuntimeError("Output already contains a raw result; do not confuse a stale decode with this attempt")
        build = read_json(args.build / "build.json")
        binding = browser_binding(read_json(args.case / "browser.json"),
                                  (args.build / "chromium.DEPS").read_text(encoding="utf-8"))
        if build.get("status") != "built" or build.get("source_binding") != binding:
            raise ValueError("Build and actual capture source bindings disagree")
        picture, picture_receipt = select_picture(args.case, args.picture)
        receipt.update(source_binding=binding, picture=picture_receipt)
        # These are original receipts, not interpreted as final-frame ownership proof.
        original = output / "original"
        original.mkdir(exist_ok=True)
        for name in ("browser.json", "pictures.json", "trace-diagnostics.json", "layer-snapshots.json",
                     "layer-events.json", "trace-config.json"):
            path = args.case / name
            if path.exists():
                shutil.copyfile(path, original / name)
        shutil.copyfile(picture, original / picture.name)
        write_json(output / "diagnostic.json", receipt)
        command = [str((args.build / build["executable"]).resolve()), str(picture.resolve()), str(output)]
        receipt["argv"] = command
        with (output / "stdout.log").open("w", encoding="utf-8") as stdout, \
                (output / "stderr.log").open("w", encoding="utf-8") as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=120, check=False,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        receipt["exit_code"] = result.returncode
        raw = read_json(output / "raw.json")
        receipt["raw_status"] = raw.get("status")
        receipt["raw_errors"] = raw.get("errors")
        receipt["blob_count"] = len(raw.get("draw_text_blobs", []))
        receipt["font_count"] = len(raw.get("typefaces", []))
        if result.returncode or raw.get("status") != "decoded" or raw.get("errors"):
            raise RuntimeError("Actual SKP decode failed; inspect preserved raw evidence")
        if not receipt["blob_count"]:
            raise RuntimeError("This selected diagnostic yielded no actual text blob records")
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
