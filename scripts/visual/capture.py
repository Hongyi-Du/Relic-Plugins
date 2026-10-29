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
DATALIST_SCENES = {
    "member-host-model-suggestions": "#layer input[list='relic-claude-models']",
    "member-existing-seat-suggestions": "#layer input[list='relic-seat-names']",
}
LIVE_SCENES = frozenset(("live-busy", "live-tool-output", "live-typing"))


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


def prepare_scene(fixture, scene):
    """Reset the previous Hub fixture, then prepare this actual CI scene."""
    request = urllib.request.Request(f"http://127.0.0.1:{fixture['port']}{fixture['scene_endpoint']}",
        data=json.dumps({"scene": scene}).encode(),
        headers={"Content-Type": "application/json", "X-Relic-Token": fixture["token"]})
    with urllib.request.urlopen(request) as response:
        result = json.load(response)
    if result.get("scene") != scene or result.get("live") is not (scene in LIVE_SCENES) or not result.get("org") or not result.get("member"):
        raise RuntimeError("Visual fixture did not prepare the requested scene: " + scene)
    return result


def open_live_tool_output(page, prepared):
    """Click the production disclosure matching the returned real tool title."""
    title = prepared["tool"]["title"]
    row = page.locator("#live details.step").filter(has=page.get_by_text(title, exact=True))
    if row.count() != 1:
        raise RuntimeError("Expected one live tool disclosure for: " + title)
    row.locator(":scope > summary").click()
    row.locator(":scope > .io").wait_for(state="visible")
    opened = row.evaluate("el => el.open")
    if not opened:
        raise RuntimeError("Real live tool disclosure did not open: " + title)
    return {"action": "click production details.step summary", "tool_title": title,
            "open": opened, "visible_output": row.locator(":scope > .io").inner_text()}


def prepare_animation_capture(page, cdp, scene):
    """Pause real framework animations at time zero; never assign paint values."""
    if scene not in LIVE_SCENES:
        return None
    return page.evaluate("""async () => {
      const animations = document.getAnimations();
      const numeric = value => typeof value === 'number' && !Number.isFinite(value) ? String(value) : value;
      const timing = value => value == null ? null : Object.fromEntries(Object.entries(value).map(([key,item]) => [key,numeric(item)]));
      const describe = animation => {
        const target = animation.effect?.target;
        return {id:animation.id,type:animation.constructor.name,
          animation_name:animation.animationName ?? null,transition_property:animation.transitionProperty ?? null,
          current_time:numeric(animation.currentTime),start_time:numeric(animation.startTime),play_state:animation.playState,
          pending:animation.pending,playback_rate:animation.playbackRate,
          target:target ? {tag:target.localName,id:target.id,class:target.getAttribute('class')} : null,
          effect_timing:animation.effect ? timing(animation.effect.getTiming()) : null,
          computed_timing:animation.effect ? timing(animation.effect.getComputedTiming()) : null};
      };
      const before = animations.map(describe);
      for (const animation of animations) { animation.pause(); animation.currentTime = 0; }
      await Promise.all(animations.map(animation => animation.ready));
      await document.fonts.ready;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (document.getAnimations().some(animation => !animations.includes(animation) || animation.playState !== 'paused' || animation.currentTime !== 0))
        throw new Error('Live capture animation changed after its real timeline was paused');
      return {source:'actual Web Animations API',operation:'pause then seek currentTime to 0',
        screenshot_animations:'allow',before,after:animations.map(describe)};
    }""")


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


def open_datalist_scene(page, cdp, scene):
    """Use the production input and a trusted ArrowDown; never draw an option.

    Chromium's datalist suggestion view belongs to browser Autofill UI, not to
    the page DOM. Page/AX evidence can therefore be incomplete even when the
    input accepted this action. The source options below are explicitly not a
    measured visible popup inventory.
    """
    selector = DATALIST_SCENES[scene]
    field = page.locator(selector)
    field.wait_for(state="visible")
    read_input = """el => ({tag:el.tagName, list:el.getAttribute('list'), value:el.value,
        focused:document.activeElement===el, disabled:el.disabled,
        bounds:(r => ({x:r.x,y:r.y,width:r.width,height:r.height}))(el.getBoundingClientRect()),
        source_options:Array.from(el.list?.options || [], o => ({value:o.value,label:o.label,text:o.textContent,disabled:o.disabled})),
        source_options_quantity:'DOM datalist definitions; not painted popup elements'})"""
    evidence = {"source": "production input focus + Playwright keyboard ArrowDown",
                "scene": scene, "selector": selector, "errors": [],
                "popup_painted_presence": None, "popup_painted_bounds": None,
                "popup_painted_elements": None, "screenshot_includes_browser_popup": None}
    def record_cdp(key, method, parameters=None):
        try:
            evidence[key] = cdp.send(method, parameters or {})
        except Exception as error:
            evidence[key] = None
            evidence["errors"].append({"method": method, "reason": str(error)})
    evidence["before_input"] = field.evaluate(read_input)
    if evidence["before_input"]["disabled"] or not evidence["before_input"]["source_options"]:
        raise RuntimeError("Datalist scene needs an enabled input with real source suggestions: " + scene)
    record_cdp("before_ax", "Accessibility.getFullAXTree")
    record_cdp("before_targets", "Target.getTargets")
    field.focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(250)
    evidence["after_input"] = field.evaluate(read_input)
    if not evidence["after_input"]["focused"]:
        raise RuntimeError("Datalist input lost focus before capture: " + scene)
    record_cdp("after_ax", "Accessibility.getFullAXTree")
    record_cdp("after_targets", "Target.getTargets")
    record_cdp("after_dom", "DOM.getDocument", {"depth": -1, "pierce": True})
    return evidence


