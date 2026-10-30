"""Audit actual AppKit surface fills without deciding popup occlusion.

NativeSurfaceFillView checks its live revision/bounds/effective color before
exporting current_draw. This reader validates the exported draw and independent
mounted-view identities. It does not certify screenshot contribution, sort
views into compositor order, or remove any canonical/AX element.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

SOURCE = "production native surface fill observation"
PROVIDER = "production NativeSurfaceFillView.draw / CGContext.fillPath"
STRUCTURE = "production parent environment and current NSView.subviews ancestry"
FRAME_SOURCE = "actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen"
SCREEN_SPACE = "AppKit screen coordinates (bottom-left)"
REGIONS = {"window", "header", "sidebar", "conversation", "composer", "right-pane", "dialog", "menu"}
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
PATH_TOKEN = re.compile(r"[MLQCZ]|" + NUMBER)


def finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def rect(value):
    return (isinstance(value, dict) and all(finite(value.get(k)) for k in ("x", "y", "width", "height"))
            and value["width"] >= 0 and value["height"] >= 0)


def identity(value):
    return isinstance(value, str) and bool(value)


def path_commands(value):
    """Decode only the command grammar actually emitted by CGPath.applyWithBlock."""
    if not isinstance(value, str) or not value.strip():
        return None
    tokens = PATH_TOKEN.findall(value)
    if PATH_TOKEN.sub("", value).strip():
        return None
    counts = {"M": 2, "L": 2, "Q": 4, "C": 6, "Z": 0}
    commands, index = [], 0
    while index < len(tokens):
        command = tokens[index]
        if command not in counts or not commands and command != "M":
            return None
        end = index + 1 + counts[command]
        if end > len(tokens):
            return None
        try:
            values = [float(token) for token in tokens[index + 1:end]]
        except ValueError:
            return None
        if not all(finite(number) for number in values):
            return None
        commands.append({"command": command, "coordinates": values})
        index = end
    return commands


def fill_observation(value):
    result = {"draw_observation_valid": False, "occlusion_proven": False,
              "presentation_identity_proven": False, "relative_compositing_order_proven": False,
              "measurements": None, "issues": [], "raw": deepcopy(value)}
    issues = result["issues"]

    def require(condition, message):
        if not condition:
            issues.append(message)

    if not isinstance(value, dict):
        issues.append("Native fill observation is not an object")
        return result
    require(value.get("source") == SOURCE, "Unexpected native fill observation source")
    require("owner_identifier" in value and (value["owner_identifier"] is None or identity(value["owner_identifier"])),
            "Actual production owner identifier is missing or malformed")
    require(isinstance(value.get("region"), str) and value["region"] in REGIONS,
            "Actual native fill region is missing or malformed")
    require(value.get("occlusion_proven") is False, "Actual fill must retain its explicit unproven occlusion claim")
    require(identity(value.get("measurement_limit")), "Native fill measurement limit is missing")
    require(value.get("errors") == [], "Producer reports missing/stale fill draw or a malformed error receipt")
    draw = value.get("current_draw")
    if not isinstance(draw, dict):
        issues.append("No current mounted fill draw; earlier draws or other surfaces cannot replace it")
        return result
    require(draw.get("provider") == PROVIDER and draw.get("draw_returned") is True,
            "No returned production CGContext.fillPath observation")
    for field in ("revision", "sequence"):
        require(type(draw.get(field)) is int and draw[field] >= (1 if field == "sequence" else 0),
                "Invalid actual draw " + field)
    structure = value.get("native_structure")
    if not isinstance(structure, dict):
        issues.append("No actual mounted NSView structure")
        structure = {}
    require(structure.get("source") == STRUCTURE, "Unexpected mounted structure source")
    for field in ("view_identity", "window_identity"):
        require(identity(draw.get(field)) and structure.get(field) == draw[field],
                "Draw " + field + " differs from the mounted view")
    require("parent_identifier" in structure and structure.get("parent_identifier") == value.get("owner_identifier"),
            "Production owner and current structure parent differ")
    path = structure.get("native_subview_path")
    require(isinstance(path, list) and all(type(i) is int and i >= 0 for i in path),
            "No actual content-root subview ancestry")
    opacity = value.get("opacity_ancestry")
    valid_opacity = isinstance(opacity, list) and bool(opacity)
    if valid_opacity:
        valid_opacity = all(isinstance(item, dict) and identity(item.get("identity"))
                            and identity(item.get("class")) and finite(item.get("alpha"))
                            and 0 <= item["alpha"] <= 1 for item in opacity)
    require(valid_opacity, "No complete finite actual opacity ancestry")
    if valid_opacity:
        require(opacity[0]["identity"] == draw.get("view_identity")
                and opacity[0]["class"] == "NativeSurfaceFillView", "Opacity ancestry starts at a different painter")
        require(len({item["identity"] for item in opacity}) == len(opacity), "Opacity ancestry repeats a native view")
    require(rect(draw.get("local_bounds")), "Draw local bounds are missing or nonfinite")
    commands = path_commands(draw.get("local_path"))
    require(commands is not None, "Actual CGPath command string is missing or malformed")
    fill = draw.get("fill")
    require(isinstance(fill, list) and len(fill) == 4 and all(finite(n) and 0 <= n <= 255 for n in fill),
            "Actual submitted sRGB fill is missing or malformed")
    require(draw.get("fill_rule") == "nonzero" and draw.get("blend_mode") == "normal"
            and type(draw.get("global_alpha")) in (int, float) and draw["global_alpha"] == 1
            and draw.get("antialias") is True, "Submitted fill operation differs from this producer contract")
    ctm = draw.get("context_ctm")
    require(isinstance(ctm, list) and len(ctm) == 6 and all(finite(n) for n in ctm), "Actual CGContext CTM is unmeasured")
    require(rect(draw.get("context_clip")), "Actual CGContext clip bounds are unmeasured")
    require(rect(value.get("screen_bounds")), "Current AppKit screen bounds are unmeasured")
    require(rect(value.get("screen_clip")), "Current AppKit screen clip is unmeasured")
    frame = value.get("content_screen_frame")
    require(isinstance(frame, dict) and frame.get("source") == FRAME_SOURCE
            and frame.get("coordinate_space") == SCREEN_SPACE and rect(frame.get("bounds"))
            and identity(frame.get("window_identity")) and frame["window_identity"] == draw.get("window_identity"),
            "Actual content screen basis is missing or belongs to another window")
    if issues:
        return result
    result["draw_observation_valid"] = True
    result["measurements"] = {"owner_identifier": value["owner_identifier"], "region": value["region"],
        "draw": deepcopy(draw), "local_path_commands": commands, "screen_bounds": deepcopy(value["screen_bounds"]),
        "screen_clip": deepcopy(value["screen_clip"]), "content_screen_frame": deepcopy(frame),
        "native_structure": deepcopy(structure), "opacity_ancestry": deepcopy(opacity),
        "quantity": "Submitted local CGContext fill and independently observed current AppKit view/screen geometry; not final pixels or covered-element visibility"}
    return result


def read_fill_observations(data, capture_path, scene, viewport):
    """Read retained capture evidence, optionally corroborated by a real local AX file."""
    audit = {"source": "shared reader of actual native_fill_draws", "status": "unavailable",
             "occlusion_proven": False, "relative_compositing_order_proven": False,
             "presentation_identity_proven": False, "observations": [], "issues": [], "inputs_read": []}
    if not isinstance(data, dict):
        return audit
    evidence = data.get("capture_evidence")
    embedded = isinstance(evidence, dict) and "native_fill_draws" in evidence
    supplied = evidence["native_fill_draws"] if embedded else None
    if embedded:
        audit["inputs_read"].append("elements.capture_evidence.native_fill_draws")
    raw_name = data.get("raw_tree", scene + ".ax.json")
    if not isinstance(raw_name, str) or raw_name != scene + ".ax.json":
        audit["issues"].append("Native fill raw_tree is not this exact scene AX sidecar")
    else:
        raw_path = Path(capture_path).parent / raw_name
        if raw_path.is_file():
            try:
                raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
                audit["inputs_read"].append(raw_name)
                if (not isinstance(raw, dict) or raw.get("client") != "macos" or raw.get("caseId") != scene
                        or raw.get("viewport") != {k: viewport[k] for k in ("width", "height")}):
                    audit["issues"].append("Native fill AX sidecar case/client/viewport does not match this capture")
                elif "native_fill_draws" in raw:
                    if embedded and supplied != raw["native_fill_draws"]:
                        audit["issues"].append("Embedded native fills differ from the actually read raw AX observations")
                        audit["conflicting_raw_observations"] = deepcopy(raw["native_fill_draws"])
                    elif not embedded:
                        supplied = raw["native_fill_draws"]
            except (OSError, ValueError) as error:
                audit["issues"].append("Cannot read actual native fill AX sidecar: " + str(error))
    if supplied is None and not embedded:
        audit["unavailable_reason"] = "No actual native_fill_draws field was read; artifact links and older receipts do not supply measurements"
        return audit
    if not isinstance(supplied, list):
        audit["issues"].append("native_fill_draws must be an actual observation array")
        return audit
    audit["observations"] = [fill_observation(item) for item in supplied]
    identities = set()
    for index, observation in enumerate(audit["observations"]):
        for issue in observation["issues"]:
            audit["issues"].append("native_fill_draws[" + str(index) + "]: " + issue)
        raw = observation["raw"]
        view = raw.get("native_structure", {}).get("view_identity") if isinstance(raw, dict) and isinstance(raw.get("native_structure"), dict) else None
        if identity(view):
            if view in identities:
                audit["issues"].append("More than one fill observation claims the same actual view: " + view)
            identities.add(view)
    audit["status"] = "observed-with-errors" if audit["issues"] else "observed"
    audit["observed_draw_count"] = sum(item["draw_observation_valid"] for item in audit["observations"])
    return audit
