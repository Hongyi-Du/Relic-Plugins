"""CI-only paint-trace experiment; never supplies canonical parity measurements.

Read an existing manifest and recreate selected scenes with serve.py in a new
fixture. Keep real browser paint records and source evidence for attribution.
No Skia parser, replacement rendering, estimated bounds or local execution.
"""
import argparse
import base64
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from capture import HERE, ROOT, configure, font_evidence, input_text_evidence, prepare_scene, wait_file

TRACE_CATEGORIES = [
    # Keep Paint/frame attribution and every picture export category. General
    # blink/cc layout/compositor events dominated the first lossy recording.
    "devtools.timeline", "disabled-by-default-devtools.timeline.frame",
    "disabled-by-default-devtools.timeline.picture",
    "disabled-by-default-cc.debug.picture",
    "disabled-by-default-cc.debug.display_items",
]


def trace_parameters():
    """Explicit supported CDP configuration; the buffer is the prior default.

    Producer packet loss is not repaired by claiming a larger central buffer.
    Keep the original picture categories until final-frame attribution works.
    """
    return {"traceConfig": {"recordMode": "recordUntilFull",
            "traceBufferSizeInKb": 200 * 1024, "includedCategories": list(TRACE_CATEGORIES)},
            "bufferUsageReportingInterval": 250, "transferMode": "ReturnAsStream",
            "streamFormat": "json", "streamCompression": "none"}


def launch_browser(playwright, channel="headless-shell"):
    # Playwright otherwise hides production scrollbars even in the reference.
    options = {"headless": True, "args": ["--disable-dev-shm-usage"], "ignore_default_args": ["--hide-scrollbars"]}
    if channel == "chromium":
        options["channel"] = "chromium"
    elif channel != "headless-shell":
        raise ValueError("Unsupported paint diagnostic channel: " + channel)
    return playwright.chromium.launch(**options)