def record_datalist_coverage(elements, evidence):
    """Keep the UA popup measurement gap visible to the existing strict gate.

    A focus/key receipt, source <option> rows, or an AX name alone cannot prove
    painted presence, glyph bounds, state, colors, or screenshot inclusion.
    This does not turn hidden source options into canonical visible elements.
    """
    elements.setdefault("capture_evidence", {})["datalist_popup"] = evidence
    owners = [row["id"] for row in elements["elements"] if row.get("kind") == "input"
              and row.get("state", {}).get("focused")]
    owner = owners[0] if len(owners) == 1 else "browser-autofill-popup"
    gaps = elements["coverage"]["unmeasured"]
    for property_name, reason in (
        ("browser_popup.painted_presence", "The real datalist input received focus and ArrowDown; page CDP evidence does not certify that the browser Autofill popup painted."),
        ("browser_popup.painted_elements", "Actual browser popup rows, text, icons, geometry, styles and states are not measured. Source datalist options are definitions, not visible counterparts."),
        ("browser_popup.screenshot_coverage", "Page.screenshot captures the page surface; inclusion of the separate browser UI popup is unproven. This screenshot cannot certify complete scene paint."),
    ):
        gaps.append({"element": owner, "property": property_name, "reason": reason,
                     "evidence": "capture_evidence.datalist_popup"})


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
            prepared = prepare_scene(manifest["fixture"], case["scene"])
            case_fixture = dict(manifest["fixture"], scene_state=prepared)
            (Path(manifest["output"]) / (case["id"] + ".scene-fixture.json")).write_text(json.dumps(prepared, ensure_ascii=False), encoding="utf-8")
            page = context.new_page()
            page.set_viewport_size({"width": case["width"], "height": case["height"]})
            page.clock.set_fixed_time(manifest["fixture"]["clock"])
            page.route("**/app.js", lambda route: route.fulfill(body=source, content_type="application/javascript"))
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{manifest['fixture']['port']}/", wait_until="domcontentloaded")
            page.wait_for_function("typeof window.__relicVisual === 'function' && document.querySelector('#stream-inner')?.children.length > 0")
            page.evaluate("([scene, fixture]) => window.__relicVisual(scene, fixture)", [case["scene"], case_fixture])
            if case["scene"] == "documents":
                # Exercise the production selection handler and its real GET.
                page.locator(".details .left .chat-row").first.click()
                page.locator(".details .doc-body").wait_for(state="visible")
            page.wait_for_timeout(700)
            if case["scene"] == "live-tool-output":
                action = open_live_tool_output(page, prepared)
                (Path(manifest["output"]) / (case["id"] + ".scene-action.json")).write_text(json.dumps(action, ensure_ascii=False), encoding="utf-8")
            cdp = page.context.new_cdp_session(page)
            page.mouse.move(case["width"] + 20, case["height"] + 20)
            datalist = open_datalist_scene(page, cdp, case["scene"]) if case["scene"] in DATALIST_SCENES else None
            animation = prepare_animation_capture(page, cdp, case["scene"])
            if animation is not None:
                (Path(manifest["output"]) / (case["id"] + ".animations.json")).write_text(json.dumps(animation, ensure_ascii=False), encoding="utf-8")
            page.screenshot(path=Path(manifest["output"]) / case["file"], animations="allow" if case["scene"] in LIVE_SCENES else "disabled")
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
            if datalist is not None:
                record_datalist_coverage(elements, datalist)
                (Path(manifest["output"]) / (case["id"] + ".datalist-popup.json")).write_text(json.dumps(datalist, ensure_ascii=False), encoding="utf-8")
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


def pending_element_request(directory, completed):
    """Read an immutable, atomically published request for one native scene.

    Completed files stay as audit evidence. No reader holds the next scene's
    target while its writer publishes it, unlike a repeatedly replaced mailbox.
    """
    for path in sorted((directory / "element-requests").glob("*.json")):
        if path.stem in completed:
            continue
        request = json.loads(path.read_text(encoding="utf-8-sig"))
        if request.get("case_id") != path.stem:
            raise ValueError("Element request filename does not match its scene: " + str(path))
        return path, request
    return None


def native(manifest_path, manifest, exe):
    environment = dict(os.environ, RELIC_VISUAL_MANIFEST=str(manifest_path), RELIC_VISUAL_OUTPUT=manifest["output"], RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable, RELIC_HOME=manifest["fixture"]["home"], RELIC_VISUAL_NOW=manifest["fixture"]["clock"], TZ="UTC")
    if manifest["client"] == "windows":
        (manifest_path.parent / "current-case.txt").write_text("startup: launching native executable", encoding="utf-8")
    with (manifest_path.parent / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=environment, stdout=log, stderr=log)
        completed_requests = set()
        def capture_elements():
            if manifest["client"] != "windows":
                return
            pending = pending_element_request(manifest_path.parent, completed_requests)
            if pending is None:
                return
            request_path, request = pending
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
            receipt = manifest_path.parent / "element-receipts" / (last_request + ".json")
            receipt.parent.mkdir(exist_ok=True)
            receipt.with_suffix(".tmp").write_text(json.dumps({"case_id": last_request}), encoding="utf-8")
            receipt.with_suffix(".tmp").replace(receipt)
            completed_requests.add(last_request)
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
