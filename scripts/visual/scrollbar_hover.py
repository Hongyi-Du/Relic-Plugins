"""CI-only, post-capture scrollbar hover diagnostic; never canonical geometry.

Actual pointer input and small PNG crops observe the production hover rule.
Neither scroll ratios nor transparent-border expansion supplies a rectangle.
All original elements, errors and PNGs remain unchanged.
"""
import copy
import io
import json
import os
from pathlib import Path

from PIL import Image

from scrollbar_pixels import only_thumb_paint


REVISION = "f842f52ef39fd97b449eb27cff414bf05a98ddce"
VERSION = "156.0.8078.4"
SOURCE_ROOT = "https://github.com/chromium/chromium/blob/" + REVISION
SOURCES = {
    "integer_pointer_hit_test": SOURCE_ROOT + "/third_party/blink/renderer/core/scroll/scrollbar.cc",
    "actual_thumb_rect_hit_test": SOURCE_ROOT + "/third_party/blink/renderer/core/scroll/scrollbar_theme.cc",
    "actual_part_size": SOURCE_ROOT + "/third_party/blink/renderer/core/layout/custom_scrollbar.cc",
    "hovered_part_selector": SOURCE_ROOT + "/third_party/blink/renderer/core/css/selector_checker.cc#L3663",
    "computed_style_is_not_a_hover_receipt": SOURCE_ROOT + "/third_party/blink/renderer/core/dom/element.cc#L10532",
    "production_css": "plugins/relic/app/static/app.css:82-85",
}
MAX_OWNERS = 2
MAX_OBSERVATIONS = 40  # Per owner, including a reserved restoration crop.


class UnknownObservation(ValueError):
    pass


def require(value, reason):
    if not value:
        raise UnknownObservation(reason)


def candidate_issue(raw, viewport):
    evidence = raw.get("scrollbar") or {}
    if evidence.get("axes") != ["vertical"]:
        return "Only an actual single vertical scrollbar is supported in this diagnostic"
    gutter = evidence.get("gutters", {}).get("vertical", {})
    box = gutter.get("bounds")
    if (viewport.get("scale") != 1 or gutter.get("fully_visible") is not True or not isinstance(box, dict)
            or not all(type(box.get(key)) is int for key in ("x", "y", "width", "height"))
            or not 0 < box["width"] <= 32 or not 0 < box["height"] <= viewport.get("height", 0)
            or box["x"] < 0 or box["y"] < 0 or box["x"] + box["width"] > viewport.get("width", 0)
            or box["y"] + box["height"] > viewport.get("height", 0)):
        return "No wholly exposed, integer, 1:1 viewport gutter with a bounded small crop"
    ancestry = evidence.get("ancestry")
    if not isinstance(ancestry, list) or not ancestry or any(
            item.get("transform") != "none" or item.get("perspective") != "none"
            or item.get("zoom") not in ("1", "normal") for item in ancestry):
        return "Actual ancestor transform/perspective/zoom is not the supported unit coordinate space"
    ink = evidence.get("original_png", {}).get("vertical", {})
    if ink.get("status") != "measured-ink" or not isinstance(ink.get("ink_bounds"), dict):
        return "The original PNG does not independently establish one actual thumb ink component"
    ink_box = ink["ink_bounds"]
    if (not all(type(ink_box.get(key)) is int for key in ("x", "y", "width", "height"))
            or ink_box["width"] <= 0 or ink_box["height"] <= 0
            or ink_box["x"] < box["x"] or ink_box["y"] < box["y"]
            or ink_box["x"] + ink_box["width"] > box["x"] + box["width"]
            or ink_box["y"] + ink_box["height"] > box["y"] + box["height"]):
        return "Actual original ink cells are not wholly inside the measured gutter"
    issue = only_thumb_paint(evidence.get("parts"))
    if issue:
        return issue
    if type(evidence.get("owner_backend_node_id")) is not int:
        return "Actual DOM backend owner identity is missing"
    return None


def browser_matches(version):
    return (isinstance(version, dict) and version.get("product") in ("HeadlessChrome/" + VERSION, "Chrome/" + VERSION)
            and str(version.get("revision", "")).removeprefix("@") == REVISION)


