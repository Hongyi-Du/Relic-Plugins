"""Independent outline measurements. Never reuse a layout border as an outline."""
from copy import deepcopy
import math

from image_paint import ImagePaintError, PATH_TOKEN, _validate_path


FIELDS = {"style", "color", "width", "offset", "dash", "dash_offset", "contour"}


def finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def contour_tokens(contour):
    """Strict absolute paths in window pixels; no inferred rounded-box contour."""
    if not isinstance(contour, dict) or set(contour) != {"coordinate_space", "paths"} or contour["coordinate_space"] != "window":
        raise ValueError("outline contour requires actual window-space paths")
    paths = contour["paths"]
    if not isinstance(paths, list) or not paths:
        raise ValueError("outline contour has no measured paths")
    result = []
    for path in paths:
        if not isinstance(path, dict) or set(path) != {"d"} or not isinstance(path["d"], str):
            raise ValueError("outline path must preserve its measured d string")
        try:
            _validate_path(path["d"], "outline contour")
        except ImagePaintError as error:
            raise ValueError(str(error)) from error
        tokens = [match.group() for match in PATH_TOKEN.finditer(path["d"])]
        if any(value.isalpha() and value not in ("M", "L", "C", "Q", "Z") for value in tokens):
            raise ValueError("outline contour requires absolute M/L/C/Q/Z commands; other representations remain unmeasured")
        result.append([value if value.isalpha() else float(value) for value in tokens])
    return result


def outline_measurement(element):
    """Return independent canonical/basic native evidence and all coverage issues."""
    style = element.get("style") if isinstance(element.get("style"), dict) else {}
    evidence = element.get("evidence") if isinstance(element.get("evidence"), dict) else {}
    raw = style.get("outline")
    issues = []
    if "outline" not in style and isinstance(style.get("native_outline"), dict):
        # Existing macOS receipt only measures these supplied values. Do not
        # invent the absent style category, phase, contour, or completion proof.
        native = style["native_outline"]
        raw = {key: deepcopy(native.get(key)) for key in FIELDS}
        issues.append("native_outline has no complete canonical outline receipt; raw values retained")
    if raw == "none":
        proof = evidence.get("outline")
        if not isinstance(proof, dict) or proof.get("absence_proven") is not True:
            issues.append("outline none has no actual absence proof")
        return raw, issues
    if not isinstance(raw, dict):
        return raw, issues + ["Missing independently measured outline (absence is not inferred from missing fields)"]
    if set(raw) != FIELDS:
        issues.append("outline fields are missing or unknown: " + repr(sorted(set(raw) ^ FIELDS, key=str)))
    for key in ("width", "offset"):
        if not finite(raw.get(key)) or key == "width" and raw[key] <= 0:
            issues.append("outline has no measured " + key + " in window pixels")
    color = raw.get("color")
    if not isinstance(color, list) or len(color) != 4 or not all(finite(value) and 0 <= value <= 255 for value in color):
        issues.append("outline has no measured RGBA color")
    category = raw.get("style")
    if category not in ("solid", "dashed", "dotted"):
        issues.append("outline style is unknown or its actual paint is not represented")
    if category in ("dashed", "dotted"):
        dash = raw.get("dash")
        if not isinstance(dash, list) or not dash or not all(finite(value) and value >= 0 for value in dash) or not any(dash):
            issues.append("outline has no measured actual dash segments")
        if not finite(raw.get("dash_offset")):
            issues.append("outline has no measured actual dash phase")
    elif category == "solid" and (raw.get("dash") != [] or raw.get("dash_offset") is not None):
        issues.append("solid outline requires continuous dash [] and inapplicable dash_offset null")
    try:
        contour_tokens(raw.get("contour"))
    except ValueError as error:
        issues.append(str(error))
    return raw, issues


def compare_outlines(reference, native, *, color_distance, geometry_tolerance):
    """Return strict existing-category records; missing measurements never match."""
    a, issues_a = outline_measurement(reference)
    b, issues_b = outline_measurement(native)
    records = []
    for side, issues in (("reference", issues_a), ("native", issues_b)):
        for issue in issues:
            records.append({"category": "extraction_errors", "field": "outline", "expected": a,
                            "actual": b, "side": side, "reason": issue})
    def mismatch(field, av, bv, **details):
        records.append({"category": "style_out_of_tolerance", "field": "outline." + field,
                        "expected": av, "actual": bv, **details})
    if a == "none" and b == "none":
        return records
    if not isinstance(a, dict) or not isinstance(b, dict):
        if a != b or issues_a or issues_b:
            mismatch("paint", a, b, reason="Outline presence differs or measurement is unknown")
        return records
    for key in ("style", "width", "offset", "dash", "dash_offset"):
        av, bv = a.get(key), b.get(key)
        if av != bv:
            mismatch(key, av, bv)
    ca, cb = a.get("color"), b.get("color")
    valid_color = lambda value: isinstance(value, list) and len(value) == 4 and all(finite(c) and 0 <= c <= 255 for c in value)
    if valid_color(ca) and valid_color(cb):
        distance = 0 if ca[3] == cb[3] == 0 else color_distance(ca, cb)
        if distance > 3 + 1e-8 or ca[3] != cb[3]:
            mismatch("color", ca, cb, delta_e_76=distance, tolerance=3)
    try:
        pa, pb = contour_tokens(a.get("contour")), contour_tokens(b.get("contour"))
    except ValueError:
        return records  # Concrete missing-contour failures already recorded above.
    if len(pa) != len(pb):
        mismatch("contour.paths.length", len(pa), len(pb))
    owner_bounds = reference.get("bounds")
    owner_bounds = owner_bounds if isinstance(owner_bounds, dict) else {}
    for index, (left, right) in enumerate(zip(pa, pb)):
        if len(left) != len(right) or any(isinstance(x, str) != isinstance(y, str) or isinstance(x, str) and x != y for x, y in zip(left, right)):
            mismatch(f"contour.paths[{index}].commands", left, right)
            continue
        axis = 0
        for position, (x, y) in enumerate(zip(left, right)):
            if isinstance(x, str):
                axis = 0
                continue
            extent = owner_bounds.get("width" if axis % 2 == 0 else "height")
            tolerance = geometry_tolerance(extent) if finite(extent) and extent >= 0 else None
            if tolerance is None or abs(x - y) > tolerance + 1e-8:
                record = {"category": "geometry_out_of_tolerance", "field": f"outline.contour.paths[{index}].coordinate[{position}]",
                          "expected": x, "actual": y, "tolerance": tolerance}
                if tolerance is None:
                    record["reason"] = "Outline contour has no measured nonnegative owner extent"
                records.append(record)
            axis += 1
    return records
