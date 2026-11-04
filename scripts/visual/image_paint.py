"""Strict SVG-byte decoding for resource paint identity, not presentation proof.

Only the documented vector-image-v1 subset is accepted. Nothing is fetched, and
neither a resource URI nor an icon name is used to supply missing paint content.
"""
from __future__ import annotations

import base64
import copy
import math
import re
import xml.etree.ElementTree as ET
from typing import Any


SVG = "http://www.w3.org/2000/svg"
NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
NUMBER_RE = re.compile(NUMBER)
ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
PATH_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZz]|" + NUMBER)
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "Z": 0}


class ImagePaintError(ValueError):
    """The resource cannot be completely represented by this strict decoder."""


def _fail(where: str, reason: str) -> None:
    raise ImagePaintError(f"{where}: {reason}")


def _number(raw: str, where: str) -> float:
    raw = raw.strip()
    if not NUMBER_RE.fullmatch(raw):
        _fail(where, f"unsupported or invalid numeric value {raw!r}")
    value = float(raw)
    if not math.isfinite(value):
        _fail(where, "numeric value is nonfinite")
    return 0.0 if value == 0 else value


def _numbers(raw: str, count: int, where: str) -> list[float]:
    values = re.split(r"(?:\s*,\s*|\s+)", raw.strip())
    if len(values) != count or not all(values):
        _fail(where, f"expected exactly {count} numbers")
    return [_number(value, where) for value in values]


def _fraction(raw: str, where: str) -> float:
    raw = raw.strip()
    return _number(raw[:-1], where) / 100 if raw.endswith("%") else _number(raw, where)


def _tag(node: ET.Element) -> str:
    if not isinstance(node.tag, str) or not node.tag.startswith("{" + SVG + "}"):
        _fail("XML", f"unsupported element namespace/tag {node.tag!r}")
    return node.tag[len(SVG) + 2:]


def _check(node: ET.Element, allowed: set[str], where: str, *, leaf: bool = False) -> None:
    unknown = set(node.attrib) - allowed
    if unknown:
        _fail(where, "unsupported attributes: " + ", ".join(sorted(unknown)))
    if (node.text or "").strip() or (node.tail or "").strip():
        _fail(where, "unexpected text content")
    if leaf and len(node):
        _fail(where, "unexpected child elements")


