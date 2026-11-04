"""Compare independently measured bitmap/gradient background contributions.

This is deliberately not an image-to-gradient recognizer. A native bitmap keeps
its actual BGRA source, placement and provenance. Every pixel in the supplied
window raster is visited; no probes, pattern guesses or missing-data defaults
can produce a match. The caller supplies element_parity.delta_e so the existing
colour metric remains the single authority. Alpha is exact and DeltaE76 <= 3.

Input for both sides:
  kind: "css-conic" | "image-brush"
  opacity: measured cumulative element opacity, opacity_source: nonempty string
  placement: {coordinate_space: "content-window", source: nonempty string,
              local_to_window: [a,b,c,d,e,f], ...}
  raster: {x,y,width,height: integer DEVICE pixels, scale: pixels/window-unit,
           clip_status: "measured", occlusion_status: "measured",
           visibility_source: nonempty string,
           visibility: {encoding: "base64-zlib", format: "A8", data: string}}

The A8 visibility raster must be independently measured over the ENTIRE raster:
it includes background clipping and occlusion/transmission by foreground paint.
An absent mask is not an opaque rectangle. Partial coverage is retained in alpha.
The two rasters must describe the same window-pixel domain; no resizing/alignment
is performed to make screenshots match.

For css-conic, paint is the canonical measured background_image descriptor, and
placement.origin is the measured background-positioning-area origin in local
units. For image-brush, brush is the live CaptureBrushEvidence object and
placement.paint_box is the actual local background painting box. This version
supports Fill and explicitly measured identity brush transforms. A nonidentity
brush transform, unresolved source DPI/filtering or absent painting box fails.

Only axis-aligned, pixel-aligned, piecewise-constant conic gradients can currently
prove complete raster coverage. Their cells do not require guessing the browser's
interpolation space, antialiasing or dithering. Computed CSS stops must also be
losslessly representable in BGRA8 (opaque integer RGB or fully transparent).
Translucent/fractional CSS colors need independently measured browser paint
pixels: computed floats cannot be equated to already-quantized native bytes by
assuming a rounding rule. Unsupported paint remains unknown, not a passing
approximation. Rounded edges require actual visibility-mask data.

Semantics: https://www.w3.org/TR/css-images-4/#conic-gradients and
https://www.w3.org/TR/css-backgrounds-3/#background-position .
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
import math
import zlib
from dataclasses import dataclass
from typing import Callable


class MeasurementError(ValueError):
    """Required independent measurement is missing, malformed or unsupported."""


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require(condition, message):
    if not condition:
        raise MeasurementError(message)


def _source(value, field):
    _require(isinstance(value, str) and bool(value.strip()), field + " has no measurement provenance")


def _vector(value, count, field):
    _require(isinstance(value, (list, tuple)) and len(value) == count and all(_number(x) for x in value), field + " is not a measured finite vector")
    return tuple(value)


def _rectangle(value, field):
    _require(isinstance(value, dict), field + " is missing")
    result = _vector([value.get(key) for key in ("x", "y", "width", "height")], 4, field)
    _require(result[2] > 0 and result[3] > 0, field + " must have positive dimensions")
    return result


def _unit(value, field):
    _require(_number(value) and 0 <= value <= 1, field + " is not a measured opacity")
    return float(value)


def _decode(data, expected, field):
    _require(isinstance(data, str), field + " has no encoded bytes")
    try:
        encoded = base64.b64decode(data, validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(encoded, expected + 1)
    except (ValueError, binascii.Error, zlib.error) as error:
        raise MeasurementError(field + " cannot be decoded: " + str(error)) from error
    _require(len(raw) == expected and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,
             field + " byte count/stream termination does not match measured dimensions")
    return raw


@dataclass(frozen=True)
class Bitmap:
    width: int
    height: int
    bgra: bytes

    def rgba(self, x, y):
        blue, green, red, alpha = self.bgra[(y * self.width + x) * 4:(y * self.width + x + 1) * 4]
        if alpha == 0:
            return (0., 0., 0., 0.)
        return (red * 255 / alpha, green * 255 / alpha, blue * 255 / alpha, float(alpha))


def decode_bitmap(image):
    """Decode only actual captured bytes; never infer pixels from a URI/type."""
    _require(isinstance(image, dict), "ImageBrush source evidence is missing")
    _source(image.get("source"), "ImageBrush source bytes")
    _require(image.get("pixel_format") == "BGRA8-premultiplied", "Unsupported or unknown bitmap pixel format")
    _require(image.get("pixel_buffer_encoding") == "base64-zlib", "Unsupported or unknown bitmap encoding")
    width, height = image.get("pixel_width"), image.get("pixel_height")
    _require(type(width) is int and type(height) is int and width > 0 and height > 0, "Bitmap dimensions are missing or invalid")
    expected = width * height * 4
    _require(image.get("pixel_buffer_length") == expected, "Bitmap buffer length does not agree with dimensions")
    raw = _decode(image.get("pixel_buffer"), expected, "bitmap pixel_buffer")
    _require(all(max(raw[offset:offset + 3]) <= raw[offset + 3] for offset in range(0, expected, 4)),
             "BGRA bytes are not valid premultiplied values")
    return Bitmap(width, height, raw)


@dataclass(frozen=True)
class Raster:
    x: int
    y: int
    width: int
    height: int
    scale: float
    visibility: bytes

    @property
    def domain(self):
        return (self.x, self.y, self.width, self.height, self.scale)


def _raster(value):
    _require(isinstance(value, dict), "Full-window background visibility evidence is missing")
    _require(all(type(value.get(key)) is int for key in ("x", "y", "width", "height")), "Raster bounds must be measured device-pixel integers")
    _require(value["width"] > 0 and value["height"] > 0, "Raster dimensions must be positive")
    _require(_number(value.get("scale")) and value["scale"] > 0, "Raster scale is unknown")
    _require(value.get("clip_status") == "measured", "Background clipping/rounded-edge coverage is unknown")
    _require(value.get("occlusion_status") == "measured", "Foreground occlusion/transmission of background is unknown")
    _source(value.get("visibility_source"), "visibility mask")
    mask = value.get("visibility")
    _require(isinstance(mask, dict) and mask.get("format") == "A8" and mask.get("encoding") == "base64-zlib", "Actual full A8 visibility raster is missing")
    raw = _decode(mask.get("data"), value["width"] * value["height"], "visibility raster")
    return Raster(*(value[key] for key in ("x", "y", "width", "height", "scale")), raw)


def _placement(value):
    _require(isinstance(value, dict) and value.get("coordinate_space") == "content-window", "Background placement coordinate space is unknown")
    _source(value.get("source"), "background placement")
    matrix = _vector(value.get("local_to_window"), 6, "local_to_window")
    a, b, c, d, _, _ = matrix
    _require(b == c == 0 and a > 0 and d > 0, "Rotated/skewed/reflected element paint needs independently measured rasterization")
    return matrix


def _aligned(value, field):
    # This is an exact sampling-domain requirement, not geometric tolerance.
    _require(value == round(value), field + " crosses device pixels; actual filtering/antialias evidence is required")


def _same_color(left, right):
    return left == right or left[3] == right[3] == 0


def _identity(value, field):
    if value is None:
        return
    _require(isinstance(value, dict), field + " is unmeasured")
    actual = tuple(value.get(key) for key in ("m11", "m12", "m21", "m22", "offset_x", "offset_y"))
    _require(actual == (1, 0, 0, 1, 0, 0), field + " needs a measured composed source-pixel mapping")


def _bitmap_sampler(record, raster):
    brush = record.get("brush")
    _require(isinstance(brush, dict), "Actual native brush record is missing")
    image = brush.get("image")
    bitmap = decode_bitmap(image)
    opacity = _unit(brush.get("opacity"), "ImageBrush opacity")
    for key in ("transform", "relative_transform"):
        _require(key in image, "ImageBrush " + key + " was not measured")
        _identity(image[key], "ImageBrush " + key)
    _require(image.get("stretch") == "Fill", "Non-Fill ImageBrush needs measured intrinsic DPI and resolved placement")
    _require(image.get("alignment_x") in ("Left", "Center", "Right") and image.get("alignment_y") in ("Top", "Center", "Bottom"), "ImageBrush alignment is unknown")
    placement = record["placement"]
    x, y, width, height = _rectangle(placement.get("paint_box"), "actual local background paint_box")
    a, _, _, d, e, f = _placement(placement)
    left, top = (x * a + e) * raster.scale, (y * d + f) * raster.scale
    device_width, device_height = width * a * raster.scale, height * d * raster.scale
    _aligned(left, "Bitmap left edge"); _aligned(top, "Bitmap top edge")
    _require(device_width == bitmap.width and device_height == bitmap.height,
             "Bitmap is not mapped one source pixel to one device pixel; actual resampling filter is unknown")

    def sample(px, py):
        sx, sy = px - int(left), py - int(top)
        _require(0 <= sx < bitmap.width and 0 <= sy < bitmap.height, "Visible background pixel lies outside measured ImageBrush paint box")
        red, green, blue, alpha = bitmap.rgba(sx, sy)
        return red, green, blue, alpha * opacity

    return sample


def _conic_sampler(record, raster):
    paint = record.get("paint")
    _require(isinstance(paint, dict) and paint.get("kind") == "conic-gradient", "Only measured conic-gradient descriptors are implemented")
    width, height = _vector(paint.get("size"), 2, "gradient tile size")
    _require(width > 0 and height > 0, "Gradient tile size must be positive")
    position = _vector(paint.get("position"), 2, "gradient position")
    cx, cy = _vector(paint.get("center"), 2, "gradient center")
    angle = paint.get("angle")
    _require(_number(angle) and isinstance(paint.get("repeating"), bool), "Gradient angle/repeating state is unknown")
    _require(angle % 90 == 0, "Non-axis-aligned conic rays need measured browser rasterization")
    repeat = paint.get("repeat")
    _require(isinstance(repeat, list) and len(repeat) == 2 and all(axis in ("repeat", "no-repeat") for axis in repeat), "Unresolved round/space or unknown background repeat")
    raw_stops = paint.get("stops")
    _require(isinstance(raw_stops, list) and len(raw_stops) >= 2, "Gradient stop measurements are missing")
    stops = []
    for stop in raw_stops:
        _require(isinstance(stop, dict) and _number(stop.get("position")), "Gradient stop position is unknown")
        color = _vector(stop.get("color"), 4, "gradient stop RGBA")
        _require(all(0 <= value <= 255 for value in color), "Gradient stop RGBA is out of range")
        _require(color[3] == 0 or color[3] == 255 and all(value == round(value) for value in color[:3]),
                 "Translucent/fractional computed CSS color lacks measured browser premultiplication/quantization; it is not an actual BGRA8 paint pixel")
        _require(not stops or stop["position"] >= stops[-1][0], "Gradient stop fixup has not been resolved")
        _require((stop["position"] * 4).is_integer() if isinstance(stop["position"] * 4, float) else (stop["position"] * 4) % 1 == 0,
                 "Non-axis-aligned gradient stop needs measured browser rasterization")
        stops.append((stop["position"], color))
    _require(all(right[0] == left[0] or _same_color(left[1], right[1]) for left, right in zip(stops, stops[1:])),
             "Continuous color interpolation/dithering is not independently measured")
    period = stops[-1][0] - stops[0][0]
    _require(not paint["repeating"] or period > 0 and 1 / period == round(1 / period), "Repeating conic period needs resolved rasterization")
    a, _, _, d, e, f = _placement(record["placement"])
    ox, oy = _vector(record["placement"].get("origin"), 2, "background-positioning origin")
    left, top = ((ox + position[0]) * a + e) * raster.scale, ((oy + position[1]) * d + f) * raster.scale
    sx, sy = a * raster.scale, d * raster.scale
    for name, value in (("Gradient origin x", left), ("Gradient origin y", top), ("Gradient tile width", width * sx), ("Gradient tile height", height * sy), ("Gradient center x", cx * sx), ("Gradient center y", cy * sy)):
        _aligned(value, name)

    def sample(px, py):
        x, y = (px + .5 - left) / sx, (py + .5 - top) / sy
        if repeat[0] == "repeat": x %= width
        elif not 0 <= x < width: return (0., 0., 0., 0.)
        if repeat[1] == "repeat": y %= height
        elif not 0 <= y < height: return (0., 0., 0., 0.)
        turn = (math.atan2(x - cx, cy - y) / math.tau - angle / 360) % 1
        if paint["repeating"]: turn = (turn - stops[0][0]) % period + stops[0][0]
        color = stops[0][1]
        for at, candidate in stops:
            if at > turn: break
            color = candidate
        return color

    return sample


def background_pattern_kind(element):
    """Actual ImageBrush evidence takes priority over a conflicting descriptor."""
    evidence = element.get("evidence") if isinstance(element, dict) else None
    brushes = evidence.get("brush_evidence") if isinstance(evidence, dict) else None
    brush = brushes.get("background") if isinstance(brushes, dict) else None
    if isinstance(brush, dict) and brush.get("type") == "Microsoft.UI.Xaml.Media.ImageBrush":
        return "image-brush"
    style = element.get("style") if isinstance(element, dict) else None
    paint = style.get("background_image") if isinstance(style, dict) else None
    if isinstance(paint, dict) and paint.get("kind") in ("conic-gradient", "image-brush"):
        return "css-conic" if paint["kind"] == "conic-gradient" else "image-brush"
    return None


def captured_pattern(element):
    """Bind a pattern to its own captured paint, never a supplied replacement.

    ``evidence.background_pattern_measurement`` is a capture-side contract, not
    a promise that a DOM/XAML rectangle is an unobstructed paint raster. It must
    name this element's actual source id and supply placement, full visibility
    raster and opacity provenance. CSS paint comes only from style; ImageBrush
    bytes come only from the retained live brush evidence. No current extractor
    may synthesize the missing mask from bounds or five screenshot probes.
    """
    _require(isinstance(element, dict), "Pattern element is missing")
    style, evidence = element.get("style"), element.get("evidence")
    _require(isinstance(style, dict) and isinstance(evidence, dict), "Captured style/evidence is missing")
    measurement = evidence.get("background_pattern_measurement")
    _require(isinstance(measurement, dict), "Independent background pattern placement/visibility measurement is missing")
    _require(isinstance(element.get("id"), str) and measurement.get("source_id") == element["id"],
             "Background pattern measurement is not bound to this actual element source")
    # A fully measured tiny crop is not full visible-background coverage. The
    # raster must contain the actual element's entire measured visible bounds;
    # the independently captured mask still decides clipping/occlusion within
    # this envelope. Never fill that mask from this rectangle.
    raster = _raster(measurement.get("raster"))
    x, y, width, height = _rectangle(element.get("visible_bounds", element.get("bounds")), "actual visible element bounds")
    _require(raster.x <= x * raster.scale and raster.y <= y * raster.scale
             and raster.x + raster.width >= (x + width) * raster.scale
             and raster.y + raster.height >= (y + height) * raster.scale,
             "Background raster does not cover the entire measured visible element bounds")
    result = {"opacity": style.get("opacity"), "opacity_source": measurement.get("opacity_source"),
              "placement": deepcopy(measurement.get("placement")), "raster": deepcopy(measurement.get("raster"))}
    paint = style.get("background_image")
    if background_pattern_kind(element) == "css-conic":
        result.update(kind="css-conic", paint=deepcopy(paint))
    else:
        brushes = evidence.get("brush_evidence")
        brush = brushes.get("background") if isinstance(brushes, dict) else None
        _require(isinstance(brush, dict) and brush.get("type") == "Microsoft.UI.Xaml.Media.ImageBrush",
                 "Actual live ImageBrush background evidence is missing")
        _require(isinstance(paint, dict) and paint.get("kind") == "image-brush" and paint.get("source_id") == element["id"],
                 "ImageBrush background descriptor is missing or disagrees with its actual source")
        result.update(kind="image-brush", brush=deepcopy(brush))
    return result


def _prepare_pattern(record):
    _require(isinstance(record, dict), "Pattern record is missing")
    raster = _raster(record.get("raster"))
    opacity = _unit(record.get("opacity"), "cumulative element opacity")
    _source(record.get("opacity_source"), "cumulative element opacity")
    _placement(record.get("placement"))
    _require(record.get("kind") in ("css-conic", "image-brush"), "Unsupported independent paint type")
    sample = _conic_sampler(record, raster) if record["kind"] == "css-conic" else _bitmap_sampler(record, raster)
    return raster, opacity, sample


def pattern_measurement_issue(record):
    """One concrete failure per source, without expanding every absent field."""
    try:
        _prepare_pattern(record)
    except MeasurementError as error:
        return str(error)
    return None


def compare_paint_patterns(reference, native, *, color_distance: Callable):
    """Return match/mismatch/unmeasured; unknown evidence can never match.

    mismatch_runs encode every mismatching pixel (inclusive x0, exclusive x1),
    rather than retaining a few representative samples. Raw capture buffers
    remain the source for regenerating pixel values and heatmaps.
    """
    report = {"status": "unmeasured", "complete": False, "quantity": "unassociated-srgb-visible-background-contribution",
              "visited_pixels": 0, "visible_pixels": 0, "compared_pixels": 0, "mismatched_pixels": 0,
              "color_mismatches": 0, "alpha_mismatches": 0, "maximum_delta_e_76": 0.,
              "color_tolerance": 3, "alpha_tolerance": 0, "mismatch_runs": [], "errors": []}
    prepared = []
    for name, record in (("reference", reference), ("native", native)):
        try:
            prepared.append(_prepare_pattern(record))
        except MeasurementError as error:
            report["errors"].append({"side": name, "reason": str(error)})
    if report["errors"]: return report
    ar, ao, af = prepared[0]; br, bo, bf = prepared[1]
    if ar.domain != br.domain:
        report["errors"].append({"reason": "Window raster domains differ; no automatic alignment/resizing is permitted", "reference": ar.domain, "native": br.domain})
        return report
    for y in range(ar.height):
        run = None
        for x in range(ar.width):
            index = y * ar.width + x; px, py = ar.x + x, ar.y + y
            report["visited_pixels"] += 1
            masks = ar.visibility[index], br.visibility[index]
            if masks == (0, 0):
                if run is not None: report["mismatch_runs"].append(run); run = None
                continue
            report["visible_pixels"] += 1
            try:
                ac = list(af(px, py)) if masks[0] else [0., 0., 0., 0.]
                bc = list(bf(px, py)) if masks[1] else [0., 0., 0., 0.]
                ac[3] *= ao * masks[0] / 255; bc[3] *= bo * masks[1] / 255
                distance = 0. if ac[3] == bc[3] == 0 else color_distance(ac, bc)
                _require(_number(distance) and distance >= 0, "Colour-distance function returned an invalid measurement")
            except MeasurementError as error:
                report["errors"].append({"x": px, "y": py, "reason": str(error)})
                # The full domain is still visited; unknown pixels never count
                # as compared, and any such error prevents a complete result.
                if run is not None: report["mismatch_runs"].append(run); run = None
                continue
            report["compared_pixels"] += 1; report["maximum_delta_e_76"] = max(report["maximum_delta_e_76"], distance)
            color_bad, alpha_bad = distance > 3, ac[3] != bc[3]
            if color_bad or alpha_bad:
                report["mismatched_pixels"] += 1; report["color_mismatches"] += int(color_bad); report["alpha_mismatches"] += int(alpha_bad)
                if run is None: run = {"y": py, "x0": px, "x1": px + 1}
                else: run["x1"] = px + 1
            elif run is not None:
                report["mismatch_runs"].append(run); run = None
        if run is not None: report["mismatch_runs"].append(run)
    if not report["visible_pixels"]:
        report["errors"].append({"reason": "No independently measured visible background pixels; zero samples are not proof of matching paint"})
    if not report["errors"]:
        report["complete"] = True
        report["status"] = "mismatch" if report["mismatched_pixels"] else "match"
    return report