def trace_diagnostics(trace, pictures):
    """Index original evidence without inferring painted geometry/attribution."""
    metadata = trace.get("metadata", {})
    stats = metadata.get("trace_processor_stats")
    losses = []
    loss_names = {"trace_writer_packet_loss", "sequence_packet_loss", "data_loss_smb_full",
                  "bytes_overwritten", "chunks_discarded", "chunks_overwritten",
                  "traced_chunks_discarded", "packet_skipped_seq_needs_incremental_state_invalid"}
    def visit(value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                path = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in loss_names and isinstance(child, (int, float)) and child > 0:
                    losses.append({"trace_json_pointer": path, "value": child})
                visit(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, pointer + "/" + str(index))
    visit(stats, "/metadata/trace_processor_stats")
    events = trace.get("traceEvents", [])
    picture_indexes = sorted({row["event_index"] for row in pictures["pictures"]})
    return {"command_line": metadata.get("command_line"), "trace_processor_stats": stats,
            "nonzero_loss_evidence": losses,
            "category_event_counts": dict(Counter(event.get("cat", "") for event in events)),
            "clock_sync_events": [{"event_index": index, "event": event}
                for index, event in enumerate(events) if event.get("name") == "clock_sync"],
            "picture_events": [{"event_index": index,
                "event": {key: events[index].get(key) for key in ("name", "cat", "ph", "ts", "pid", "tid", "id")}}
                for index in picture_indexes],
            "final_scene_attribution": None,
            "quantity": "Original timing, command line and loss evidence; not a final-frame or glyph measurement"}

# These metrics describe the live scene, not painted glyphs/scrollbar parts.
SCENE_METRICS = """() => {
  const box = r => ({x:r.x,y:r.y,width:r.width,height:r.height});
  const nodes = [document.body, ...document.body.querySelectorAll('*')];
  return {url:location.href, device_pixel_ratio:devicePixelRatio,
    navigator_platform:navigator.platform, user_agent:navigator.userAgent,
    viewport:{width:innerWidth,height:innerHeight}, scroll:{x:scrollX,y:scrollY},
    visual_viewport:visualViewport ? {offset_left:visualViewport.offsetLeft,
      offset_top:visualViewport.offsetTop,page_left:visualViewport.pageLeft,
      page_top:visualViewport.pageTop,width:visualViewport.width,
      height:visualViewport.height,scale:visualViewport.scale} : null,
    performance_now:performance.now(),performance_time_origin:performance.timeOrigin,
    nodes:nodes.map((el,index) => {
      const s=getComputedStyle(el),r=el.getBoundingClientRect();
      return {dom_inventory_id:'dom-'+index,tag:el.localName,id:el.id,
        class:el.getAttribute('class'),bounds:box(r),display:s.display,
        visibility:s.visibility,opacity:s.opacity,
        client_width:el.clientWidth,client_height:el.clientHeight,
        scroll_width:el.scrollWidth,scroll_height:el.scrollHeight,
        scroll_left:el.scrollLeft,scroll_top:el.scrollTop,
        overflow_x:s.overflowX,overflow_y:s.overflowY,
        text_overflow:s.textOverflow,white_space:s.whiteSpace,
        line_clamp:s.webkitLineClamp,writing_mode:s.writingMode,direction:s.direction};
    }),quantity:'DOM layout/scroll metrics only; not glyph ink, visible substring, or UA scrollbar paint'};
}"""


def require_ci():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Paint tracing is CI-only; no browser or fixture is opened locally.")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def select_cases(manifest, scenes, width, height):
    """Select existing diagnostic cases without editing the full matrix."""
    selected = []
    for scene in scenes:
        matches = [case for case in manifest["cases"] if case["scene"] == scene
                   and case["width"] == width and case["height"] == height]
        if len(matches) != 1:
            raise ValueError(f"Manifest must contain exactly one {width}x{height} {scene}; found {len(matches)}")
        selected.append(dict(matches[0]))
    return selected


def read_trace_stream(cdp, handle, path):
    """Persist exact CDP stream bytes; no JSON event filtering or rewriting."""
    byte_count = 0
    try:
        with path.open("wb") as target:
            while True:
                part = cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
                data = base64.b64decode(part["data"], validate=True) if part.get("base64Encoded") else part["data"].encode("utf-8")
                target.write(data)
                byte_count += len(data)
                if part.get("eof"):
                    break
    finally:
        cdp.send("IO.close", {"handle": handle})
    return byte_count


def extract_pictures(trace, output):
    """Decode actual skp64 values and retain their original JSON locations.

    Valid base64 is not proof of a readable SKP or a final-frame glyph. Keep
    every event's payload; do not select a matching-looking picture.
    """
    output.mkdir(exist_ok=True)
    pictures, errors = [], []
    events = trace.get("traceEvents", [])
    def visit(value, pointer, event, event_index):
        if isinstance(value, dict):
            for key, child in value.items():
                location = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key == "skp64":
                    try:
                        if not isinstance(child, str) or not child:
                            raise ValueError("skp64 must be a nonempty base64 string")
                        data = base64.b64decode(child, validate=True)
                        if not data:
                            raise ValueError("skp64 decoded to zero bytes")
                        filename = f"picture-{len(pictures):05d}.skp"
                        (output / filename).write_bytes(data)
                        pictures.append({"file": "pictures/" + filename, "byte_count": len(data),
                            "first_16_bytes_hex": data[:16].hex(), "trace_json_pointer": location,
                            "event_index": event_index,
                            "event": {k: event.get(k) for k in ("name", "cat", "ph", "ts", "pid", "tid", "id")},
                            "layer_id": event.get("args", {}).get("layer_id"),
                            "parsed_skp": None, "final_scene_attribution": None})
                    except (ValueError, TypeError) as error:
                        errors.append({"trace_json_pointer": location, "reason": str(error)})
                else:
                    visit(child, location, event, event_index)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, pointer + "/" + str(index), event, event_index)
    for index, event in enumerate(events):
        visit(event, f"/traceEvents/{index}", event, index)
    return {"trace_event_count": len(events), "pictures": pictures, "errors": errors,
            "quantity": "Unparsed serialized paint records; no canonical glyph or scrollbar measurements"}


def layer_boundary(events, first_event, name, output, boundaries):
    """Retain the latest received tree, not a fabricated synchronous tree read.

    LayerTree has no get-current-tree command. The event's own receipt time and
    source index must remain distinct from this boundary's host clock. In
    particular, no intervening event is not proof of unchanged compositor paint.
    """
    tree_index = next((index for index in range(len(events) - 1, first_event - 1, -1)
                       if events[index]["method"] == "LayerTree.layerTreeDidChange"), None)
    previous_count = boundaries[-1]["event_count"] if boundaries else first_event
    boundary = {"name": name, "received_monotonic": time.monotonic(),
        "source_events_start_index": first_event, "event_count": len(events),
        "latest_tree_event_index": tree_index,
        "latest_tree_event": copy.deepcopy(events[tree_index]) if tree_index is not None else None,
        "paint_events_since_previous_boundary": [
            {"event_index": index, "event": copy.deepcopy(events[index])}
            for index in range(previous_count, len(events))
            if events[index]["method"] == "LayerTree.layerPainted"],
        "final_scene_attribution": None,
        "quantity": "Received protocol tree/paint events; not a synchronous frame or screenshot identity"}
    boundaries.append(boundary)
    write_json(output / "layer-boundaries.json", boundaries)
    return boundary


