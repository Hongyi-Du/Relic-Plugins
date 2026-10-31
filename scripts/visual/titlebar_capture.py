"""CI-only full native window captures, including operating-system chrome."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from capture import HERE, ROOT, configure, stop_native_process, wait_file
from relic_core.process import creation_flags


def capture_case(exe, output, fixture, client, theme, width, height, logical_sizing=False):
    case_id = f"{client}-zh-CN-{theme}-{width}x{height}-group"
    work = output / "data" / case_id
    work.mkdir(parents=True)
    state = work / "state"
    state.mkdir()
    case = {"id": case_id, "scene": "group", "width": width, "height": height, "file": case_id + ".png"}
    manifest = {"version": 1, "client": client, "lang": "zh-CN", "theme": theme,
                "capture_mode": "whole-window", "fixture": fixture, "output": str(output),
                "state_directory": str(state), "cases": [case]}
    if logical_sizing:
        manifest["window_units"] = "dip" if client == "windows" else "point"
    path = work / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    env = dict(os.environ, RELIC_TITLEBAR_CAPTURE="1", RELIC_VISUAL_MANIFEST=str(path),
               RELIC_VISUAL_OUTPUT=str(output), RELIC_VISUAL_STATE_DIR=str(state),
               RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable, RELIC_HOME=fixture["home"],
               RELIC_VISUAL_NOW=fixture["clock"], TZ="UTC")
    row = {"case": case, "status": "failed", "errors": []}
    with (work / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=log, creationflags=creation_flags())
        try:
            receipt = wait_file(work / "complete.json", process, timeout=150)
            row["native_receipt"] = receipt
            if receipt.get("errors") or receipt.get("count") != 1:
                raise RuntimeError("Native whole-window capture did not complete: " + str(receipt))
            from PIL import Image
            with Image.open(output / case["file"]) as image:
                image.load()
                row["png"] = {"file": case["file"], "width": image.width, "height": image.height, "format": image.format}
                if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                    raise ValueError("Whole-window screenshot is not a nonempty PNG")
                if client == "windows" and not logical_sizing and image.size != (width, height):
                    raise ValueError("Windows PNG does not cover the requested full window rectangle")
            chrome_path = output / (case_id + ".window-chrome.json")
            row["window_chrome"] = json.loads(chrome_path.read_text(encoding="utf-8-sig"))
            row["status"] = "captured"
        except Exception as error:
            row["errors"].append(str(error))
        finally:
            row["cleanup"] = stop_native_process(process)
            (work / "driver-receipt.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Full-window screenshots are CI-only; nothing is launched locally.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("windows", "macos"), required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-sizing", action="store_true",
                        help="Request DIP/point sizes and retain actual startup-placement receipts")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = output / "fixture"
    data.mkdir()
    results = []
    with (data / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-X", "utf8", str(HERE / "serve.py"),
                                   "--output", str(data), "--lang", "zh-CN"],
                                  stdout=log, stderr=log, creationflags=creation_flags())
        try:
            fixture = wait_file(data / "fixture.json", server)
            fixture["clock"] = "2026-10-29T11:02:00Z"
            for theme in ("light", "dark"):
                configure(fixture, lang="zh-CN", theme=theme, font="medium", density="comfortable", notify=False)
                for width, height in ((1440, 900), (1024, 700)):
                    print(f"Whole-window capture: {args.client} {theme} {width}x{height}", flush=True)
                    results.append(capture_case(args.exe.resolve(), output, fixture, args.client, theme, width, height,
                                                args.window_sizing))
                    (output / ("window-report.json" if args.window_sizing else "titlebar-report.json")).write_text(json.dumps({
                        "commit": os.environ.get("GITHUB_SHA"), "client": args.client,
                        "capture": "complete native window with system caption controls", "expected": 4,
                        "requested_units": "logical" if args.window_sizing else "platform",
                        "captured": sum(row["status"] == "captured" for row in results), "cases": results},
                        ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            stop_native_process(server)
    if len(results) != 4 or any(row["status"] != "captured" for row in results):
        raise RuntimeError("Full-window screenshot collection failed; see titlebar-report.json and retained logs")


if __name__ == "__main__":
    main()
