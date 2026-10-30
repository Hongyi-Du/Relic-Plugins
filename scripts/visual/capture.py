"""Capture the real reference/native UI in CI; no local execution is permitted."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATALIST_SCENES = {
    "member-host-model-suggestions": "#layer input[list='relic-claude-models']",
    "member-existing-seat-suggestions": "#layer input[list='relic-seat-names']",
}
LIVE_SCENES = frozenset(("live-busy", "live-tool-output", "live-typing"))
MEMBER_CARD_SCENES = {
    "member-card-rename": ".top h3 > button.icon-btn",
    "member-card-model": ".kv dd > div > button.btn.sm.ghost",
    "member-card-avatar-hover": ".avatar-wrap",
}
MESSAGE_SCENES = frozenset(("message-hover", "message-copy-toast"))
RESIZE_SCENES = frozenset(("new-org-textarea-resized",))


class TextareaResizeCapture:
    """Observe a real textarea corner drag; the action point is not a grip box."""
    SELECTOR = "#layer .dialog[role='dialog'] .form textarea"
    READ_FIELD = """(el, selector) => {
      const r=el.getBoundingClientRect(),s=getComputedStyle(el);
      return {connected:el.isConnected,same_node:document.querySelector(selector)===el,tag:el.tagName,
        bounds:{x:r.x,y:r.y,width:r.width,height:r.height},value:el.value,text_content:el.textContent,
        placeholder:el.getAttribute('placeholder'),rows:el.rows,disabled:el.disabled,readonly:el.readOnly,
        focused:document.activeElement===el,hovered:el.matches(':hover'),inline_style:el.getAttribute('style'),
        resize:s.resize,direction:s.direction,writing_mode:s.writingMode,overflow_x:s.overflowX,overflow_y:s.overflowY,
        display:s.display,visibility:s.visibility,opacity:s.opacity,background:s.backgroundColor,color:s.color,
        border_colors:['Top','Right','Bottom','Left'].map(side=>s['border'+side+'Color']),
        client_width:el.clientWidth,client_height:el.clientHeight,scroll_width:el.scrollWidth,scroll_height:el.scrollHeight};
    }"""
    SETTLE = """async () => {await document.fonts.ready; await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame); return {status:document.fonts.status,count:document.fonts.size};}"""

    def __init__(self, page, cdp, scene, receipt_path):
        self.page, self.cdp, self.scene, self.receipt_path = page, cdp, scene, receipt_path
        self.field = self.observer = None
        self.baseline = None
        self.evidence = {"source": "production textarea + actual Playwright mouse move/down/move/up",
            "scene": scene, "navigation_scene": "new-org", "selector": self.SELECTOR, "checkpoints": [], "errors": [],
            "resize_handle": {"kind": "resize-handle", "painted_presence": None, "bounds": None, "style": None, "state": None,
                "measurement_limit": "The corner action point and owner border box do not measure the UA resize grip's painted box, style or state."}}

    def save(self):
        self.receipt_path.write_text(json.dumps(self.evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_sources(self, stage):
        evidence = {}
        for key, method, parameters in (("dom", "DOM.getDocument", {"depth": -1, "pierce": True}),
                                         ("ax", "Accessibility.getFullAXTree", {})):
            try:
                evidence[key] = self.cdp.send(method, parameters)
            except Exception as error:
                evidence[key] = None
                self.evidence["errors"].append({"stage": stage, "method": method, "reason": str(error)})
        self.evidence[stage + "_sources"] = evidence

    def open(self):
        self.evidence["fonts_before_action"] = self.page.evaluate(self.SETTLE)
        if self.evidence["fonts_before_action"].get("status") != "loaded":
            raise RuntimeError("Textarea resize requires the actual page fonts before measuring the corner")
        locator = self.page.locator(self.SELECTOR)
        locator.wait_for(state="visible")
        if locator.count() != 1:
            raise RuntimeError("Expected one production new-organization purpose textarea")
        self.field = locator.element_handle()
        if self.field is None:
            raise RuntimeError("Production textarea detached before the resize action")
        before = self.field.evaluate(self.READ_FIELD, self.SELECTOR)
        self.evidence["before"] = before
        self.save()
        if (not before.get("connected") or not before.get("same_node") or before.get("tag") != "TEXTAREA"
                or before.get("disabled") or before.get("resize") not in ("both", "vertical", "block")):
            raise RuntimeError("The actual new-organization textarea does not expose the requested vertical resize mechanism")
        if before.get("writing_mode") != "horizontal-tb" or before.get("direction") != "ltr":
            raise RuntimeError("The recorded corner recipe requires actual horizontal-tb/ltr layout; no grip location is inferred for other writing modes")
        bounds = before["bounds"]
        if bounds["width"] <= 6 or bounds["height"] <= 6:
            raise RuntimeError("The actual textarea border box cannot contain the corner action point")
        self.observer = self.page.evaluate_handle("""selector => {
          const events=[];
          const observe=event=>{events.push({type:event.type,trusted:event.isTrusted,x:event.clientX,y:event.clientY,
            buttons:event.buttons,button:event.button,pointer_id:event.pointerId,timestamp:event.timeStamp,
            target:{tag:event.target.localName,is_textarea:event.target===document.querySelector(selector)}});};
          const types=['pointermove','pointerdown','pointerup','pointercancel','mousedown','mouseup'];
          for(const type of types)document.addEventListener(type,observe,true);
          return {events,dispose:()=>{for(const type of types)document.removeEventListener(type,observe,true);}};
        }""", self.SELECTOR)
        start = {"x": bounds["x"] + bounds["width"] - 3, "y": bounds["y"] + bounds["height"] - 3}
        end = {"x": start["x"], "y": start["y"] + 64}
        self.evidence["action"] = {"start": start, "end": end, "delta": {"x": 0, "y": 64}, "steps": 8,
            "units": "window CSS pixels", "recipe": "actual owner border-box bottom-right inset 3; vertical drag +64",
            "quantity": "requested pointer path, not measured resize-handle geometry"}
        self.read_sources("before")
        self.save()
        self.page.mouse.move(start["x"], start["y"])
        self.page.mouse.down(button="left")
        try:
            self.page.mouse.move(end["x"], end["y"], steps=8)
        finally:
            self.page.mouse.up(button="left")
        self.evidence["fonts_after_action"] = self.page.evaluate(self.SETTLE)
        after = self.field.evaluate(self.READ_FIELD, self.SELECTOR)
        self.evidence["after"] = after
        self.evidence["pointer_events"] = self.observer.evaluate("capture => capture.events")
        self.evidence["geometry_delta"] = {key: after["bounds"][key] - before["bounds"][key] for key in ("x", "y", "width", "height")}
        self.evidence["event_delivery"] = {"observed_types": sorted({event["type"] for event in self.evidence["pointer_events"]}),
            "quantity": "actual document event receipts; UA resize tracking can consume individual pointer events"}
        self.read_sources("after")
        self.save()
        if self.evidence["fonts_after_action"].get("status") != "loaded":
            raise RuntimeError("Actual fonts changed or did not settle after the textarea drag")
        if after["value"] != before["value"] or after["text_content"] != before["text_content"] or after["placeholder"] != before["placeholder"]:
            raise RuntimeError("The real textarea drag changed text instead of preserving the production field")
        if self.evidence["geometry_delta"]["height"] <= 0:
            raise RuntimeError("The real corner drag did not increase the actual textarea height")
        if any(event.get("trusted") is not True for event in self.evidence["pointer_events"]):
            raise RuntimeError("Textarea drag receipt contains an untrusted synthetic document event")
        self.checkpoint("after_action")

    def checkpoint(self, stage):
        state = self.field.evaluate(self.READ_FIELD, self.SELECTOR)
        events = self.observer.evaluate("capture => capture.events")
        record = {"stage": stage, "state": state, "pointer_events": events, "host_monotonic": time.monotonic()}
        self.evidence["checkpoints"].append(record)
        self.save()
        if not state.get("connected") or not state.get("same_node"):
            raise RuntimeError("The actual resized textarea was replaced during capture at " + stage)
        if self.baseline is None:
            self.baseline = {"state": state, "pointer_events": events}
        elif {"state": state, "pointer_events": events} != self.baseline:
            raise RuntimeError("The actual resized textarea geometry, text, style, state or pointer receipt changed during capture at " + stage)

    def close(self):
        self.save()
        if self.observer is not None:
            self.observer.evaluate("capture => capture.dispose()")
            self.observer.dispose()
        if self.field is not None:
            self.field.dispose()


def read_fixture_json(fixture, path):
    request = urllib.request.Request(f"http://127.0.0.1:{fixture['port']}{path}",
        headers={"X-Relic-Token": fixture["token"]})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


class MessageSceneCapture:
    """Observe trusted production hover/copy and the same scene throughout capture.

    Only the browser's virtual timeline is paused, after the real toast exists.
    No DOM/CSS/application state or timeout callback is replaced or extended.
    """
    READ_MESSAGE = """(el, selector) => {
      const box=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
      const state=n=>{const s=getComputedStyle(n);return {bounds:box(n),display:s.display,visibility:s.visibility,
        opacity:s.opacity,background:s.backgroundColor,color:s.color,font_family:s.fontFamily,font_size:s.fontSize,
        font_weight:s.fontWeight,hovered:n.matches(':hover'),focused:n===document.activeElement};};
      const toolbar=el.querySelector(':scope > .hover-acts');
      return {connected:el.isConnected,same_node:document.querySelector(selector)===el,id:el.dataset.id,
        hovered:el.matches(':hover'),bounds:box(el),text:el.textContent,
        toolbar:toolbar?{...state(toolbar),html:toolbar.outerHTML,
          buttons:Array.from(toolbar.querySelectorAll('button'),button=>({...state(button),title:button.title,
            text:button.textContent,disabled:button.disabled}))}:null};
    }"""
    READ_TOAST = """el => {
      const r=el.getBoundingClientRect(),s=getComputedStyle(el);
      return {connected:el.isConnected,same_node:document.querySelectorAll('.toast').length===1&&document.querySelector('.toast')===el,
        text:el.textContent,role:el.getAttribute('role'),bounds:{x:r.x,y:r.y,width:r.width,height:r.height},
        display:s.display,visibility:s.visibility,opacity:s.opacity,background:s.backgroundColor,color:s.color};
    }"""
    READ_CLOCK = "() => ({date_now:Date.now(),performance_now:performance.now(),time_origin:performance.timeOrigin})"

    def __init__(self, page, cdp, scene, fixture, lang, receipt_path):
        self.page, self.cdp, self.scene, self.fixture, self.lang = page, cdp, scene, fixture, lang
        self.receipt_path = receipt_path
        self.message = self.toast = self.observer = None
        self.paused = False
        self.baseline = None
        self.evidence = {"source": "trusted production pointer/click + actual DOM/clipboard/CDP receipts",
            "scene": scene, "navigation_scene": "group", "checkpoints": [], "errors": [],
            "toast_remaining_ms": None,
            "toast_remaining_reason": "CDP exposes no remaining delay for the production setTimeout handle; no duration is inferred"}

    def save(self):
        self.receipt_path.write_text(json.dumps(self.evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    def progress(self, step, status="started", **details):
        self.evidence.setdefault("steps", []).append({"step": step, "status": status,
            "host_monotonic": time.monotonic(), **details})
        self.save()

    def read_clipboard(self, phase):
        if self.paused:
            raise RuntimeError("Async Clipboard must not be awaited while the browser virtual clock is paused")
        self.progress("clipboard:" + phase)
        before = self.page.evaluate(self.READ_CLOCK)
        value = self.page.evaluate("() => navigator.clipboard.readText()")
        after = self.page.evaluate(self.READ_CLOCK)
        self.evidence.setdefault("clipboard_reads", {})[phase] = {"value": value, "before": before, "after": after,
            "quantity": "actual async clipboard read while virtual time is running; not a paused-checkpoint measurement"}
        self.progress("clipboard:" + phase, "completed")
        return value

    def open(self):
        message_id = str(self.fixture["thread"])
        if not message_id.isdecimal():
            raise RuntimeError("Message scene needs the fixture's real numeric thread/message identity")
        self.selector = '.msg[data-id="' + message_id + '"]'
        vocabulary = read_fixture_json(self.fixture, "/api/i18n?lang=" + urllib.parse.quote(self.lang))
        words = vocabulary.get("strings", {})
        self.copy_label, self.copied_label = words.get("common.copy"), words.get("msg.copied")
        if not self.copy_label or not self.copied_label:
            raise RuntimeError("Message capture requires actual /api/i18n copy and success labels")
        chat_path = "/api/org/" + urllib.parse.quote(self.fixture["org"], safe="") + "/chat?kind=group&limit=1000"
        chat = read_fixture_json(self.fixture, chat_path)
        matches = [item for item in chat.get("items", []) if str(item.get("id")) == message_id]
        if len(matches) != 1 or not isinstance(matches[0].get("body"), str) or not matches[0]["body"]:
            raise RuntimeError("The actual group API did not return exactly one nonempty target message")
        self.body = matches[0]["body"]
        self.evidence.update(selector=self.selector, message_api={"path": chat_path, "message": matches[0]},
                             vocabulary={"lang": vocabulary.get("lang"), "common.copy": self.copy_label, "msg.copied": self.copied_label})
        self.progress("fonts_before_action")
        self.evidence["fonts_before_action"] = self.page.evaluate("async () => {await document.fonts.ready; return {status:document.fonts.status,count:document.fonts.size};}")
        self.progress("fonts_before_action", "completed")
        if self.evidence["fonts_before_action"].get("status") != "loaded":
            raise RuntimeError("Actual page fonts were not ready before the message action")
        self.observer = self.page.evaluate_handle("""() => {
          const events=[];
          const observe=event=>{events.push({type:event.type,trusted:event.isTrusted,x:event.clientX,y:event.clientY,
            timestamp:event.timeStamp,target:{tag:event.target.localName,title:event.target.getAttribute('title'),
              message_id:event.target.closest('.msg')?.dataset.id ?? null}});if(events.length>32)events.shift();};
          const types=['pointermove','pointerdown','pointerup','click'];
          for(const type of types)document.addEventListener(type,observe,true);
          return {events,dispose:()=>{for(const type of types)document.removeEventListener(type,observe,true);}};
        }""")
        row = self.page.locator(self.selector)
        if row.count() != 1:
            raise RuntimeError("Expected exactly one real group message for " + message_id)
        self.progress("production_message_hover")
        row.hover()
        toolbar = row.locator(":scope > .hover-acts")
        toolbar.wait_for(state="visible")
        self.message = row.element_handle()
        if self.message is None:
            raise RuntimeError("Message detached after the real hover action")
        self.progress("production_message_hover", "completed")
        if self.scene == "message-copy-toast":
            origin = f"http://127.0.0.1:{self.fixture['port']}"
            permissions = ["clipboard-read", "clipboard-write"]
            self.page.context.grant_permissions(permissions, origin=origin)
            self.evidence["permissions"] = {"source": "Playwright BrowserContext.grant_permissions in CI", "origin": origin, "permissions": permissions}
            self.evidence["clipboard_before"] = self.read_clipboard("before_copy")
            if self.page.locator(".toast").count() != 0:
                raise RuntimeError("Copy scene already contains a toast before the production action")
            button = toolbar.get_by_title(self.copy_label, exact=True)
            if button.count() != 1:
                raise RuntimeError("Expected exactly one actual Copy button on the target message")
            self.progress("production_copy_click_and_toast")
            button.click()
            notice = self.page.locator(".toast[role='status']")
            notice.wait_for(state="visible")
            if notice.count() != 1:
                raise RuntimeError("Copy action did not produce exactly one real toast")
            self.toast = notice.element_handle()
            if self.toast is None or self.toast.evaluate("el => el.textContent") != self.copied_label:
                raise RuntimeError("The real Copy action did not show its success toast")
            self.progress("production_copy_click_and_toast", "completed")
            self.evidence["clipboard_after"] = self.read_clipboard("after_copy_before_pause")
            self.evidence["clipboard_after_phase"] = "after_copy_before_pause"
            if self.evidence["clipboard_after"] != self.body:
                raise RuntimeError("Actual clipboard contents do not equal the selected API message body before pause")
            self.progress("clock_pause")
            before_clock = self.page.evaluate(self.READ_CLOCK)
            self.paused = True  # Ensure cleanup attempts to resume even if CDP disconnects mid-command.
            receipt = self.cdp.send("Emulation.setVirtualTimePolicy", {"policy": "pause"})
            self.evidence["clock_pause"] = {"method": "Emulation.setVirtualTimePolicy", "parameters": {"policy": "pause"},
                "receipt": receipt, "before": before_clock, "after": self.page.evaluate(self.READ_CLOCK),
                "host_monotonic": time.monotonic(), "scope": "this isolated page target; actual toast already created"}
            if not isinstance(receipt.get("virtualTimeTicksBase"), (int, float)):
                raise RuntimeError("CDP did not return the actual virtual clock receipt")
            self.progress("clock_pause", "completed")
        self.checkpoint("after_action")

    def checkpoint(self, stage):
        self.progress("checkpoint:" + stage)
        message = self.message.evaluate(self.READ_MESSAGE, self.selector)
        toast = self.toast.evaluate(self.READ_TOAST) if self.toast is not None else None
        pointer_events = self.observer.evaluate("capture => capture.events")
        point = next((event for event in reversed(pointer_events) if event["type"] == "pointermove"), None)
        state = {"message": message, "toast": toast, "pointer": {key: point.get(key) for key in ("x", "y", "trusted")} if point else None}
        clock = self.page.evaluate(self.READ_CLOCK)
        record = {"stage": stage, "state": state, "clock": clock, "pointer_events": pointer_events, "host_monotonic": time.monotonic(),
            "clipboard_measurement": "not read at this checkpoint; see actual before-pause and after-resume read receipts"}
        self.evidence["checkpoints"].append(record)
        self.save()
        toolbar = message.get("toolbar")
        if (not message.get("connected") or not message.get("same_node") or not message.get("hovered") or not toolbar
                or toolbar.get("display") == "none" or toolbar.get("visibility") != "visible" or float(toolbar.get("opacity", 0)) <= 0
                or not point or point.get("trusted") is not True or not toolbar.get("buttons")):
            raise RuntimeError("Real message hover/toolbar/pointer state was not retained at " + stage)
        if self.scene == "message-copy-toast":
            if (not toast or not toast.get("connected") or not toast.get("same_node") or toast.get("text") != self.copied_label
                    or toast.get("role") != "status" or toast.get("display") == "none" or toast.get("visibility") != "visible"
                    or float(toast.get("opacity", 0)) <= 0 or toast.get("bounds", {}).get("width", 0) <= 0
                    or toast.get("bounds", {}).get("height", 0) <= 0):
                raise RuntimeError("The same actual Copy toast expired or changed at " + stage)
            if not any(event.get("type") == "click" and event.get("trusted") is True
                       and event.get("target", {}).get("message_id") == str(self.fixture["thread"]) for event in pointer_events):
                raise RuntimeError("No trusted production Copy click was observed")
        if self.baseline is None:
            self.baseline = record
        elif state != self.baseline["state"]:
            raise RuntimeError("Message/toolbar/toast geometry, text, state or actual pointer changed during capture at " + stage)
        elif self.paused and clock["performance_now"] != self.baseline["clock"]["performance_now"]:
            raise RuntimeError("Actual browser virtual time advanced during paused toast capture at " + stage)
        self.progress("checkpoint:" + stage, "completed")

    def close(self):
        try:
            if self.paused:
                self.progress("clock_resume")
                self.evidence["clock_resume"] = {"method": "Emulation.setVirtualTimePolicy", "parameters": {"policy": "advance"},
                    "receipt": self.cdp.send("Emulation.setVirtualTimePolicy", {"policy": "advance"}), "host_monotonic": time.monotonic()}
                self.paused = False
                self.progress("clock_resume", "completed")
                self.evidence["clipboard_after_resume"] = self.read_clipboard("after_resume")
                if self.evidence["clipboard_after_resume"] != self.body:
                    raise RuntimeError("Actual clipboard changed between the before-pause and after-resume reads")
        except Exception as error:
            self.evidence["errors"].append("Message capture cleanup failed: " + str(error))
            raise
        finally:
            self.save()
            if self.observer is not None:
                self.observer.evaluate("capture => capture.dispose()")
                self.observer.dispose()
            for handle in (self.message, self.toast):
                if handle is not None:
                    handle.dispose()
            if self.scene == "message-copy-toast":
                self.page.context.clear_permissions()


def wait_file(path, process, timeout=60, on_tick=None, on_stall=None):
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
                reason = "Native capture did not advance for 90 seconds: " + current_case
                if on_stall is not None:
                    try:
                        on_stall(reason)
                    except Exception as error:
                        # Diagnostics never reset the elapsed progress deadline
                        # or replace its failure with a successful observation.
                        reason += "; stall diagnostic failed: " + str(error)
                raise TimeoutError(reason)
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


def open_member_card_scene(page, scene):
    """Enter an existing production card state using real click/hover actions.

    All evaluate calls below only read the resulting controls. They do not set
    editing flags, values, classes, attributes, CSS, or synthesize hover state.
    """
    card_selector = ".card[role='dialog']"
    card = page.locator(card_selector)
    card.wait_for(state="visible")
    if card.count() != 1:
        raise RuntimeError("Expected one production member card for: " + scene)
    selector = MEMBER_CARD_SCENES[scene]
    control = card.locator(selector)
    control.wait_for(state="visible")
    if control.count() != 1:
        raise RuntimeError("Expected one production member card control for: " + scene)
    read_card = """el => {
      const bounds = node => { const r=node.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height}; };
      const field = node => ({tag:node.tagName,value:node.value,disabled:node.disabled,
        focused:document.activeElement===node,placeholder:node.getAttribute('placeholder'),
        maxlength:node.getAttribute('maxlength'),bounds:bounds(node),
        options:node.options?Array.from(node.options,o=>({value:o.value,text:o.text,selected:o.selected,disabled:o.disabled})):null});
      const rename=el.querySelector('.rename input'), editor=el.querySelector('.model-edit'),
        avatar=el.querySelector('.avatar-wrap'), overlay=avatar?.querySelector('.change');
      return {role:el.getAttribute('role'),name:el.getAttribute('aria-label'),bounds:bounds(el),
        member_text:el.querySelector('.id')?.textContent ?? null,
        rename:rename?field(rename):null,
        model:editor?{selects:Array.from(editor.querySelectorAll('select'),field),
          save_text:editor.querySelector('button')?.textContent ?? null,bounds:bounds(editor)}:null,
        avatar:avatar?{hovered:avatar.matches(':hover'),bounds:bounds(avatar),
          overlay:overlay?{text:overlay.textContent,opacity:getComputedStyle(overlay).opacity,
            display:getComputedStyle(overlay).display,visibility:getComputedStyle(overlay).visibility,bounds:bounds(overlay)}:null}:null};
    }"""
    evidence = {"source": "production member-card controls via Playwright click/hover",
                "scene": scene, "navigation_scene": "member-card", "card_selector": card_selector,
                "control_selector": selector, "before": card.evaluate(read_card),
                "control": control.evaluate("""el => ({tag:el.tagName,text:el.textContent,
                    title:el.getAttribute('title'),disabled:'disabled' in el?el.disabled:null,
                    bounds:(r=>({x:r.x,y:r.y,width:r.width,height:r.height}))(el.getBoundingClientRect())})""")}
    if evidence["control"]["disabled"]:
        raise RuntimeError("Member card control is disabled: " + scene)
    if scene == "member-card-avatar-hover":
        control.hover()
        page.wait_for_function("""selector => {
          const avatar=document.querySelector(selector), overlay=avatar?.querySelector('.change');
          return avatar?.matches(':hover') && overlay && Number(getComputedStyle(overlay).opacity)===1;
        }""", arg=card_selector + " .avatar-wrap")
    else:
        control.click()
        state_selector = ".rename input" if scene == "member-card-rename" else ".model-edit"
        card.locator(state_selector).wait_for(state="visible")
        if scene == "member-card-rename":
            page.wait_for_function("selector => document.querySelector(selector)===document.activeElement",
                                   arg=card_selector + " .rename input")
    evidence["after"] = card.evaluate(read_card)
    after = evidence["after"]
    if scene == "member-card-rename" and (not after["rename"] or not after["rename"]["focused"]):
        raise RuntimeError("Real member rename input did not receive focus")
    if scene == "member-card-model" and (not after["model"] or len(after["model"]["selects"]) != 2):
        raise RuntimeError("Real member model editor did not expose both model and effort controls")
    if scene == "member-card-avatar-hover" and (not after["avatar"] or not after["avatar"]["hovered"]
            or not after["avatar"]["overlay"] or after["avatar"]["overlay"]["opacity"] != "1"):
        raise RuntimeError("Actual avatar hover overlay did not become opaque")
    return evidence


def capture_paused_message_png(page, cdp, path, width, height, action):
    """Save the original CDP page PNG without Playwright's async preparation.

    Its screenshotter awaits document.fonts.ready even with animations=allow
    and temporarily hides carets. Neither belongs inside the frozen phase.
    """
    action.progress("screenshot:viewport")
    viewport = page.evaluate("() => ({width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio,scroll_x:scrollX,scroll_y:scrollY})")
    if viewport.get("width") != width or viewport.get("height") != height or viewport.get("device_pixel_ratio") != 1:
        raise RuntimeError("The actual frozen reference viewport does not equal the requested 1:1 screenshot dimensions")
    parameters = {"format": "png", "fromSurface": True, "captureBeyondViewport": False,
        "clip": {"x": viewport["scroll_x"], "y": viewport["scroll_y"], "width": width, "height": height, "scale": 1}}
    action.evidence["screenshot"] = {"method": "Page.captureScreenshot", "parameters": parameters, "actual_viewport": viewport,
        "quantity": "original browser page-surface PNG; no DOM/caret/style/animation mutation or image composition"}
    action.progress("screenshot:viewport", "completed")
    action.progress("screenshot:Page.captureScreenshot")
    result = cdp.send("Page.captureScreenshot", parameters)
    encoded = base64.b64decode(result["data"], validate=True)
    if len(encoded) < 24 or encoded[:8] != b"\x89PNG\r\n\x1a\n" or encoded[12:16] != b"IHDR":
        raise RuntimeError("CDP screenshot did not return a PNG with an actual IHDR")
    actual_size = [int.from_bytes(encoded[16:20], "big"), int.from_bytes(encoded[20:24], "big")]
    action.evidence["screenshot"].update(png_dimensions=actual_size, png_bytes=len(encoded))
    path.write_bytes(encoded)
    action.progress("screenshot:Page.captureScreenshot", "completed")
    if actual_size != [width, height]:
        raise RuntimeError("Actual CDP PNG dimensions differ from the requested viewport; original bytes are retained")


CARET_CONTEXT = """() => {
  const el=document.activeElement, selection=document.getSelection();
  const box=r=>({x:r.x,y:r.y,width:r.width,height:r.height});
  const ranges=[];
  if(selection)for(let i=0;i<selection.rangeCount;i++){
    const range=selection.getRangeAt(i);
    ranges.push({collapsed:range.collapsed,start_offset:range.startOffset,end_offset:range.endOffset,
      client_rects:Array.from(range.getClientRects(),box),bounding_rect:box(range.getBoundingClientRect()),
      quantity:'actual document Range rectangles; not measured input caret paint'});
  }
  const s=el instanceof Element?getComputedStyle(el):null;
  const textInput=el?.tagName==='INPUT'&&['text','search','url','tel','email','password','number'].includes(el.type);
  return {source:'actual activeElement, document focus/selection and computed caret CSS',
    phase:'source collection after PNG; not a synchronous PNG blink-phase measurement',
    focused_editor_candidate:!!el&&(el.tagName==='TEXTAREA'||textInput||el.isContentEditable===true),
    document_has_focus:document.hasFocus(),performance_now:performance.now(),
    active_element:el?{tag:el.tagName,id:el.id,type:el.type??null,content_editable:el.isContentEditable===true,
      value:el.value??null,placeholder:el.getAttribute('placeholder'),disabled:el.disabled??null,readonly:el.readOnly??null,
      selection_start:el.selectionStart??null,selection_end:el.selectionEnd??null,selection_direction:el.selectionDirection??null,
      bounds:box(el.getBoundingClientRect()),display:s?.display??null,visibility:s?.visibility??null,opacity:s?.opacity??null,
      computed_caret_color:s?.getPropertyValue('caret-color')??null,
      computed_caret_shape:s?.getPropertyValue('caret-shape')??null,
      computed_caret_animation:s?.getPropertyValue('caret-animation')??null}:null,
    document_selection:selection?{collapsed:selection.isCollapsed,range_count:selection.rangeCount,ranges}:null,
    painted_presence:null,painted_bounds:null,painted_color:null,blink_phase:null,
    measurement_limit:'Focus/selection, computed CSS and document ranges do not measure the UA caret painted bounds, pixels or blink phase.'};
}"""


def record_caret_coverage(elements, evidence):
    """Retain actual caret context and fail unknown editor paint, without boxes."""
    elements.setdefault("capture_evidence", {})["caret"] = evidence
    if evidence is not None and evidence.get("focused_editor_candidate") is False:
        return  # No focused text-editor candidate in this actual DOM context; no absence value is synthesized.
    owners = [row["id"] for row in elements.get("elements", []) if row.get("kind") == "input" and row.get("state", {}).get("focused")]
    owner = owners[0] if len(owners) == 1 else "browser-caret"
    reason = ("The screenshot preserves the production caret. Its independently painted presence, bounds, color and blink phase are unmeasured; "
              "focus, insertion offsets and document Range boxes cannot be substituted for actual caret pixels.")
    elements.setdefault("coverage", {}).setdefault("unmeasured", []).append({"element": owner, "property": "caret.rendered_part",
        "reason": reason, "evidence": "capture_evidence.caret"})
    elements.setdefault("extraction_errors", []).append({"type": "ua_caret_measurement_unavailable", "node": owner, "reason": reason})


def capture_reference_evidence(page, cdp, browser, manifest, case, member_card=None, datalist=None):
    output = Path(manifest["output"])
    message = MessageSceneCapture(page, cdp, case["scene"], manifest["fixture"], manifest["lang"],
        output / (case["id"] + ".scene-action.json")) if case["scene"] in MESSAGE_SCENES else None
    resize = TextareaResizeCapture(page, cdp, case["scene"], output / (case["id"] + ".scene-action.json")) if case["scene"] in RESIZE_SCENES else None
    actions = [action for action in (message, resize) if action is not None]
    def source_step(name, operation):
        if message is not None:
            message.progress(name)
        result = operation()
        if message is not None:
            message.progress(name, "completed")
        return result
    try:
        for action in actions:
            action.open()
            action.checkpoint("before_screenshot")
        if case["scene"] == "message-copy-toast":
            capture_paused_message_png(page, cdp, output / case["file"], case["width"], case["height"], message)
        else:
            source_step("screenshot:Playwright", lambda: page.screenshot(path=output / case["file"], caret="initial", animations="allow" if case["scene"] in LIVE_SCENES | MESSAGE_SCENES | RESIZE_SCENES else "disabled"))
        for action in actions:
            action.checkpoint("after_screenshot")
        snapshot = source_step("source:DOMSnapshot", lambda: cdp.send("DOMSnapshot.captureSnapshot", {"computedStyles": [], "includePaintOrder": True, "includeDOMRects": True}))
        for action in actions:
            action.checkpoint("after_dom_snapshot")
        ax_tree = source_step("source:Accessibility", lambda: cdp.send("Accessibility.getFullAXTree"))
        input_text = source_step("source:input_text", lambda: input_text_evidence(cdp))
        fonts = source_step("source:platform_fonts", lambda: font_evidence(cdp, snapshot, input_text))
        environment = source_step("source:environment", lambda: page.evaluate("({navigator_platform:navigator.platform,user_agent:navigator.userAgent,language:navigator.language,device_pixel_ratio:devicePixelRatio,url:location.href,display_mode:matchMedia('(display-mode: standalone)').matches?'standalone':matchMedia('(display-mode: minimal-ui)').matches?'minimal-ui':'browser',navigator_standalone:navigator.standalone===true,caret_context:(" + CARET_CONTEXT + ")()})"))
        environment.update(platform="macos" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else sys.platform,
                           browser={"name": "Chromium", "version": browser.version}, fonts=fonts)
        (output / (case["id"] + ".dom.json")).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        (output / (case["id"] + ".ax.json")).write_text(json.dumps(ax_tree, ensure_ascii=False), encoding="utf-8")
        (output / (case["id"] + ".input-text.json")).write_text(json.dumps(input_text, ensure_ascii=False), encoding="utf-8")
        for action in actions:
            action.checkpoint("after_source_evidence")
        extractor = (HERE / "reference-elements.js").read_text(encoding="utf-8")
        elements = source_step("source:element_extraction", lambda: page.evaluate(extractor, {"scene_id": case["id"], "lang": manifest["lang"], "theme": manifest["theme"], "dom_snapshot": snapshot, "ax_tree": ax_tree, "input_text_boxes": input_text["inputs"], "input_text_errors": input_text["errors"], "reference_environment": environment}))
        for action in actions:
            action.checkpoint("after_element_extraction")
        if message is not None:
            elements.setdefault("capture_evidence", {})["message_action"] = message.evidence
        if resize is not None:
            elements.setdefault("capture_evidence", {})["textarea_resize_action"] = resize.evidence
        record_caret_coverage(elements, environment.get("caret_context"))
        if member_card is not None:
            elements.setdefault("capture_evidence", {})["member_card_action"] = member_card
        if datalist is not None:
            record_datalist_coverage(elements, datalist)
            (output / (case["id"] + ".datalist-popup.json")).write_text(json.dumps(datalist, ensure_ascii=False), encoding="utf-8")
        (output / (case["id"] + ".elements.json")).write_text(json.dumps(elements, ensure_ascii=False), encoding="utf-8")
    except Exception as error:
        for action in actions:
            action.evidence["errors"].append(str(error))
            action.save()
        raise
    finally:
        try:
            for action in actions:
                action.close()
        finally:
            try:
                cdp.detach()
            finally:
                page.close()


def reference(manifest):
    from playwright.sync_api import sync_playwright
    source = (ROOT / "plugins/relic/app/static/app.js").read_text(encoding="utf-8")
    at = source.rfind("})();")
    assert at > 0
    source = source[:at] + (HERE / "reference-hook.js").read_text(encoding="utf-8") + source[at:]
    with sync_playwright() as pw:
        # Capture the production page's own scrollbar styling. Playwright's
        # default --hide-scrollbars otherwise suppresses visible reference UI.
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"], ignore_default_args=["--hide-scrollbars"])
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
            navigation_scene = "member-card" if case["scene"] in MEMBER_CARD_SCENES else "group" if case["scene"] in MESSAGE_SCENES else "new-org" if case["scene"] in RESIZE_SCENES else case["scene"]
            page.evaluate("([scene, fixture]) => window.__relicVisual(scene, fixture)", [navigation_scene, case_fixture])
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
            member_card = open_member_card_scene(page, case["scene"]) if case["scene"] in MEMBER_CARD_SCENES else None
            if member_card is not None:
                (Path(manifest["output"]) / (case["id"] + ".scene-action.json")).write_text(json.dumps(member_card, ensure_ascii=False), encoding="utf-8")
                if case["scene"] != "member-card-avatar-hover":
                    page.mouse.move(case["width"] + 20, case["height"] + 20)
            datalist = open_datalist_scene(page, cdp, case["scene"]) if case["scene"] in DATALIST_SCENES else None
            animation = prepare_animation_capture(page, cdp, case["scene"])
            if animation is not None:
                (Path(manifest["output"]) / (case["id"] + ".animations.json")).write_text(json.dumps(animation, ensure_ascii=False), encoding="utf-8")
            capture_reference_evidence(page, cdp, browser, manifest, case, member_card, datalist)
            if errors:
                raise RuntimeError(f"{case['id']}: {errors}")
        context.close()
        browser.close()


def font_evidence(cdp, snapshot, input_text):
    """Query real Text nodes, retaining parent aggregates only as raw evidence.

    Chromium accepts any DOM Node here. For a Text node it reads that node's
    LayoutText/ShapeResult; querying an Element instead includes descendant
    LayoutTexts and cannot attribute mixed fonts to a direct text sibling.
    """
    document = snapshot["documents"][0]
    nodes, layout = document["nodes"], document["layout"]
    candidates = {}

    def candidate(backend_id, node_type, source, **identity):
        if not isinstance(backend_id, int) or isinstance(backend_id, bool):
            return
        record = candidates.setdefault(backend_id, {"backend_node_id": backend_id,
            "node_type": node_type, "identities": []})
        record["identities"].append({"source": source, "node_type": node_type, **identity})

    def snapshot_candidate(index, source):
        candidate(nodes["backendNodeId"][index], nodes["nodeType"][index], source,
            snapshot_node_index=index, parent_backend_node_id=(
                nodes["backendNodeId"][nodes["parentIndex"][index]] if nodes["parentIndex"][index] >= 0 else None),
            node_value=snapshot["strings"][nodes["nodeValue"][index]] if nodes.get("nodeValue") else None)

    for offset, node_index in enumerate(layout["nodeIndex"]):
        text_index = layout["text"][offset]
        if text_index < 0 or not snapshot["strings"][text_index]:
            continue
        snapshot_candidate(node_index, "DOMSnapshot.layout.text")
        owner = nodes["parentIndex"][node_index] if nodes["nodeType"][node_index] == 3 else node_index
        if owner >= 0 and owner != node_index:
            snapshot_candidate(owner, "DOMSnapshot.parent-aggregate")
    raw_nodes = {}

    def index_raw(node):
        if isinstance(node.get("backendNodeId"), int):
            raw_nodes[node["backendNodeId"]] = node
        for child in node.get("children", []) + node.get("shadowRoots", []):
            index_raw(child)

    index_raw(input_text.get("raw_document", {}).get("root", {}))
    for measured in input_text["inputs"].values():
        for text_node in measured["text_nodes"]:
            if not text_node["boxes"]:
                continue
            backend_id = text_node.get("backend_node_id")
            actual = raw_nodes.get(backend_id, {})
            # nodeType comes from the pierced DOM receipt, never from a name or
            # the assumption that every input descendant is a Text node.
            candidate(backend_id, actual.get("nodeType"), "DOM.getDocument-UA-text",
                node_value=actual.get("nodeValue"), measured_text=text_node.get("text"))
            owner = text_node.get("font_owner_backend_node_id")
            actual_owner = raw_nodes.get(owner, {})
            candidate(owner, actual_owner.get("nodeType"), "DOM.getDocument-UA-parent-aggregate",
                node_value=actual_owner.get("nodeValue"))
    backend_ids = sorted(candidates)
    result = {"source": "CDP.CSS.getPlatformFontsForNode", "by_backend_node": {},
        "queries": {}, "errors": [], "setup": [],
        "quantity": "actual LayoutText shaping font usage; not per-painted-glyph ink or resolved variation axes"}
    setup_error = None
    for method, parameters in [("CSS.enable", {}),
            ("DOM.pushNodesByBackendIdsToFrontend", {"backendNodeIds": backend_ids})]:
        receipt = {"method": method, "parameters": parameters, "result": None, "error": None}
        result["setup"].append(receipt)
        try:
            receipt["result"] = cdp.send(method, parameters)
        except Exception as error:
            receipt["error"] = str(error)
            result["errors"].append({"method": method, "reason": str(error)})
            setup_error = str(error)
    frontend_ids = (result["setup"][-1]["result"] or {}).get("nodeIds", [])
    for offset, backend_id in enumerate(backend_ids):
        node_id = frontend_ids[offset] if offset < len(frontend_ids) else None
        receipt = {**candidates[backend_id], "frontend_node_id": node_id,
            "scope": "text-node-layout" if candidates[backend_id]["node_type"] == 3 else "descendant-layout-aggregate",
            "request": {"method": "CSS.getPlatformFontsForNode", "parameters": {"nodeId": node_id}},
            "request_sent": False, "result": None, "error": None}
        result["queries"][str(backend_id)] = receipt
        try:
            if setup_error:
                raise RuntimeError("Font query setup failed: " + setup_error)
            if not node_id:
                raise RuntimeError("Rendered text node has no live frontend DOM node")
            receipt["request_sent"] = True
            receipt["result"] = cdp.send(receipt["request"]["method"], receipt["request"]["parameters"])
            fonts = receipt["result"].get("fonts")
            if not isinstance(fonts, list) or not fonts:
                raise RuntimeError("Actual DOM node returned no platform font usage")
            result["by_backend_node"][str(backend_id)] = fonts
        except Exception as error:
            receipt["error"] = str(error)
            result["errors"].append({"backend_node_id": backend_id, "node_type": receipt["node_type"],
                "frontend_node_id": node_id, "reason": str(error)})
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


def stop_native_process(process):
    """Reap this owned client, including a forced kill after a stuck shutdown."""
    forced_kill = False
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            if process.poll() is None:
                process.kill()
                forced_kill = True
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            forced_kill = True
            process.wait(timeout=10)
    else:
        process.wait(timeout=5)
    return {"pid": process.pid, "returncode": process.returncode, "forced_kill": forced_kill}


def sample_native_stall(process, directory, client, reason):
    """Bounded CI macOS sample of the actual owned native client, before reap.

    This callback only records a failed capture. It cannot resume the wait or
    sample a PID taken from a manifest, element request or another process.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.platform != "darwin" or client != "macos":
        return {"status": "not_applicable", "reason": "Only the actual CI macOS native process may be sampled"}
    directory = Path(directory)
    sample_path = directory / "native-stall.sample.txt"
    status_path = directory / "native-stall.sample.json"
    started = time.monotonic()
    status = {"status": "collecting", "capture_failed": True, "trigger": reason,
        "progress_timeout_seconds": 90, "pid": process.pid, "client": client, "platform": sys.platform,
        "sample_seconds": 3, "subprocess_timeout_seconds": 8, "sample_file": sample_path.name,
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sample_written_by_tool": False}
    def save():
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    def output_text(value):
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
    status["process_returncode_before_sample"] = process.poll()
    if (not isinstance(process.pid, int) or isinstance(process.pid, bool) or process.pid <= 0
            or status["process_returncode_before_sample"] is not None):
        status.update(status="unavailable", reason="The actual owned native process has exited or has no valid PID")
        save()
        return status
    command = ["/usr/bin/sample", str(process.pid), "3", "-file", str(sample_path)]
    status["command"] = command
    save()
    try:
        result = subprocess.run(command, timeout=8, capture_output=True, text=True, encoding="utf-8", errors="replace")
        status.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        status["sample_written_by_tool"] = sample_path.exists() and sample_path.stat().st_size > 0
        status["status"] = "sample_collected" if result.returncode == 0 and status["sample_written_by_tool"] else "failed"
        if not status["sample_written_by_tool"]:
            status["reason"] = "sample did not produce a nonempty stack report; retained command output is diagnostic only"
    except subprocess.TimeoutExpired as error:
        status.update(status="timeout", reason=str(error), stdout=output_text(error.stdout), stderr=output_text(error.stderr))
        status["sample_written_by_tool"] = sample_path.exists() and sample_path.stat().st_size > 0
    except Exception as error:
        status.update(status="failed", reason=str(error))
        status["sample_written_by_tool"] = sample_path.exists() and sample_path.stat().st_size > 0
    finally:
        if not status["sample_written_by_tool"]:
            sample_path.write_text(status.get("stdout", "") + status.get("stderr", ""), encoding="utf-8")
            status["sample_file_quantity"] = "Actual sampler stdout/stderr only; no stack report was produced"
        else:
            status["sample_file_quantity"] = "Original sample tool report; timeout/error status is retained independently"
        status["elapsed_seconds"] = time.monotonic() - started
        status["process_returncode_after_sample"] = process.poll()
        save()
    return status


def native_process(manifest_path, manifest, exe):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Native visual capture is CI-only; no local process is launched.")
    environment = dict(os.environ, RELIC_VISUAL_MANIFEST=str(manifest_path), RELIC_VISUAL_OUTPUT=manifest["output"], RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable, RELIC_HOME=manifest["fixture"]["home"], RELIC_VISUAL_NOW=manifest["fixture"]["clock"], TZ="UTC")
    if manifest["client"] == "windows":
        if len(manifest["cases"]) != 1 or not manifest.get("state_directory"):
            raise ValueError("Windows capture requires one case and its isolated native state directory")
        environment["RELIC_VISUAL_STATE_DIR"] = manifest["state_directory"]
        (manifest_path.parent / "current-case.txt").write_text("startup: launching native executable", encoding="utf-8")
    with (manifest_path.parent / "client.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=environment, stdout=log, stderr=log)
        completed_requests, capture_errors = set(), []
        expected_ids = {case["id"] for case in manifest["cases"]}
        def capture_elements():
            if manifest["client"] != "windows":
                return
            pending = pending_element_request(manifest_path.parent, completed_requests)
            if pending is None:
                return
            request_path, request = pending
            last_request = request["case_id"]
            if last_request not in expected_ids or request.get("pid") != process.pid:
                raise RuntimeError(f"Element request is not bound to this case/process: {last_request}, request PID {request.get('pid')}, client PID {process.pid}")
            output = Path(manifest["output"])
            raw = output / (last_request + ".uia.json")
            try:
                result = subprocess.run([manifest["uia_exe"], "--request", str(request_path), "--output", str(raw)], timeout=75, capture_output=True, text=True)
                with (manifest_path.parent / "uia.log").open("a", encoding="utf-8") as observer_log:
                    observer_log.write(f"case={last_request} pid={process.pid} returncode={result.returncode}\n{result.stdout}\n{result.stderr}\n")
                if result.returncode:
                    raise RuntimeError(f"UIA extractor exited {result.returncode}: {result.stderr}")
            except Exception as error:
                capture_errors.append("UIA capture failed: " + str(error))
                partial = json.loads(raw.read_text(encoding="utf-8-sig")) if raw.exists() else {"raw_nodes": []}
                partial.setdefault("extraction_errors", []).append(str(error))
                raw.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
            from windows_elements import project
            try:
                projected = project(output / (last_request + ".xaml.json"), raw, output / (last_request + ".png"))
            except Exception as error:
                capture_errors.append("Projection failed: " + str(error))
                projected = {"schema_version": 1, "scene_id": last_request, "client": "windows", "viewport": {"width": request["width"], "height": request["height"], "scale": 1}, "elements": [], "extraction_errors": ["Projection failed: " + str(error)]}
            (output / (last_request + ".elements.json")).write_text(json.dumps(projected, ensure_ascii=False), encoding="utf-8")
            receipt = manifest_path.parent / "element-receipts" / (last_request + ".json")
            receipt.parent.mkdir(exist_ok=True)
            receipt.with_suffix(".tmp").write_text(json.dumps({"case_id": last_request}), encoding="utf-8")
            receipt.with_suffix(".tmp").replace(receipt)
            completed_requests.add(last_request)
        try:
            if manifest["client"] == "windows":
                (manifest_path.parent / "process.json").write_text(json.dumps({"pid": process.pid,
                    "case_ids": sorted(expected_ids), "state_directory": manifest["state_directory"],
                    "fixture_home": manifest["fixture"]["home"]}), encoding="utf-8")
            wait_options = {"timeout": 240 if manifest["client"] == "windows" else 1200, "on_tick": capture_elements}
            if manifest["client"] == "macos" and sys.platform == "darwin":
                wait_options["on_stall"] = lambda reason: sample_native_stall(process, manifest_path.parent, manifest["client"], reason)
            receipt = wait_file(manifest_path.parent / "complete.json", process, **wait_options)
            if receipt.get("errors"):
                raise RuntimeError(str(receipt["errors"]))
            for case in manifest["cases"]:
                if not (Path(manifest["output"]) / case["file"]).exists():
                    raise RuntimeError("Missing native screenshot: " + case["id"])
            if manifest["client"] == "windows":
                if receipt.get("count") != 1 or completed_requests != expected_ids:
                    raise RuntimeError("Native completion did not include this case's actual UIA hand-off")
                for case_id in expected_ids:
                    for suffix in (".xaml.json", ".uia.json", ".elements.json"):
                        if not (Path(manifest["output"]) / (case_id + suffix)).exists():
                            raise RuntimeError("Missing native evidence: " + case_id + suffix)
                if capture_errors:
                    raise RuntimeError("; ".join(capture_errors))
            return receipt
        finally:
            if manifest["client"] == "windows":
                cleanup = stop_native_process(process)
                (manifest_path.parent / "process-exit.json").write_text(json.dumps(cleanup), encoding="utf-8")
            elif process.poll() is None:
                process.terminate()
                process.wait(timeout=20)


def native(manifest_path, manifest, exe):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Native visual capture is CI-only; no local process is launched.")
    if manifest["client"] != "windows":
        return native_process(manifest_path, manifest, exe)
    if not manifest["cases"]:
        raise ValueError("Windows capture manifest has no cases")
    results, errors = [], []
    for case in manifest["cases"]:
        work = manifest_path.parent / "cases" / case["id"]
        result = {"case_id": case["id"], "directory": str(work), "status": "failed"}
        created = False
        try:
            # Fresh on-disk state, IPC and logs belong to this one process.
            # Refuse stale case directories rather than accepting old evidence.
            work.mkdir(parents=True)
            created = True
            state = work / "state"
            state.mkdir()
            per_case = dict(manifest, cases=[case], state_directory=str(state))
            case_path = work / "manifest.json"
            case_path.write_text(json.dumps(per_case, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Windows isolated capture: " + case["id"], flush=True)
            result["native_receipt"] = native_process(case_path, per_case, exe)
            result["status"] = "captured"
        except Exception as error:
            result["error"] = str(error)
            errors.append(case["id"] + ": " + str(error))
            if created:
                (work / "capture-exception.log").write_text(traceback.format_exc(), encoding="utf-8")
                progress = work / "current-case.txt"
                result["last_progress"] = progress.read_text(encoding="utf-8-sig") if progress.exists() else None
            print("Windows isolated capture failed: " + case["id"] + ": " + str(error), flush=True)
        results.append(result)
        # Preserve progress even if the CI runner stops before the final case.
        aggregate = {"count": sum(row["status"] == "captured" for row in results),
                     "expected_count": len(manifest["cases"]), "attempted_count": len(results),
                     "errors": errors, "cases": results}
        (manifest_path.parent / "complete.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    return aggregate


def capture_components(manifest_path, manifest, exe=None, reference_output=None):
    """Attempt independent clients; a reference failure cannot suppress native work.

    Native goes first so a stuck browser protocol cannot prevent its attempts.
    Every side still uses the same fixture's real reset endpoint. Existing error
    receipts remain failures; file presence is diagnostic, never a passing count.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Visual capture is CI-only; no local component is launched.")
    result = {"expected_count": len(manifest["cases"]), "components": [], "errors": []}
    destination = manifest_path.parent / "components.json"
    def save():
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    components = [(manifest["client"], manifest)]
    if reference_output is not None and manifest["client"] != "reference":
        components.append(("reference", dict(manifest, client="reference", output=str(reference_output))))
    for client, current in components:
        entry = {"client": client, "status": "started", "count": 0, "errors": []}
        result["components"].append(entry)
        Path(current["output"]).mkdir(parents=True, exist_ok=True)
        save()
        try:
            if client == "reference":
                reference(current)
                entry["count"] = len(current["cases"])
            else:
                if exe is None:
                    raise ValueError("Native capture needs --exe")
                receipt = native(manifest_path, current, exe.resolve())
                entry["receipt"] = receipt
                entry["count"] = receipt.get("count", 0)
                entry["errors"] = receipt.get("errors", [])
            entry["status"] = "failed" if entry["errors"] else "completed"
        except Exception as error:
            entry["status"] = "failed"
            entry["errors"].append(str(error))
            (manifest_path.parent / (client + "-component-exception.log")).write_text(traceback.format_exc(), encoding="utf-8")
        finally:
            entry["artifacts_present"] = {suffix: sum((Path(current["output"]) / (case["id"] + suffix)).is_file()
                for case in current["cases"]) for suffix in (".png", ".elements.json")}
            entry["artifacts_present_quantity"] = "Existing files only; incomplete captures and extraction failures are not acceptance"
            result["errors"].extend(client + ": " + error for error in entry["errors"])
            save()
    return result


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
    scenes = spec["scenes"] if args.matrix == "full" else ["group", "private", "overview", "settings-appearance", "new-org", "copies", "chart", "menu-file", "file-code", "live-tool-output", "live-typing", "member-card-rename", "member-card-model", "member-card-avatar-hover", "message-hover", "message-copy-toast", "new-org-textarea-resized"]
    languages = [args.lang] if args.lang else spec["languages"] if args.matrix == "full" else ["zh-CN"]
    themes = [args.theme] if args.theme else spec["themes"] if args.matrix == "full" else ["light"]
    sizes = spec["sizes"] if args.matrix == "full" else [[1440, 900]]
    capture_errors, captured_client, captured_reference = [], 0, 0
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
                    receipt = capture_components(path, manifest, args.exe, reference_output if args.reference else None)
                    capture_errors.extend(receipt["errors"])
                    for component in receipt["components"]:
                        if component["client"] == args.client: captured_client += component["count"]
                        elif component["client"] == "reference": captured_reference += component["count"]
            finally:
                server.terminate()
                server.wait(timeout=20)
    receipt_name = "capture-complete" + ("-" + args.lang + "-" + args.theme if args.lang and args.theme else "") + ".json"
    expected_count = len(scenes) * len(sizes) * len(languages) * len(themes)
    receipt = {"client": args.client, "matrix": args.matrix, "count": captured_client,
               "expected_count": expected_count, "errors": capture_errors}
    (output / receipt_name).write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    if args.reference:
        (reference_output / receipt_name).write_text(json.dumps({"client": "reference", "platform": args.client,
            "matrix": args.matrix, "count": captured_reference, "expected_count": expected_count,
            "errors": capture_errors}, ensure_ascii=False), encoding="utf-8")


    if capture_errors:
        raise RuntimeError(f"Capture has {len(capture_errors)} component/case error(s); see {output / receipt_name}")


if __name__ == "__main__":
    main()