def collect_layer_snapshots(cdp, read, output, events, first_event, boundaries):
    """Ask only actual post-navigation layer IDs for their diagnostic pictures.

    makeSnapshot flushes document lifecycle in this Chromium implementation and
    temporarily suppresses paint events. Run it AFTER the original screenshot;
    command logs cannot certify that earlier screenshot's content or geometry.
    """
    snapshots = output / "layer-snapshots"
    snapshots.mkdir()
    result = {"status": "failed", "layers": [], "errors": [],
        "final_scene_attribution": None,
        "quantity": "Actual LayerTree snapshot command logs; not measured glyph/scrollbar geometry"}
    boundary = layer_boundary(events, first_event, "before_layer_snapshots", output, boundaries)
    tree = boundary["latest_tree_event"]
    layers = tree.get("params", {}).get("layers") if tree is not None else None
    def persist():
        write_json(output / "layer-snapshots.json", result)
    if not isinstance(layers, list) or not layers:
        result["errors"].append({"source": "LayerTree",
            "reason": "No actual post-navigation layer tree; no snapshot IDs can be requested"})
        persist()
        return result
    seen = set()
    for index, layer in enumerate(layers):
        entry = {"source_layer_event_index": boundary["latest_tree_event_index"],
            "source_layer_index": index, "source_layer": copy.deepcopy(layer),
            "status": "failed", "requests": [], "errors": [], "final_scene_attribution": None,
            "lifecycle_side_effect": "makeSnapshot updates document lifecycle while suppressing paint events"}
        path = snapshots / f"layer-{index:04d}.json"
        item = {"file": "layer-snapshots/" + path.name,
            "source_layer_event_index": boundary["latest_tree_event_index"],
            "source_layer_index": index, "layer_id": layer.get("layerId"),
            "status": "failed", "errors": entry["errors"]}
        result["layers"].append(item)
        def persist_entry():
            item["status"] = entry["status"]
            write_json(path, entry)
            persist()
        def invoke(method, parameters):
            request = {"method": method, "parameters": copy.deepcopy(parameters),
                "started_monotonic": time.monotonic(), "status": "started", "response": None}
            entry["requests"].append(request)
            persist_entry()
            response = read(cdp, method, parameters)
            request.update({"completed_monotonic": time.monotonic(), "response": response,
                            "status": "completed" if response is not None else "failed"})
            persist_entry()
            return response
        layer_id = layer.get("layerId")
        if not isinstance(layer_id, str) or not layer_id:
            entry["errors"].append({"source": "LayerTree", "reason": "Actual layer ID missing"})
        elif layer_id in seen:
            entry["errors"].append({"source": "LayerTree", "reason": "Duplicate actual layer ID in source tree"})
        else:
            seen.add(layer_id)
        if layer.get("drawsContent") is False and not entry["errors"]:
            entry["status"] = "not_requested_non_content_layer"
            persist_entry()
            continue
        if layer.get("drawsContent") is not True:
            entry["errors"].append({"source": "LayerTree", "reason": "Actual drawsContent flag unavailable"})
            persist_entry()
            continue
        paint_count = layer.get("paintCount")
        if type(paint_count) is not int or paint_count <= 0:
            entry["errors"].append({"source": "LayerTree.paintCount",
                "reason": "Actual content-layer paintCount is zero or unavailable; paint attribution remains unproven",
                "value": paint_count})
        if not isinstance(layer_id, str) or not layer_id:
            persist_entry()
            continue
        layer_boundary(events, first_event, f"before_snapshot_{index}", output, boundaries)
        snapshot = invoke("LayerTree.makeSnapshot", {"layerId": layer_id})
        snapshot_id = snapshot.get("snapshotId") if isinstance(snapshot, dict) else None
        if not isinstance(snapshot_id, str) or not snapshot_id:
            entry["errors"].append({"source": "LayerTree.makeSnapshot",
                "reason": "No actual snapshot ID returned for this layer"})
        else:
            try:
                commands = invoke("LayerTree.snapshotCommandLog", {"snapshotId": snapshot_id})
                if not isinstance(commands, dict) or not isinstance(commands.get("commandLog"), list) or not commands["commandLog"]:
                    entry["errors"].append({"source": "LayerTree.snapshotCommandLog",
                        "reason": "No nonempty actual commandLog returned for this snapshot"})
            finally:
                if invoke("LayerTree.releaseSnapshot", {"snapshotId": snapshot_id}) is None:
                    entry["errors"].append({"source": "LayerTree.releaseSnapshot", "reason": "Snapshot release failed"})
        layer_boundary(events, first_event, f"after_snapshot_{index}", output, boundaries)
        entry["status"] = "failed" if entry["errors"] else "raw_records_collected"
        persist_entry()
    result["errors"].extend(dict(error, layer_id=row["layer_id"], file=row["file"])
        for row in result["layers"] for error in row["errors"])
    if not any(row["status"] == "raw_records_collected" for row in result["layers"]):
        result["errors"].append({"source": "LayerTree", "reason": "No actual content-layer command log collected"})
    result["status"] = "failed" if result["errors"] else "raw_records_collected"
    layer_boundary(events, first_event, "after_layer_snapshots", output, boundaries)
    persist()
    return result


