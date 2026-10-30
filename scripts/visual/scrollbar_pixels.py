"""Read real reference PNG scrollbar ink without inventing transparent part boxes.

No browser, image drawing, resizing, DOM mutation or scroll-ratio geometry.
Only a fully exposed, independently measured integer gutter is eligible. Full
pixel runs remain evidence even when attribution is ambiguous. The thumb's
outer/hit rectangles and canonical paint remain unknown in every path here.
"""
from collections import Counter, deque
import json
import math
from pathlib import Path


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def rgba(value):
    return isinstance(value, list) and len(value) == 4 and all(finite(v) and 0 <= v <= 255 for v in value)


def only_thumb_paint(parts):
    """Actual pseudo requests restrict attribution; they do not supply geometry."""
    expected = {"::-webkit-scrollbar", "::-webkit-scrollbar-button", "::-webkit-scrollbar-track",
        "::-webkit-scrollbar-track-piece", "::-webkit-scrollbar-thumb", "::-webkit-scrollbar-corner", "::-webkit-resizer"}
    if not isinstance(parts, list) or {p.get("pseudo") for p in parts} != expected:
        return "Actual computed evidence does not cover all possible scrollbar paint parts"
    for part in parts:
        if (part.get("background_image") != "none" or part.get("box_shadow") != "none"
                or part.get("content") not in ("normal", "none", '""')
                or part.get("transform") != "none" or part.get("filter") != "none"
                or part.get("mix_blend_mode") != "normal" or part.get("opacity") != "1"):
            return "A scrollbar pseudo contains unresolved image, generated content, effect or opacity"
        background = part.get("computed_background_rgba")
        if not rgba(background):
            return "A pseudo background has no independently parsed computed sRGB value"
        if part["pseudo"] == "::-webkit-scrollbar-thumb":
            if background[3] <= 0:
                return "Actual thumb background is transparent; PNG ink cannot be assigned from it"
        elif background[3] != 0:
            return "Another actual scrollbar pseudo can paint the reserved gutter"
        widths, styles, colors = (part.get(key) for key in ("border_widths", "border_styles", "computed_border_rgba"))
        if not all(isinstance(values, list) and len(values) == 4 for values in (widths, styles, colors)):
            return "A pseudo border paint witness is incomplete"
        if any(width != "0px" and style not in ("none", "hidden") and (not rgba(color) or color[3] != 0)
                for width, style, color in zip(widths, styles, colors)):
            return "A pseudo border can contribute separate visible ink"
    return None


def measure_gutter_pixels(rows, evidence, axis):
    """Inspect captured pixel cells. Never consult scroll offset/range for bounds."""
    gutter = evidence.get("gutters", {}).get(axis, {})
    bounds = gutter.get("bounds")
    result = {"orientation": axis, "status": "unknown", "ink_bounds": None, "outer_bounds": None, "hit_bounds": None,
        "reason": None, "gutter": gutter, "pixel_runs": [], "components": [], "colors": [],
        "quantity": "original PNG occupied pixel-cell envelope; not continuous ink boundary, transparent thumb border box or hit rectangle"}
    def fail(reason):
        result["reason"] = reason
        return result
    if not isinstance(bounds, dict) or not all(isinstance(bounds.get(k), int) and not isinstance(bounds[k], bool) for k in ("x", "y", "width", "height")):
        return fail("No exact integer DOM gutter rectangle is available for original pixel extraction")
    height, width = len(rows), len(rows[0]) if rows else 0
    if width != bounds["width"] or height != bounds["height"] or any(len(row) != width for row in rows):
        return fail("Actual PNG crop dimensions differ from the measured DOM gutter")
    if not width or not height or any(not rgba(list(pixel)) or any(int(v) != v for v in pixel) for row in rows for pixel in row):
        return fail("Original PNG pixel cells are missing or not RGBA8")
    counts = Counter(tuple(pixel) for row in rows for pixel in row)
    result["colors"] = [{"rgba": list(color), "count": count} for color, count in sorted(counts.items())]
    for y, row in enumerate(rows):
        start = 0
        for x in range(1, width + 1):
            if x == width or row[x] != row[start]:
                result["pixel_runs"].append({"x": bounds["x"] + start, "y": bounds["y"] + y,
                    "width": x - start, "rgba": list(row[start])})
                start = x
    if gutter.get("fully_visible") is not True:
        return fail("Reserved gutter is clipped, occluded or lacks a complete visibility witness")
    ancestry = evidence.get("ancestry")
    if not isinstance(ancestry, list) or not ancestry or any(
            part.get("opacity") != "1" or part.get("filter") != "none" or part.get("backdrop_filter") != "none"
            or part.get("mix_blend_mode") != "normal" or part.get("clip_path") != "none" or part.get("mask_image") != "none"
            or part.get("background_image") != "none"
            for part in ancestry):
        return fail("Actual ancestor opacity/effects/clipping/background images do not permit unique original-gutter ink attribution")
    reason = only_thumb_paint(evidence.get("parts"))
    if reason:
        return fail(reason)
    if any(pixel[3] != 255 for row in rows for pixel in row):
        return fail("PNG gutter pixels are not opaque; composited background is unresolved")
    edge = [tuple(pixel) for pixel in rows[0] + rows[-1]] + [tuple(row[x]) for row in rows for x in (0, width - 1)]
    if len(set(edge)) != 1:
        return fail("Actual gutter perimeter does not expose a single uniform background")
    background = edge[0]
    result["observed_background_rgba"] = list(background)
    if counts[background] <= width * height / 2:
        return fail("Actual perimeter color is not a unique majority gutter background")
    pixels = {(x, y) for y, row in enumerate(rows) for x, pixel in enumerate(row) if tuple(pixel) != background}
    result["non_background_pixel_count"] = len(pixels)
    if not pixels:
        return fail("No independently visible thumb ink is distinguishable in the actual PNG; absence is not inferred")
    thumb = next(part for part in evidence["parts"] if part["pseudo"] == "::-webkit-scrollbar-thumb")
    foreground = thumb["computed_background_rgba"]
    # RGB cell quantization only: no DeltaE/tolerance matching and no expected
    # thumb position/length. Values outside the measured foreground/background
    # channel interval imply an additional or differently composited painter.
    if any(any(not math.floor(min(foreground[c], background[c])) <= rows[y][x][c] <= math.ceil(max(foreground[c], background[c]))
            for c in range(3)) for x, y in pixels):
        return fail("Actual non-background pixels cannot be attributed solely to the measured thumb fill")
    pending = set(pixels)
    while pending:
        first = min(pending, key=lambda point: (point[1], point[0])); pending.remove(first)
        queue, component = deque([first]), [first]
        while queue:
            x, y = queue.popleft()
            for adjacent in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if adjacent in pending:
                    pending.remove(adjacent); queue.append(adjacent); component.append(adjacent)
        xs, ys = [p[0] for p in component], [p[1] for p in component]
        result["components"].append({"pixel_count": len(component), "ink_bounds": {"x": bounds["x"] + min(xs), "y": bounds["y"] + min(ys),
            "width": max(xs) - min(xs) + 1, "height": max(ys) - min(ys) + 1}})
    if len(result["components"]) != 1:
        return fail("Multiple disconnected PNG ink components make individual scrollbar-part attribution ambiguous")
    result.update(status="measured-ink", ink_bounds=result["components"][0]["ink_bounds"],
        attribution="one actual connected non-background component in an independently reserved and exposed gutter; computed pseudo witnesses allow only the thumb fill")
    return result


