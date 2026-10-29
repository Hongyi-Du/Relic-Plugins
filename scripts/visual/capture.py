"""Capture the real reference/native UI in CI; no local execution is permitted."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def wait_file(path, process, timeout=60, on_tick=None):
    end = time.monotonic() + timeout
    progress_file = path.parent / "current-case.txt" if path.name == "complete.json" else None
    current_case, last_progress = "", time.monotonic()
    while time.monotonic() < end:
        if on_tick:
            on_tick()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
        if process.poll() is not None:
            raise RuntimeError(f"Process exited {process.returncode}; missing {path}")
        if progress_file and progress_file.exists():
            case = progress_file.read_text(encoding="utf-8-sig").strip()
            if case and case != current_case:
                current_case, last_progress = case, time.monotonic()
                print("Native capture: " + case, flush=True)
            elif current_case and time.monotonic() - last_progress > 90:
                raise TimeoutError("Native capture did not advance for 90 seconds: " + current_case)
        time.sleep(.2)
    raise TimeoutError(str(path))


def configure(fixture, **changes):
    request = urllib.request.Request(f"http://127.0.0.1:{fixture['port']}/api/prefs", data=json.dumps(changes).encode(), headers={"Content-Type": "application/json", "X-Relic-Token": fixture["token"]})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def reference(manifest):
    from playwright.sync_api import sync_playwright
    source = (ROOT / "plugins/relic/app/static/app.js").read_text(encoding="utf-8")
    at = source.rfind("})();")
    assert at > 0
    source = source[:at] + (HERE / "reference-hook.js").read_text(encoding="utf-8") + source[at:]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        for case in manifest["cases"]:
            print("Reference capture: " + case["id"], flush=True)
            page = browser.new_page(viewport={"width": case["width"], "height": case["height"]}, device_scale_factor=1, locale=manifest["lang"], color_scheme=manifest["theme"], timezone_id="UTC")
            page.clock.set_fixed_time(manifest["fixture"]["clock"])
            page.route("**/app.js", lambda route: route.fulfill(body=source, content_type="application/javascript"))
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{manifest['fixture']['port']}/", wait_until="domcontentloaded")
            page.wait_for_function("typeof window.__relicVisual === 'function' && document.querySelector('#stream-inner')?.children.length > 0")
            page.evaluate("([scene, fixture]) => window.__relicVisual(scene, fixture)", [case["scene"], manifest["fixture"]])
            if case["scene"] == "documents":
                # Exercise the production selection handler and its real GET.
                page.locator(".details .left .chat-row").first.click()
                page.locator(".details .doc-body").wait_for(state="visible")
            page.wait_for_timeout(700)
            page.mouse.move(case["width"] + 20, case["height"] + 20)
            page.screenshot(path=Path(manifest["output"]) / case["file"], animations="disabled")
            cdp = page.context.new_cdp_session(page)
            snapshot = cdp.send("DOMSnapshot.captureSnapshot", {"computedStyles": [], "includePaintOrder": True, "includeDOMRects": True})
            ax_tree = cdp.send("Accessibility.getFullAXTree")
            evidence = Path(manifest["output"]) / (case["id"] + ".dom.json")
            evidence.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            (Path(manifest["output"]) / (case["id"] + ".ax.json")).write_text(json.dumps(ax_tree, ensure_ascii=False), encoding="utf-8")
            extractor = (HERE / "reference-elements.js").read_text(encoding="utf-8")
            elements = page.evaluate(extractor, {"scene_id": case["id"], "lang": manifest["lang"], "theme": manifest["theme"], "dom_snapshot": snapshot, "ax_tree": ax_tree})
            (Path(manifest["output"]) / (case["id"] + ".elements.json")).write_text(json.dumps(elements, ensure_ascii=False), encoding="utf-8")
            cdp.detach()
            if errors:
                raise RuntimeError(f"{case['id']}: {errors}")
            page.close()
        browser.close()


def native(manifest_path, manifest, exe):
    environment = dict(os.environ, RELIC_VISUAL_MANIFEST=str(manifest_path), RELIC_VISUAL_OUTPUT=manifest["output"], RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable, RELIC_HOME=manifest["fixture"]["home"], RELIC_VISUAL_NOW=manifest["fixture"]["clock"], TZ="UTC")
    if manifest["client"] == "windows":
        (manifest_path.parent / "current-case.txt").write_text("startup: launching native executable", encoding="utf-8")
    with (manifest_path.parent / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=environment, stdout=log, stderr=log)
        last_request = ""
        def capture_elements():
            nonlocal last_request
            if manifest["client"] != "windows":
                return
            request_path = manifest_path.parent / "elements-request.json"
            if not request_path.exists():
                return
            request = json.loads(request_path.read_text(encoding="utf-8-sig"))
            if request["case_id"] == last_request:
                return
            last_request = request["case_id"]
            output = Path(manifest["output"])
            raw = output / (last_request + ".uia.json")
            try:
                result = subprocess.run([manifest["uia_exe"], "--request", str(request_path), "--output", str(raw)], timeout=75, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(f"UIA extractor exited {result.returncode}: {result.stderr}")
            except Exception as error:
                partial = json.loads(raw.read_text(encoding="utf-8-sig")) if raw.exists() else {"raw_nodes": []}
                partial.setdefault("extraction_errors", []).append(str(error))
                raw.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
            from windows_elements import project
            try:
                projected = project(output / (last_request + ".xaml.json"), raw, output / (last_request + ".png"))
            except Exception as error:
                projected = {"schema_version": 1, "scene_id": last_request, "client": "windows", "viewport": {"width": request["width"], "height": request["height"], "scale": 1}, "elements": [], "extraction_errors": ["Projection failed: " + str(error)]}
            (output / (last_request + ".elements.json")).write_text(json.dumps(projected, ensure_ascii=False), encoding="utf-8")
            receipt = manifest_path.parent / "elements-complete.json"
            receipt.with_suffix(".tmp").write_text(json.dumps({"case_id": last_request}), encoding="utf-8")
            receipt.with_suffix(".tmp").replace(receipt)
        try:
            receipt = wait_file(manifest_path.parent / "complete.json", process, timeout=1200, on_tick=capture_elements)
            if receipt.get("errors"):
                raise RuntimeError(str(receipt["errors"]))
            for case in manifest["cases"]:
                if not (Path(manifest["output"]) / case["file"]).exists():
                    raise RuntimeError("Missing native screenshot: " + case["id"])
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Visual capture is CI-only; no app is opened locally.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", choices=["reference", "windows", "macos"], required=True)
    parser.add_argument("--matrix", choices=["smoke", "full"], default="full")
    parser.add_argument("--lang", choices=["zh-CN", "en-US"])
    parser.add_argument("--theme", choices=["light", "dark"])
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--uia-exe", type=Path, help="Independent Windows UIA reader; CI only")
    parser.add_argument("--reference", action="store_true", help="Capture reference against this exact native fixture/server on the Windows runner")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scenes = spec["scenes"] if args.matrix == "full" else ["group", "private", "overview", "settings-appearance", "new-org", "copies", "chart"]
    languages = [args.lang] if args.lang else spec["languages"] if args.matrix == "full" else ["zh-CN"]
    themes = [args.theme] if args.theme else spec["themes"] if args.matrix == "full" else ["light"]
    sizes = spec["sizes"] if args.matrix == "full" else [[1440, 900]]
    for lang in languages:
        data = output / "data" / lang
        data.mkdir(parents=True, exist_ok=True)
        with (data / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-X", "utf8", str(HERE / "serve.py"), "--output", str(data), "--lang", lang], stdout=log, stderr=log)
            try:
                fixture = wait_file(data / "fixture.json", server)
                zh = lang == "zh-CN"
                fixture.update(clock="2026-10-29T11:02:00Z", quote="先看页面，再判断是否完成。" if zh else "Look at the screens before calling them done.", plain="请对照截图检查布局与文字，再提交验收。" if zh else "Compare the layout and wording before submitting for review.", digest={"text": "团队正在核对原生界面。设计师整理视觉问题，工程师准备跨平台截图；权限与负责人安排等待您决定。" if zh else "The team is reviewing the native interface. Design is collecting visual issues and engineering is preparing cross-platform screenshots. Permissions and the integration lead await your decision.", "at": datetime.datetime(2026, 10, 29, 11, 2, tzinfo=datetime.timezone.utc).timestamp(), "count": 5, "last_id": 999})
                for theme in themes:
                    configure(fixture, lang=lang, theme=theme)
                    work = data / theme
                    work.mkdir(exist_ok=True)
                    cases = [{"id": f"{lang}-{theme}-{width}x{height}-{scene}", "scene": scene, "width": width, "height": height, "file": f"{lang}-{theme}-{width}x{height}-{scene}.png"} for width, height in sizes for scene in scenes]
                    manifest = {"version": 1, "client": args.client, "lang": lang, "theme": theme, "fixture": fixture, "output": str(output), "cases": cases}
                    if args.client == "windows":
                        if not args.uia_exe:
                            raise ValueError("Windows capture requires the independent --uia-exe reader")
                        manifest["uia_exe"] = str(args.uia_exe.resolve())
                    path = work / "manifest.json"
                    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    if args.reference:
                        reference_output = output.parent / "reference"
                        reference_output.mkdir(exist_ok=True)
                        reference(dict(manifest, client="reference", output=str(reference_output)))
                    if args.client == "reference":
                        reference(manifest)
                    else:
                        if not args.exe:
                            raise ValueError("Native capture needs --exe")
                        native(path, manifest, args.exe.resolve())
            finally:
                server.terminate()
                server.wait(timeout=20)
    receipt_name = "capture-complete" + ("-" + args.lang + "-" + args.theme if args.lang and args.theme else "") + ".json"
    (output / receipt_name).write_text(json.dumps({"client": args.client, "matrix": args.matrix, "count": len(scenes) * len(sizes) * len(languages) * len(themes)}), encoding="utf-8")
    if args.reference:
        (output.parent / "reference" / receipt_name).write_text(json.dumps({"client": "reference", "matrix": args.matrix, "count": len(scenes) * len(sizes) * len(languages) * len(themes)}), encoding="utf-8")


if __name__ == "__main__":
    main()