def collect_scene(browser, context, manifest, case, output, source):
    output.mkdir(parents=True)
    report = {"scene_id": case["id"], "status": "failed", "measurement_status": "unresolved",
              "glyph_bounds": None, "scrollbar_parts": None, "errors": [], "trace_categories": TRACE_CATEGORIES}
    page = context.new_page()
    page.set_viewport_size({"width": case["width"], "height": case["height"]})
    page.clock.set_fixed_time(manifest["fixture"]["clock"])
    page.route("**/app.js", lambda route: route.fulfill(body=source, content_type="application/javascript"))
    page.on("pageerror", lambda error: report["errors"].append({"source": "page", "reason": str(error)}))
    cdp = context.new_cdp_session(page)
    trace_cdp = browser.new_browser_cdp_session()
    complete, layer_events, markers, buffer_usage, boundaries = [], [], [], [], []
    phase = {"name": "initial"}
    progress = []
    def checkpoint(operation, state):
        # Persist before potentially blocking protocol calls. A CI step timeout
        # must retain the operation that stalled, not erase all partial evidence.
        progress.append({"operation": operation, "state": state,
                         "phase": phase["name"], "monotonic": time.monotonic()})
        write_json(output / "progress.json", progress)
    trace_cdp.on("Tracing.tracingComplete", lambda data: complete.append(data))
    trace_cdp.on("Tracing.bufferUsage", lambda data: buffer_usage.append({
        "phase": phase["name"], "received_monotonic": time.monotonic(), "params": data}))
    for event in ("LayerTree.layerTreeDidChange", "LayerTree.layerPainted"):
        cdp.on(event, lambda data, method=event: layer_events.append({"method": method,
            "phase": phase["name"], "received_monotonic": time.monotonic(), "params": data}))
    def read(session, method, parameters=None):
        checkpoint(method, "started")
        try:
            result = session.send(method, parameters or {})
            checkpoint(method, "completed")
            return result
        except Exception as error:
            checkpoint(method, "failed")
            report["errors"].append({"source": method, "reason": str(error)})
            return None
    def marker(name):
        phase["name"] = name
        marker_id = case["id"] + ":" + name
        result = read(trace_cdp, "Tracing.recordClockSyncMarker", {"syncId": marker_id})
        markers.append({"id": marker_id, "receipt": result, "received_monotonic": time.monotonic()})
    tracing = False
    try:
        write_json(output / "browser.json", {"playwright_browser_version": browser.version,
            "cdp": read(trace_cdp, "Browser.getVersion"), "host_platform": sys.platform,
            "categories": read(trace_cdp, "Tracing.getCategories")})
        read(cdp, "DOM.enable")
        read(cdp, "LayerTree.enable")
        parameters = trace_parameters()
        write_json(output / "trace-config.json", parameters)
        checkpoint("Tracing.start", "started")
        trace_cdp.send("Tracing.start", parameters)
        checkpoint("Tracing.start", "completed")
        tracing = True
        marker("before_navigation")
        checkpoint("page/navigation-and-real-scene", "started")
        page.goto(f"http://127.0.0.1:{manifest['fixture']['port']}/", wait_until="domcontentloaded")
        page.wait_for_function("typeof window.__relicVisual === 'function' && document.querySelector('#stream-inner')?.children.length > 0")
        page.evaluate("([scene, fixture]) => window.__relicVisual(scene, fixture)", [case["scene"], manifest["fixture"]])
        if case["scene"] == "documents":
            page.locator(".details .left .chat-row").first.click()
            page.locator(".details .doc-body").wait_for(state="visible")
        page.mouse.move(case["width"] + 20, case["height"] + 20)
        checkpoint("page/navigation-and-real-scene", "completed")
        marker("post_navigation_layer_enable")
        # InspectorLayerTreeAgent::Restore deliberately does not re-enable this
        # domain after navigation. Request the new document first, as DevTools
        # does; old-document layers cannot supply current DOM ownership.
        first_scene_layer_event = len(layer_events)
        document = read(cdp, "DOM.getDocument", {"depth": 0, "pierce": True})
        write_json(output / "layer-document.json", document)
        if not isinstance(document, dict) or not isinstance(document.get("root"), dict):
            report["errors"].append({"source": "DOM.getDocument",
                "reason": "Actual post-navigation document identity unavailable; layer DOM ownership remains unproven"})
        read(cdp, "LayerTree.enable")
        page.wait_for_timeout(700)  # Existing settle interval also pumps actual layer events.
        marker("before_screenshot")
        layer_boundary(layer_events, first_scene_layer_event, "before_screenshot", output, boundaries)
        checkpoint("page/screenshot", "started")
        page.screenshot(path=output / "scene.png", animations="disabled")
        checkpoint("page/screenshot", "completed")
        marker("after_screenshot")
        layer_boundary(layer_events, first_scene_layer_event, "after_screenshot", output, boundaries)
        marker("before_layer_snapshots")
        layer_snapshots = collect_layer_snapshots(cdp, read, output, layer_events,
                                                   first_scene_layer_event, boundaries)
        report["errors"].extend(layer_snapshots["errors"])
        report["layer_snapshot_status"] = layer_snapshots["status"]
        marker("after_layer_snapshots")
        write_json(output / "scene-metrics.json", page.evaluate(SCENE_METRICS))
        write_json(output / "layout-metrics.json", read(cdp, "Page.getLayoutMetrics"))
        write_json(output / "target.json", read(cdp, "Target.getTargetInfo"))
        snapshot = read(cdp, "DOMSnapshot.captureSnapshot", {"computedStyles": [], "includePaintOrder": True, "includeDOMRects": True})
        write_json(output / "dom.json", snapshot)
        write_json(output / "ax.json", read(cdp, "Accessibility.getFullAXTree"))
        checkpoint("input-text-evidence", "started")
        inputs = input_text_evidence(cdp)
        checkpoint("input-text-evidence", "completed")
        write_json(output / "input-text.json", inputs)
        if snapshot is not None:
            checkpoint("font-evidence", "started")
            write_json(output / "fonts.json", font_evidence(cdp, snapshot, inputs))
            checkpoint("font-evidence", "completed")
        marker("after_source_evidence")
    except Exception as error:
        report["errors"].append({"source": "scene_capture", "reason": str(error)})
    finally:
        if tracing:
            try:
                checkpoint("Tracing.end", "started")
                trace_cdp.send("Tracing.end")
                checkpoint("Tracing.end", "completed")
                deadline = time.monotonic() + 45
                while not complete and time.monotonic() < deadline:
                    # Playwright must pump the CDP completion event.
                    page.wait_for_timeout(100)
                if not complete:
                    raise TimeoutError("No Tracing.tracingComplete event within 45 seconds")
                write_json(output / "trace-complete.json", complete[0])
                if complete[0].get("dataLossOccurred"):
                    report["errors"].append({"source": "Tracing", "reason": "Trace data loss occurred"})
                trace_path = output / "trace.json"
                checkpoint("trace-stream", "started")
                report["trace_byte_count"] = read_trace_stream(trace_cdp, complete[0]["stream"], trace_path)
                checkpoint("trace-stream", "completed")
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
                index = extract_pictures(trace, output / "pictures")
                write_json(output / "pictures.json", index)
                diagnostics = trace_diagnostics(trace, index)
                write_json(output / "trace-diagnostics.json", diagnostics)
                command_line = diagnostics["command_line"]
                if not isinstance(command_line, str) or not command_line:
                    report["errors"].append({"source": "browser_command_line",
                        "reason": "Actual trace metadata command line missing; scrollbar launch environment unverified"})
                elif "--hide-scrollbars" in command_line:
                    report["errors"].append({"source": "browser_command_line",
                        "reason": "Actual browser command line still contains --hide-scrollbars"})
                if diagnostics["nonzero_loss_evidence"]:
                    report["errors"].append({"source": "trace_processor_stats",
                        "reason": "Original trace processor statistics report packet loss or discarded/overwritten data",
                        "evidence": diagnostics["nonzero_loss_evidence"]})
                report["picture_count"] = len(index["pictures"])
                report["trace_event_count"] = index["trace_event_count"]
                report["errors"].extend(index["errors"])
                if not index["pictures"]:
                    report["errors"].append({"source": "Tracing", "reason": "No actual skp64 payload exported; paint-record route remains unproven"})
            except Exception as error:
                report["errors"].append({"source": "trace_export", "reason": str(error)})
        write_json(output / "layer-events.json", layer_events)
        write_json(output / "trace-markers.json", markers)
        write_json(output / "buffer-usage.json", buffer_usage)
        if not layer_events:
            report["errors"].append({"source": "LayerTree",
                "reason": "No actual layer events exported; final-scene layer/transform attribution remains unproven"})
        report["status"] = "failed" if report["errors"] else "raw_records_collected"
        write_json(output / "diagnostic.json", report)
        checkpoint("page/protocol-cleanup", "started")
        cdp.detach()
        trace_cdp.detach()
        page.close()
        checkpoint("page/protocol-cleanup", "completed")
    return report