def append_scrollbar_pixels(elements, png_path, evidence_path):
    owners = [raw for raw in elements.get("raw_nodes", []) if raw.get("scrollbar")]
    if not owners:
        return
    receipt = {"source": "original reference PNG decoded without resizing or drawing", "file": Path(png_path).name,
        "parts": [], "errors": []}
    image = raster = None
    try:
        from PIL import Image
        image = Image.open(png_path)
        receipt.update(format=image.format, mode=image.mode, size=list(image.size))
        viewport = elements.get("viewport", {})
        if image.format != "PNG" or image.mode not in ("RGB", "RGBA") or viewport.get("scale") != 1 or list(image.size) != [viewport.get("width"), viewport.get("height")]:
            raise ValueError("Original PNG format/mode/size does not match a 1:1 reference viewport")
        raster = image.convert("RGBA")
        for raw in owners:
            source = raw["scrollbar"]
            for axis in source["axes"]:
                gutter = source.get("gutters", {}).get(axis, {})
                box = gutter.get("bounds")
                rows = []
                if isinstance(box, dict) and all(isinstance(box.get(k), int) for k in ("x", "y", "width", "height")) and 0 <= box["x"] <= box["x"] + box["width"] <= raster.width and 0 <= box["y"] <= box["y"] + box["height"] <= raster.height:
                    rows = [[raster.getpixel((x, y)) for x in range(box["x"], box["x"] + box["width"])]
                        for y in range(box["y"], box["y"] + box["height"])]
                measured = measure_gutter_pixels(rows, source, axis)
                measured["owner"] = raw["id"]
                receipt["parts"].append(measured)
                summary = {key: value for key, value in measured.items() if key != "pixel_runs"}
                summary.update(file=Path(evidence_path).name, pixel_runs_quantity="all actual RGBA8 cells, losslessly grouped into horizontal equal-color runs")
                raw["scrollbar"].setdefault("original_png", {})[axis] = summary
                for item in elements.get("elements", []):
                    if item.get("id") == raw["id"] + ":scrollbar-thumb:" + axis:
                        item["evidence"]["original_png"] = summary
                        item["evidence"]["ink_bounds"] = measured["ink_bounds"]
                        item["evidence"]["painted_presence"] = True if measured["status"] == "measured-ink" else None
                if measured["status"] != "measured-ink":
                    elements.setdefault("coverage", {}).setdefault("unmeasured", []).append({"element": raw["id"] + ":scrollbar-thumb:" + axis,
                        "property": "scrollbar.original_png_ink", "reason": measured["reason"]})
    except Exception as error:
        receipt["errors"].append(str(error))
        elements.setdefault("extraction_errors", []).append({"type": "scrollbar_png_measurement_failed", "reason": str(error)})
    finally:
        if raster is not None:
            raster.close()
        if image is not None:
            image.close()
        Path(evidence_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        elements.setdefault("capture_evidence", {})["scrollbar_pixels"] = {"file": Path(evidence_path).name,
            "source_png": Path(png_path).name, "parts": len(receipt["parts"]), "errors": receipt["errors"],
            "measurement_limit": "Ink never supplies transparent thumb outer/hit bounds, resolved radius/style or pointer-part state. Existing UA-part failures remain."}