def _color(raw: str, where: str) -> list[int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", raw):
        _fail(where, f"unsupported color {raw!r}; expected #RGB or #RRGGBB")
    digits = raw[1:]
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    return [int(digits[index:index + 2], 16) for index in (0, 2, 4)] + [255]


def _validate_path(data: str, where: str) -> None:
    tokens = list(PATH_TOKEN.finditer(data))
    if not tokens or tokens[0].group() not in ("M", "m"):
        _fail(where, "path must begin with moveto")
    previous_end = 0
    for index, token in enumerate(tokens):
        gap = data[previous_end:token.start()]
        if not re.fullmatch(r"\s*,?\s*", gap):
            _fail(where, f"unsupported path command or syntax {gap!r}")
        if "," in gap and (index == 0 or tokens[index - 1].group().isalpha() or token.group().isalpha()):
            _fail(where, "comma must separate numeric path arguments")
        previous_end = token.end()
    if data[previous_end:].strip():
        _fail(where, "unsupported path suffix or trailing comma")
    command = None
    arguments = 0
    for token in tokens:
        value = token.group()
        if value.isalpha():
            if command and PATH_ARITY[command] and (arguments == 0 or arguments % PATH_ARITY[command]):
                _fail(where, f"incomplete {command} path arguments")
            command, arguments = value.upper(), 0
        else:
            if command is None or PATH_ARITY[command] == 0:
                _fail(where, "numeric arguments without a path command")
            _number(value, where)
            arguments += 1
    if command and PATH_ARITY[command] and (arguments == 0 or arguments % PATH_ARITY[command]):
        _fail(where, f"incomplete {command} path arguments")


def _gradient(node: ET.Element, where: str) -> tuple[str, dict[str, Any]]:
    _check(node, {"id", "x1", "y1", "x2", "y2", "gradientUnits", "spreadMethod"}, where)
    identity = node.get("id", "")
    if not ID_RE.fullmatch(identity):
        _fail(where, "gradient requires a supported nonempty local id")
    if node.get("gradientUnits", "objectBoundingBox") != "objectBoundingBox":
        _fail(where, "only objectBoundingBox gradient units are currently represented")
    if node.get("spreadMethod", "pad") != "pad":
        _fail(where, "only pad gradient spread is currently represented")
    points = [_fraction(node.get(key, default), where + "/" + key)
              for key, default in (("x1", "0%"), ("y1", "0%"), ("x2", "100%"), ("y2", "0%"))]
    if points[:2] == points[2:]:
        _fail(where, "degenerate gradient is outside the represented subset")
    stops = []
    for index, stop in enumerate(node):
        location = f"{where}/stop[{index}]"
        if _tag(stop) != "stop":
            _fail(location, "unsupported gradient child")
        _check(stop, {"offset", "stop-color"}, location, leaf=True)
        if "offset" not in stop.attrib:
            _fail(location, "missing stop offset")
        offset = _fraction(stop.attrib["offset"], location + "/offset")
        if not 0 <= offset <= 1 or stops and offset < stops[-1]["offset"]:
            _fail(location, "stop offsets must be in [0,1] and nondecreasing in this subset")
        stops.append({"offset": offset, "color": _color(stop.get("stop-color", "#000000"), location)})
    if len(stops) < 2:
        _fail(where, "fewer than two gradient stops are outside the represented subset")
    return identity, {"points": points, "stops": stops}


def _fill(raw: str, bounds: list[float] | None, gradients: dict, where: str) -> dict:
    if raw == "none":
        return {"kind": "none"}
    if not raw.startswith("url("):
        return {"kind": "solid", "color": _color(raw, where)}
    match = re.fullmatch(r"url\(#([A-Za-z_][A-Za-z0-9_.-]*)\)", raw)
    if not match or match[1] not in gradients:
        _fail(where, "unresolved or unsupported paint reference; external resources are not fetched")
    if bounds is None:
        _fail(where, "gradient path bounds are not measured by this decoder")
    gradient = gradients[match[1]]
    x1, y1, x2, y2 = gradient["points"]
    x, y, width, height = bounds
    # An anisotropic objectBoundingBox changes a diagonal gradient's normal.
    # Endpoints alone cannot encode that metric; fail rather than approximate it.
    if x1 != x2 and y1 != y2 and width != height:
        _fail(where, "diagonal gradient in a nonsquare object needs an unrepresented gradient metric")
    start = [x + x1 * width, y + y1 * height]
    end = [x + x2 * width, y + y2 * height]
    if not all(math.isfinite(value) for value in start + end):
        _fail(where, "resolved gradient coordinates are nonfinite")
    return {"kind": "linear-gradient", "start": start, "end": end, "spread": "pad",
            "color_space": "srgb", "stops": copy.deepcopy(gradient["stops"])}


def decode_svg_bytes(content: bytes) -> dict[str, Any]:
    """Return canonical resource paint; raise ImagePaintError for any unmodeled content.

    This function deliberately has no URI or icon-name argument. A successful
    parse does not establish that any browser/native image used these bytes.
    """
    if not isinstance(content, bytes):
        _fail("resource", "actual loaded content must be supplied as bytes")
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise ImagePaintError("resource: only UTF-8 SVG bytes are supported") from error
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        _fail("XML", "DTD and entity declarations are unsupported")
    declaration = re.match(r"^\s*<\?xml\s+[^?]*\?>", text)
    if declaration:
        encoding = re.search(r"\bencoding\s*=\s*(['\"])(.*?)\1", declaration.group())
        if encoding and encoding[2].lower() not in ("utf-8", "utf8"):
            _fail("XML", "non-UTF-8 encoding declaration is outside the represented subset")
    without_declaration = re.sub(r"^\s*<\?xml\s+[^?]*\?>", "", text, count=1)
    if "<?" in without_declaration:
        _fail("XML", "processing instructions, including external stylesheets, are unsupported")
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as error:
        raise ImagePaintError("XML: " + str(error)) from error
    if _tag(root) != "svg":
        _fail("XML", "root must be SVG")
    _check(root, {"viewBox"}, "svg")
    if "viewBox" not in root.attrib:
        _fail("svg", "missing viewBox")
    view_box = _numbers(root.attrib["viewBox"], 4, "svg/viewBox")
    if view_box[2] <= 0 or view_box[3] <= 0:
        _fail("svg/viewBox", "width and height must be positive")
    gradients = {}
    for node in root:
        if _tag(node) != "defs":
            continue
        _check(node, set(), "svg/defs")
        for index, definition in enumerate(node):
            where = f"svg/defs[{index}]"
            if _tag(definition) != "linearGradient":
                _fail(where, "unsupported definition")
            identity, gradient = _gradient(definition, where)
            if identity in gradients:
                _fail(where, "duplicate gradient id")
            gradients[identity] = gradient
    layers = []
    for index, node in enumerate(root):
        kind = _tag(node)
        where = f"svg/{kind}[{index}]"
        bounds = None
        if kind == "defs":
            continue
        if kind == "rect":
            _check(node, {"x", "y", "width", "height", "rx", "ry", "fill"}, where, leaf=True)
            if "width" not in node.attrib or "height" not in node.attrib:
                _fail(where, "explicit rectangle width and height are required")
            bounds = [_number(node.get(key, "0"), where + "/" + key) for key in ("x", "y", "width", "height")]
            if bounds[2] <= 0 or bounds[3] <= 0:
                _fail(where, "nonpositive rectangle dimensions are outside the represented subset")
            rx = _number(node.get("rx", node.get("ry", "0")), where + "/rx")
            ry = _number(node.get("ry", node.get("rx", "0")), where + "/ry")
            if min(rx, ry) < 0:
                _fail(where, "negative corner radius")
            # SVG used values inherit the omitted other radius and clamp to half
            # the corresponding extent; this is specification decoding, not a tolerance.
            layer = {"kind": "rounded-rect", "bounds": bounds, "radii": [min(rx, bounds[2] / 2), min(ry, bounds[3] / 2)]}
        elif kind == "circle":
            _check(node, {"cx", "cy", "r", "fill"}, where, leaf=True)
            center = [_number(node.get(key, "0"), where + "/" + key) for key in ("cx", "cy")]
            if "r" not in node.attrib:
                _fail(where, "missing circle radius")
            radius = _number(node.attrib["r"], where + "/r")
            if radius <= 0:
                _fail(where, "nonpositive circle radius is outside the represented subset")
            bounds = [center[0] - radius, center[1] - radius, 2 * radius, 2 * radius]
            layer = {"kind": "circle", "center": center, "radius": radius}
        elif kind == "path":
            _check(node, {"d", "fill", "fill-rule"}, where, leaf=True)
            data = node.get("d", "")
            _validate_path(data, where + "/d")
            rule = node.get("fill-rule", "nonzero")
            if rule not in ("nonzero", "evenodd"):
                _fail(where, "unsupported fill rule")
            layer = {"kind": "path", "d": data, "fill_rule": rule}
        else:
            _fail(where, "unsupported element")
        if bounds is not None and not all(math.isfinite(value) for value in bounds):
            _fail(where, "derived shape bounds are nonfinite")
        layer["fill"] = _fill(node.get("fill", "#000000"), bounds, gradients, where + "/fill")
        layers.append(layer)
    if not layers:
        _fail("svg", "no represented paint layers")
    result = {"source": "vector-image-v1", "glyph": {"view_box": view_box, "layers": layers}}
    validate_vector_paint(result)
    return result


def _fields(value: Any, expected: set[str], where: str) -> None:
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    missing, unknown = expected - set(value), set(value) - expected
    if missing or unknown:
        _fail(where, f"missing fields {sorted(missing)!r}; unknown fields {sorted(unknown, key=str)!r}")


def _finite(value: Any, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, "expected a finite number, not a string/bool/null")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        _fail(where, "expected a finite number")


def _vector(value: Any, size: int, where: str) -> None:
    if not isinstance(value, list) or len(value) != size:
        _fail(where, f"expected an array of {size} finite numbers")
    for index, component in enumerate(value):
        _finite(component, f"{where}[{index}]")


def _rgba(value: Any, where: str) -> None:
    _vector(value, 4, where)
    if any(not 0 <= component <= 255 for component in value) or value[3] != 255:
        _fail(where, "v1 supports opaque sRGB channels in [0,255] with alpha exactly 255")


def _validate_fill(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        _fail(where, "fill must be an object")
    kind = value.get("kind")
    if kind == "none":
        _fields(value, {"kind"}, where)
    elif kind == "solid":
        _fields(value, {"kind", "color"}, where)
        _rgba(value["color"], where + "/color")
    elif kind == "linear-gradient":
        _fields(value, {"kind", "start", "end", "spread", "color_space", "stops"}, where)
        _vector(value["start"], 2, where + "/start")
        _vector(value["end"], 2, where + "/end")
        if value["start"] == value["end"]:
            _fail(where, "degenerate gradient is outside the represented subset")
        if value["spread"] != "pad" or value["color_space"] != "srgb":
            _fail(where, "v1 requires pad spread and srgb interpolation")
        stops = value["stops"]
        if not isinstance(stops, list) or len(stops) < 2:
            _fail(where, "at least two ordered gradient stops are required")
        previous = 0
        for index, stop in enumerate(stops):
            location = f"{where}/stops[{index}]"
            _fields(stop, {"offset", "color"}, location)
            _finite(stop["offset"], location + "/offset")
            if not previous <= stop["offset"] <= 1:
                _fail(location, "stop offsets must be in [0,1] and nondecreasing")
            _rgba(stop["color"], location + "/color")
            previous = stop["offset"]
    else:
        _fail(where, "unknown fill kind")


def validate_vector_paint(value: Any) -> None:
    """Validate the complete v1 canonical object, without normalizing or repairing it.

    Raises ImagePaintError for missing/unknown fields or unsupported paint.
    Validation proves a well-formed resource description, not content binding.
    """
    _fields(value, {"source", "glyph"}, "vector-image-v1")
    if value["source"] != "vector-image-v1":
        _fail("vector-image-v1/source", "source must identify this exact schema")
    glyph = value["glyph"]
    _fields(glyph, {"view_box", "layers"}, "vector-image-v1/glyph")
    _vector(glyph["view_box"], 4, "glyph/view_box")
    if glyph["view_box"][2] <= 0 or glyph["view_box"][3] <= 0:
        _fail("glyph/view_box", "width and height must be positive")
    layers = glyph["layers"]
    if not isinstance(layers, list) or not layers:
        _fail("glyph/layers", "nonempty ordered paint layers are required")
    for index, layer in enumerate(layers):
        where = f"glyph/layers[{index}]"
        if not isinstance(layer, dict):
            _fail(where, "layer must be an object")
        kind = layer.get("kind")
        if kind == "rounded-rect":
            _fields(layer, {"kind", "bounds", "radii", "fill"}, where)
            _vector(layer["bounds"], 4, where + "/bounds")
            _vector(layer["radii"], 2, where + "/radii")
            width, height = layer["bounds"][2:]
            rx, ry = layer["radii"]
            if width <= 0 or height <= 0 or not 0 <= rx <= width / 2 or not 0 <= ry <= height / 2:
                _fail(where, "rectangle dimensions/radii are not valid used values")
        elif kind == "circle":
            _fields(layer, {"kind", "center", "radius", "fill"}, where)
            _vector(layer["center"], 2, where + "/center")
            _finite(layer["radius"], where + "/radius")
            if layer["radius"] <= 0:
                _fail(where, "circle radius must be positive")
            _finite(2 * layer["radius"], where + "/diameter")
        elif kind == "path":
            _fields(layer, {"kind", "d", "fill_rule", "fill"}, where)
            if not isinstance(layer["d"], str):
                _fail(where, "path d must be the actual string")
            _validate_path(layer["d"], where + "/d")
            if layer["fill_rule"] not in ("nonzero", "evenodd"):
                _fail(where, "unsupported path fill rule")
        else:
            _fail(where, "unknown shape kind")
        _validate_fill(layer["fill"], where + "/fill")


def svg_paint_evidence(content: bytes, source_evidence: Any = None) -> dict[str, Any]:
    """Preserve original content and failures beside decoded paint, never binding proof."""
    result = {"status": "error", "paint": None,
              "content_encoding": "base64", "content_bytes": base64.b64encode(content).decode("ascii"),
              "byte_length": len(content), "source_evidence": copy.deepcopy(source_evidence),
              "content_binding_status": "unverified-by-parser", "presentation_identity_proven": False}
    try:
        result["paint"] = decode_svg_bytes(content)
        result["status"] = "decoded"
    except ImagePaintError as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    return result