def main(argv=None):
    require_ci()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scene", action="append", help="Existing manifest scene; default group and file-code")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--channel", choices=["headless-shell", "chromium"], default="headless-shell")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    cases = select_cases(manifest, args.scene or ["group", "file-code"], args.width, args.height)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {"kind": "CI paint-trace diagnostic", "source_manifest": str(args.manifest), "requested_browser_channel": args.channel,
        "lang": manifest["lang"], "theme": manifest["theme"], "cases": cases, "results": [],
        "canonical_measurements_changed": False, "measurement_status": "unresolved", "errors": []}
    source = (ROOT / "plugins/relic/app/static/app.js").read_text(encoding="utf-8")
    at = source.rfind("})();")
    if at < 0:
        raise ValueError("Production closure missing; cannot reuse reference-hook.js")
    source = source[:at] + (HERE / "reference-hook.js").read_text(encoding="utf-8") + source[at:]
    # Main capture terminates its fixture. Use a new isolated copy; never attach
    # to or restart the person's Relic server.
    data = output / "fixture"
    data.mkdir()
    with (data / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-X", "utf8", str(HERE / "serve.py"),
                                   "--output", str(data), "--lang", manifest["lang"]], stdout=log, stderr=log)
        try:
            fixture = wait_file(data / "fixture.json", server)
            manifest["fixture"] = dict(manifest["fixture"], **fixture)
            configure(manifest["fixture"], lang=manifest["lang"], theme=manifest["theme"])
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = launch_browser(pw, args.channel)
                try:
                    context = browser.new_context(device_scale_factor=1, locale=manifest["lang"],
                        color_scheme=manifest["theme"], timezone_id="UTC")
                    context.add_init_script("localStorage.clear(); sessionStorage.clear();")
                    for case in cases:
                        print("Paint trace diagnostic: " + case["id"], flush=True)
                        state = prepare_scene(manifest["fixture"], case["scene"])
                        manifest["fixture"]["scene_state"] = state
                        write_json(output / (case["id"] + ".scene-fixture.json"), state)
                        summary["results"].append(collect_scene(browser, context, manifest, case, output / case["id"], source))
                    context.close()
                finally:
                    browser.close()
        except Exception as error:
            summary["errors"].append(str(error))
        finally:
            server.terminate()
            server.wait(timeout=20)
            summary["status"] = "failed" if summary["errors"] or len(summary["results"]) != len(cases) or any(
                result["status"] != "raw_records_collected" for result in summary["results"]) else "raw_records_collected"
            write_json(output / "summary.json", summary)
    return 1 if summary["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
