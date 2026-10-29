"""Capture the real reference/native UI in CI; no local execution is permitted."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def wait_file(path, process, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
        if process.poll() is not None:
            raise RuntimeError(f"Process exited {process.returncode}; missing {path}")
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
            page = browser.new_page(viewport={"width": case["width"], "height": case["height"]}, device_scale_factor=1, locale=manifest["lang"], color_scheme=manifest["theme"])
            page.route("**/app.js", lambda route: route.fulfill(body=source, content_type="application/javascript"))
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{manifest['fixture']['port']}/", wait_until="domcontentloaded")
            page.wait_for_function("typeof window.__relicVisual === 'function' && document.querySelector('#stream-inner')?.children.length > 0")
            page.evaluate("([scene, fixture]) => window.__relicVisual(scene, fixture)", [case["scene"], manifest["fixture"]])
            page.wait_for_timeout(700)
            page.screenshot(path=Path(manifest["output"]) / case["file"], animations="disabled")
            if errors:
                raise RuntimeError(f"{case['id']}: {errors}")
            page.close()
        browser.close()


def native(manifest_path, manifest, exe):
    environment = dict(os.environ, RELIC_VISUAL_MANIFEST=str(manifest_path), RELIC_VISUAL_OUTPUT=manifest["output"], RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable, RELIC_HOME=manifest["fixture"]["home"])
    with (manifest_path.parent / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=environment, stdout=log, stderr=log)
        try:
            receipt = wait_file(manifest_path.parent / "complete.json", process, timeout=1200)
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
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--reference", action="store_true", help="Capture reference against this exact native fixture/server on the Windows runner")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scenes = spec["scenes"] if args.matrix == "full" else ["group", "private", "overview", "settings-appearance", "new-org", "copies", "chart"]
    languages = spec["languages"] if args.matrix == "full" else ["zh-CN"]
    themes = spec["themes"] if args.matrix == "full" else ["light"]
    sizes = spec["sizes"] if args.matrix == "full" else [[1440, 900]]
    for lang in languages:
        data = output / "data" / lang
        data.mkdir(parents=True, exist_ok=True)
        with (data / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-X", "utf8", str(HERE / "serve.py"), "--output", str(data), "--lang", lang], stdout=log, stderr=log)
            try:
                fixture = wait_file(data / "fixture.json", server)
                zh = lang == "zh-CN"
                fixture.update(quote="先看页面，再判断是否完成。" if zh else "Look at the screens before calling them done.", plain="请对照截图检查布局与文字，再提交验收。" if zh else "Compare the layout and wording before submitting for review.", digest={"text": "团队正在核对原生界面。设计师整理视觉问题，工程师准备跨平台截图；权限与负责人安排等待您决定。" if zh else "The team is reviewing the native interface. Design is collecting visual issues and engineering is preparing cross-platform screenshots. Permissions and the integration lead await your decision.", "at": time.time(), "count": 5, "last_id": 999})
                for theme in themes:
                    configure(fixture, lang=lang, theme=theme)
                    work = data / theme
                    work.mkdir(exist_ok=True)
                    cases = [{"id": f"{lang}-{theme}-{width}x{height}-{scene}", "scene": scene, "width": width, "height": height, "file": f"{lang}-{theme}-{width}x{height}-{scene}.png"} for width, height in sizes for scene in scenes]
                    manifest = {"version": 1, "client": args.client, "lang": lang, "theme": theme, "fixture": fixture, "output": str(output), "cases": cases}
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
    (output / "capture-complete.json").write_text(json.dumps({"client": args.client, "matrix": args.matrix, "count": len(scenes) * len(sizes) * len(languages) * len(themes)}), encoding="utf-8")
    if args.reference:
        (output.parent / "reference/capture-complete.json").write_text(json.dumps({"client": "reference", "matrix": args.matrix, "count": len(scenes) * len(sizes) * len(languages) * len(themes)}), encoding="utf-8")


if __name__ == "__main__":
    main()