def rgba_png(data):
    with Image.open(io.BytesIO(data)) as image:
        require(image.format == "PNG", "Actual screenshot response is not PNG")
        rgba = image.convert("RGBA")
        return rgba.size, rgba.tobytes()


def classify_response(actual, neutral, hovered):
    if actual == neutral:
        return "miss"
    if actual == hovered:
        return "hit"
    raise UnknownObservation("Actual gutter PNG is neither observed baseline nor observed hover response")


def require_thumb_color_response(neutral, hovered, gutter, ink):
    require(neutral[0] == hovered[0] and neutral != hovered, "Actual seed input produced no distinct thumb hover PNG response")
    width, height = neutral[0]
    require(len(neutral[1]) == len(hovered[1]) == width * height * 4, "Actual PNG RGBA cells are incomplete")
    for offset in range(0, len(neutral[1]), 4):
        if neutral[1][offset:offset + 4] == hovered[1][offset:offset + 4]:
            continue
        x, y = gutter["x"] + (offset // 4) % width, gutter["y"] + (offset // 4) // width
        require(ink["x"] <= x < ink["x"] + ink["width"] and ink["y"] <= y < ink["y"] + ink["height"],
                "Actual seed changed gutter pixels outside the independently observed original thumb ink envelope")


def search_edge(observe, seed, domain_start, domain_end, axis, lower):
    """Actual integer-coordinate membership, with adjacent hit/miss witnesses."""
    def at(value):
        point = list(seed)
        point[axis] = value
        outcome = observe(point)
        require(outcome in ("hit", "miss"), "Unknown observation is not a negative hit test")
        return outcome
    outside = domain_start - 1 if lower else domain_end
    require(at(outside) == "miss", "Actual point outside the measured gutter did not produce baseline pixels")
    edge_cell = domain_start if lower else domain_end - 1
    if at(edge_cell) == "hit":
        return edge_cell if lower else edge_cell + 1
    inside, outside = seed[axis], edge_cell
    while abs(inside - outside) > 1:
        midpoint = (inside + outside) // 2
        if at(midpoint) == "hit":
            inside = midpoint
        else:
            outside = midpoint
    return inside if lower else inside + 1


INSTALL = """function() {
  const owner=this, active=document.activeElement;
  const scrollables=Array.from(new Set([document.scrollingElement,...document.querySelectorAll('*')]))
    .filter(el=>el&&(el===owner||el.scrollWidth>el.clientWidth||el.scrollHeight>el.clientHeight));
  return {owner,active,scrollables,originalScroll:scrollables.map(el=>[el.scrollLeft,el.scrollTop])};
}"""
STATE = """function() {
  const box=el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
  const owner=this.owner, style=getComputedStyle(owner);
  return {owner_connected:owner.isConnected,owner_bounds:box(owner),device_pixel_ratio:devicePixelRatio,
    viewport:{width:innerWidth,height:innerHeight},visual_viewport:visualViewport?
      {scale:visualViewport.scale,offset_left:visualViewport.offsetLeft,offset_top:visualViewport.offsetTop}:null,
    owner_metrics:{client_width:owner.clientWidth,client_height:owner.clientHeight,client_left:owner.clientLeft,
      client_top:owner.clientTop,offset_width:owner.offsetWidth,offset_height:owner.offsetHeight,
      scroll_width:owner.scrollWidth,scroll_height:owner.scrollHeight,scroll_left:owner.scrollLeft,scroll_top:owner.scrollTop},
    owner_coordinate_style:{transform:style.transform,perspective:style.perspective,zoom:style.zoom},
    focus:{same_retained_element:document.activeElement===this.active,document_has_focus:document.hasFocus(),
      tag:document.activeElement?.tagName??null,id:document.activeElement?.id??null},
    scrollables:this.scrollables.map((el,index)=>({index,connected:el.isConnected,x:el.scrollLeft,y:el.scrollTop,
      width:el.scrollWidth,height:el.scrollHeight,client_width:el.clientWidth,client_height:el.clientHeight,bounds:box(el)}))};
}"""
RESTORE_STATE = """function() {
  const actions=[];
  this.scrollables.forEach((el,index)=>{const [x,y]=this.originalScroll[index];
    if(el.scrollLeft!==x||el.scrollTop!==y){
      actions.push({action:'restore_changed_scroll',index,before:[el.scrollLeft,el.scrollTop],requested:[x,y]});
      el.scrollTo({left:x,top:y,behavior:'instant'});
    }
  });
  if(document.activeElement!==this.active){
    actions.push({action:'restore_changed_focus',target_connected:this.active?.isConnected??false});
    if(this.active?.isConnected)this.active.focus({preventScroll:true});
  }
  return actions;
}"""


class HoverObservation:
    def __init__(self, page, cdp, raw, viewport, original, directory, pointer):
        self.page, self.cdp, self.raw, self.viewport = page, cdp, raw, viewport
        self.directory, self.pointer = Path(directory), pointer
        self.box = raw["scrollbar"]["gutters"]["vertical"]["bounds"]
        self.original = original
        self.context = None
        self.owner_object = None
        self.initial = None
        self.entry = {"owner": raw["id"], "backend_node_id": raw["scrollbar"]["owner_backend_node_id"],
            "status": "unknown", "observations": [], "errors": [], "calls": [], "restoration": None,
            "diagnostic_observed_hit_bounds": None, "canonical_hit_bounds": None, "canonical_outer_bounds": None,
            "diagnostic_bounds_verified": False,
            "gutter": copy.deepcopy(self.box), "original_ink": copy.deepcopy(raw["scrollbar"]["original_png"]["vertical"]),
            "maximum_observations_including_restore": MAX_OBSERVATIONS}

    def call(self, method, params):
        record = {"method": method, "params": copy.deepcopy(params)}
        self.entry["calls"].append(record)
        try:
            result = self.cdp.send(method, params)
            record["response"] = copy.deepcopy(result)
            require(not result.get("exceptionDetails"), "Actual CDP JavaScript evaluation failed")
            return result
        except Exception as error:
            record["error"] = str(error)
            raise

    def function(self, declaration):
        response = self.call("Runtime.callFunctionOn", {"objectId": self.context, "functionDeclaration": declaration,
            "returnByValue": True})
        require("value" in response.get("result", {}), "Actual browser state response is absent")
        return response["result"]["value"]

    def sample(self, point=None, phase="boundary", restoring=False):
        limit = MAX_OBSERVATIONS if restoring else MAX_OBSERVATIONS - 1
        require(len(self.entry["observations"]) < limit, "Explicit small observation budget exhausted")
        row = {"index": len(self.entry["observations"]), "phase": phase, "requested_pointer": point,
               "status": "unknown", "classification": None}
        self.entry["observations"].append(row)
        if point is not None:
            # Cell centers avoid a fractional-to-integer boundary ambiguity.
            x, y = (point if restoring else (point[0] + .5, point[1] + .5))
            row["input"] = {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0, "pointerType": "mouse"}
            row["input_response"] = self.call("Input.dispatchMouseEvent", row["input"])
        row["before"] = self.function(STATE)
        require(row["before"] == self.initial, "Actual geometry/scroll/focus changed before the gutter screenshot")
        path = self.directory / (str(row["index"]).zfill(2) + "-" + phase + ".png")
        # No animation disabling, scrolling, CSS rewrite, or full-page image.
        data = self.page.screenshot(path=path, clip=self.box, caret="initial", animations="allow", scale="css", timeout=5000)
        row["png"] = path.name
        actual = rgba_png(data)
        require(actual[0] == (self.box["width"], self.box["height"]), "Actual crop size differs from the measured gutter")
        row["after"] = self.function(STATE)
        require(row["after"] == self.initial, "Actual geometry/scroll/focus changed during the gutter screenshot")
        row["status"] = "observed"
        return actual

    def run(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            resolved = self.call("DOM.resolveNode", {"backendNodeId": self.entry["backend_node_id"]})
            owner = resolved.get("object", {}).get("objectId")
            require(isinstance(owner, str), "Actual scrollbar owner could not be resolved")
            self.owner_object = owner
            installed = self.call("Runtime.callFunctionOn", {"objectId": owner, "functionDeclaration": INSTALL, "returnByValue": False})
            self.context = installed.get("result", {}).get("objectId")
            require(isinstance(self.context, str), "Actual retained owner observation context is unavailable")
            self.initial = self.function(STATE)
            self.entry["initial_state"] = self.initial
            evidence = self.raw["scrollbar"]
            require(self.initial.get("owner_connected") is True and self.initial.get("device_pixel_ratio") == 1
                and self.initial.get("owner_bounds") == evidence["owner_bounds"]
                and self.initial.get("visual_viewport") == {"scale": 1, "offset_left": 0, "offset_top": 0}
                and self.initial.get("viewport") == {"width": self.viewport["width"], "height": self.viewport["height"]}
                and self.initial.get("owner_metrics") == {key: evidence[key] for key in self.initial["owner_metrics"]},
                "Actual retained owner/coordinate/scroll metrics differ from the original capture")
            baseline = self.sample(phase="baseline")
            require(baseline == self.original, "Actual baseline gutter differs from the retained original PNG")
            ink = evidence["original_png"]["vertical"]["ink_bounds"]
            seed = [ink["x"] + ink["width"] // 2, ink["y"] + ink["height"] // 2]
            hovered = self.sample(seed, "seed-hover")
            require_thumb_color_response(baseline, hovered, self.box, ink)
            self.entry["observations"][-1]["classification"] = "observed-hover-template"
            neutral = self.sample([self.box["x"] - 1, seed[1]], "outside-control")
            require(neutral == baseline, "Actual outside control did not restore baseline gutter pixels")
            self.entry["observations"][-1]["classification"] = "miss"
            def observe(point):
                actual = self.sample(point)
                outcome = classify_response(actual, baseline, hovered)
                self.entry["observations"][-1]["classification"] = outcome
                return outcome
            x, y, width, height = (self.box[key] for key in ("x", "y", "width", "height"))
            left = search_edge(observe, seed, x, x + width, 0, True)
            right = search_edge(observe, seed, x, x + width, 0, False)
            top = search_edge(observe, seed, y, y + height, 1, True)
            bottom = search_edge(observe, seed, y, y + height, 1, False)
            for point in ([left, top], [right - 1, top], [left, bottom - 1], [right - 1, bottom - 1]):
                require(observe(point) == "hit", "Actual corner does not reproduce the observed rectangular thumb hover response")
            self.entry["diagnostic_observed_hit_bounds"] = {"x": left, "y": top, "width": right - left, "height": bottom - top}
            self.entry["status"] = "observed-awaiting-restoration"
        except Exception as error:
            self.entry["errors"].append(str(error))
        finally:
            if self.context is not None and self.initial is not None:
                restoration = {"known_original_pointer": copy.deepcopy(self.pointer)}
                self.entry["restoration"] = restoration
                try:
                    restoration["state_before"] = self.function(STATE)
                    restoration["state_actions"] = self.function(RESTORE_STATE)
                except Exception as error:
                    self.entry["errors"].append("Restoration state: " + str(error))
                try:
                    # Restore the pointer even if the independent state read or
                    # scroll/focus recovery above failed.
                    restored = self.sample([self.pointer["x"], self.pointer["y"]], "restore", restoring=True)
                    restoration["original_png_equal"] = restored == self.original
                    require(restoration["original_png_equal"], "Restored pointer did not restore original gutter pixels")
                    require(restoration.get("state_actions") == [], "Scroll/focus changed or recovery is unknown; recovery cannot validate the earlier measurement")
                    if not self.entry["errors"]:
                        self.entry["status"] = "diagnostic-observed"
                        self.entry["diagnostic_bounds_verified"] = True
                except Exception as error:
                    self.entry["errors"].append("Restoration: " + str(error))
            if self.entry["errors"]:
                self.entry["status"] = "unknown"
                self.entry["diagnostic_bounds_verified"] = False
            for remote in (self.context, self.owner_object):
                if remote is None:
                    continue
                try:
                    self.call("Runtime.releaseObject", {"objectId": remote})
                except Exception as error:
                    self.entry["errors"].append("Release: " + str(error))
                    self.entry["status"] = "unknown"
                    self.entry["diagnostic_bounds_verified"] = False
        return self.entry


def capture_scrollbar_hover(page, cdp, elements, original_png, receipt_path, known_pointer=None):
    """Return a diagnostic summary without mutating canonical input elements."""
    receipt_path, original_png = Path(receipt_path), Path(original_png)
    receipt = {"source": "actual post-capture pointer hover and production gutter PNG responses", "sources": SOURCES,
        "original_png": original_png.name, "original_png_rewritten": False, "canonical_geometry_supplied": False,
        "existing_gate_errors_removed": False, "status": "unsupported", "parts": [], "errors": [],
        "maximum_owners": MAX_OWNERS, "maximum_observations_per_owner_including_restore": MAX_OBSERVATIONS,
        "known_capture_pointer": copy.deepcopy(known_pointer)}
    owners = [raw for raw in elements.get("raw_nodes", []) if raw.get("scrollbar")]
    try:
        require(os.environ.get("GITHUB_ACTIONS") == "true", "Diagnostic runs only in CI")
        require(isinstance(known_pointer, dict) and known_pointer.get("returned_normally") is True
                and known_pointer.get("scope") == "group-without-subsequent-pointer-actions"
                and all(type(known_pointer.get(key)) in (int, float) for key in ("x", "y")),
                "Current capture pointer is not established; original state cannot be precisely restored")
        version = cdp.send("Browser.getVersion")
        receipt["browser_get_version"] = version
        require(browser_matches(version), "Actual browser version/revision is outside the source-bound diagnostic")
        viewport = elements.get("viewport", {})
        selected = 0
        with Image.open(original_png) as image:
            require(image.format == "PNG" and image.size == (viewport.get("width"), viewport.get("height")),
                    "Actual original PNG dimensions/format differ from the captured viewport")
            for raw in owners:
                issue = candidate_issue(raw, viewport)
                if selected >= MAX_OWNERS:
                    issue = "Explicit small owner observation budget exhausted"
                if issue:
                    receipt["parts"].append({"owner": raw["id"], "status": "unsupported", "reason": issue,
                        "canonical_hit_bounds": None, "canonical_outer_bounds": None})
                    continue
                selected += 1
                box = raw["scrollbar"]["gutters"]["vertical"]["bounds"]
                crop = image.crop((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"])).convert("RGBA")
                directory = receipt_path.with_suffix("") / raw["id"]
                observation = HoverObservation(page, cdp, raw, viewport, (crop.size, crop.tobytes()), directory, known_pointer)
                entry = observation.run()
                entry["crop_directory"] = str(directory.relative_to(receipt_path.parent)).replace("\\", "/")
                receipt["parts"].append(entry)
                if entry.get("status") != "diagnostic-observed":
                    # A failed restoration cannot provide a starting point for
                    # another owner's diagnostic. Preserve all remaining rows.
                    for remaining in owners[owners.index(raw) + 1:]:
                        receipt["parts"].append({"owner": remaining["id"], "status": "unsupported",
                            "reason": "A preceding owner diagnostic did not complete with verified restoration",
                            "canonical_hit_bounds": None, "canonical_outer_bounds": None})
                    break
        receipt["status"] = "diagnostic-only"
    except Exception as error:
        receipt["errors"].append(str(error))
        if not receipt["parts"]:
            receipt["parts"] = [{"owner": raw["id"], "status": "unsupported", "reason": str(error),
                "canonical_hit_bounds": None, "canonical_outer_bounds": None} for raw in owners]
    finally:
        try:
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            receipt["errors"].append("Diagnostic receipt write failed: " + str(error))
            receipt["status"] = "unknown"
    return {"file": receipt_path.name, "status": receipt["status"], "owners": len(receipt["parts"]),
        "observed_owners": sum(part.get("status") == "diagnostic-observed" for part in receipt["parts"]),
        "unknown_or_unsupported_owners": sum(part.get("status") != "diagnostic-observed" for part in receipt["parts"]),
        "canonical_geometry_supplied": False, "existing_gate_errors_removed": False, "errors": receipt["errors"]}
