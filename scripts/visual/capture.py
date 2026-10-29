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


def input_text_evidence(cdp):
    """Read real UA-shadow input text ranges omitted by DOMSnapshot.

    A missing range remains unknown. This neither creates a mirror element nor
    changes input contents/styles to estimate their layout.
    """
    document = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
    evidence = {}
    errors = []
    def children(node):
        return node.get("children", []) + node.get("shadowRoots", [])
    def text_nodes(node, parent_backend=None):
        if node.get("nodeType") == 3 and node.get("nodeValue"):
            yield node, parent_backend
        for child in children(node):
            yield from text_nodes(child, node.get("backendNodeId"))
    def visit(node):
        if node.get("nodeName", "").upper() in {"INPUT", "TEXTAREA", "SELECT"}:
            owner = str(node["backendNodeId"])
            measured = {"boxes": [], "text_nodes": [], "source": "CDP.DOM+Runtime.DOMRange"}
            for shadow in node.get("shadowRoots", []):
                for text_node, font_owner in text_nodes(shadow):
                    object_id = None
                    try:
                        resolved = cdp.send("DOM.resolveNode", {"backendNodeId": text_node["backendNodeId"]})
                        object_id = resolved["object"]["objectId"]
                        result = cdp.send("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": "function() { for (let p = this.parentElement || this.getRootNode().host; p; p = p.parentElement || p.getRootNode().host) { const s = getComputedStyle(p); if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return []; } const r = this.ownerDocument.createRange(); r.selectNodeContents(this); return Array.from(r.getClientRects(), b => ({x:b.x,y:b.y,width:b.width,height:b.height})); }", "returnByValue": True})
                        if result.get("exceptionDetails"):
                            raise RuntimeError(str(result["exceptionDetails"]))
                        boxes = [b for b in result["result"].get("value", []) if b["width"] >= 0 and b["height"] > 0]
                        measured["boxes"].extend(boxes)
                        measured["text_nodes"].append({"backend_node_id": text_node["backendNodeId"], "font_owner_backend_node_id": font_owner, "text": text_node["nodeValue"], "boxes": boxes})
                    except Exception as error:
                        errors.append({"owner_backend_node_id": owner, "text_backend_node_id": text_node.get("backendNodeId"), "reason": str(error)})
                    finally:
                        if object_id:
                            cdp.send("Runtime.releaseObject", {"objectId": object_id})
            evidence[owner] = measured
        for child in children(node):
            visit(child)
    visit(document["root"])
    return {"inputs": evidence, "errors": errors, "raw_document": document}


def reference(manifest):
    from playwright.sync_api import sync_playwright
    source = (ROOT / "plugins/relic/app/static/app.js").read_text(encoding="utf-8")
    at = source.rfind("})();")
    assert at > 0
    source = source[:at] + (HERE / "reference-hook.js").read_text(encoding="utf-8") + source[at:]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        # Reuse the transport pool. A fresh Chromium context for each of 126
        # scenes exhausted the Windows runner's socket buffers near the end of
        # en-US/light (40930725969). Reset browser storage before each real page
        # load, preserving the previous isolated scene inputs without hundreds
        # of independent connection pools. No page markup/style is replaced.
        context = browser.new_context(device_scale_factor=1, locale=manifest["lang"], color_scheme=manifest["theme"], timezone_id="UTC")
        context.add_init_script("localStorage.clear(); sessionStorage.clear();")
        for case in manifest["cases"]:
            print("Reference capture: " + case["id"], flush=True)
            page = context.new_page()
            page.set_viewport_size({"width": case["width"], "height": case["height"]})
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
            input_text = input_text_evidence(cdp)
            fonts = font_evidence(cdp, snapshot, input_text)
            environment = page.evaluate("({navigator_platform:navigator.platform,user_agent:navigator.userAgent,language:navigator.language,device_pixel_ratio:devicePixelRatio,url:location.href,display_mode:matchMedia('(display-mode: standalone)').matches?'standalone':matchMedia('(display-mode: minimal-ui)').matches?'minimal-ui':'browser',navigator_standalone:navigator.standalone===true})")
            environment.update(platform="macos" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else sys.platform,
                               browser={"name": "Chromium", "version": browser.version}, fonts=fonts)
            evidence = Path(manifest["output"]) / (case["id"] + ".dom.json")
            evidence.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            (Path(manifest["output"]) / (case["id"] + ".ax.json")).write_text(json.dumps(ax_tree, ensure_ascii=False), encoding="utf-8")
            (Path(manifest["output"]) / (case["id"] + ".input-text.json")).write_text(json.dumps(input_text, ensure_ascii=False), encoding="utf-8")
            extractor = (HERE / "reference-elements.js").read_text(encoding="utf-8")
            elements = page.evaluate(extractor, {"scene_id": case["id"], "lang": manifest["lang"], "theme": manifest["theme"], "dom_snapshot": snapshot, "ax_tree": ax_tree, "input_text_boxes": input_text["inputs"], "input_text_errors": input_text["errors"], "reference_environment": environment})
            (Path(manifest["output"]) / (case["id"] + ".elements.json")).write_text(json.dumps(elements, ensure_ascii=False), encoding="utf-8")
            cdp.detach()
            if errors:
                raise RuntimeError(f"{case['id']}: {errors}")
            page.close()
        context.close()
        browser.close()


def font_evidence(cdp, snapshot, input_text):
    """Record fonts actually used by Chromium for rendered text, not CSS fallbacks."""
    cdp.send("CSS.enable")
    document = snapshot["documents"][0]
    nodes, layout = document["nodes"], document["layout"]
    candidates = set()
    for offset, node_index in enumerate(layout["nodeIndex"]):
        text_index = layout["text"][offset]
        if text_index < 0 or not snapshot["strings"][text_index]:
            continue
        owner = nodes["parentIndex"][node_index] if nodes["nodeType"][node_index] == 3 else node_index
        if owner >= 0:
            candidates.add(nodes["backendNodeId"][owner])
    for measured in input_text["inputs"].values():
        for text_node in measured["text_nodes"]:
            if text_node["boxes"] and text_node.get("font_owner_backend_node_id"):
                candidates.add(text_node["font_owner_backend_node_id"])
    backend_ids = sorted(candidates)
    result = {"source": "CDP.CSS.getPlatformFontsForNode", "by_backend_node": {}, "errors": []}
    frontend_ids = cdp.send("DOM.pushNodesByBackendIdsToFrontend", {"backendNodeIds": backend_ids})["nodeIds"]
    for backend_id, node_id in zip(backend_ids, frontend_ids):
        try:
            if not node_id:
                raise RuntimeError("Rendered text node has no live frontend DOM node")
            result["by_backend_node"][str(backend_id)] = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node_id})["fonts"]
        except Exception as error:
            result["errors"].append({"backend_node_id": backend_id, "reason": str(error)})
    return result


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
    parser.add_argument("--reference", action="store_true", help="Capture reference against this exact native fixture/server on its own platform")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    output = args.output.resolve()
    reference_output = output.parent / ("reference-macos" if args.client == "macos" else "reference")
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
        (reference_output / receipt_name).write_text(json.dumps({"client": "reference", "platform": args.client, "matrix": args.matrix, "count": len(scenes) * len(sizes) * len(languages) * len(themes)}), encoding="utf-8")


if __name__ == "__main__":
    main()
