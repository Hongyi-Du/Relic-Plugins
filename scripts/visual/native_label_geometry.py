"""Geometry from the one production NativeLabel draw, without reference data.

Every output names its quantity. Layout, selection, font-metric advance and
glyph ink rectangles are not substituted for each other. Unknown final desktop
pixel contribution does not erase independently measured layout/paint bounds.
"""
import copy
import math
import struct


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def rect(value):
    return (isinstance(value, dict) and all(number(value.get(k)) for k in ("x", "y", "width", "height"))
            and value["width"] >= 0 and value["height"] >= 0)


def matrix(value, x="dx", y="dy"):
    if not isinstance(value, dict): return None
    fields = ("m11", "m12", "m21", "m22", x, y)
    return [value[k] for k in fields] if all(number(value.get(k)) for k in fields) else None


def inverse(m):
    if m is None: return None
    a, b, c, d, x, y = m
    det = a * d - b * c
    if not number(det) or det == 0: return None
    result = [d / det, -b / det, -c / det, a / det, (c * y - d * x) / det, (b * x - a * y) / det]
    return result if all(number(v) for v in result) else None


def point(m, p):
    x, y = p
    return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]


def polygon(r):
    x, y, w, h = (r[k] for k in ("x", "y", "width", "height"))
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def envelope(points):
    if not points or any(not number(v) for p in points for v in p): return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def intersect(a, b):
    if not rect(a) or not rect(b): return None
    x, y = max(a["x"], b["x"]), max(a["y"], b["y"])
    right, bottom = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
    if right < x or bottom < y: return None
    return {"x": x, "y": y, "width": right - x, "height": bottom - y}


def empty_native_glyph_outline(run):
    """Validate a same-callback empty base outline, not an empty advance box."""
    evidence = run.get("ink_bounds_evidence")
    if not isinstance(evidence, dict): return False
    outline = evidence.get("outline")
    if (evidence.get("source") != "Actual GetGlyphRunWorldBounds result and same-callback glyph outline observation"
            or run.get("source") != "IDWriteTextLayout.Draw -> IDWriteTextRenderer.DrawGlyphRun -> ID2D1RenderTarget.DrawGlyphRun"
            or run.get("submitted_to_d2d") is not True
            or evidence.get("classification") != "outline-empty" or evidence.get("failure") is not None
            or type(evidence.get("bounds_hresult")) is not int or evidence["bounds_hresult"] < 0
            or run.get("ink_bounds_world_dip") is not None or not isinstance(outline, dict)
            or outline.get("source") != "Actual same-run IDWriteFontFace.GetGlyphRunOutline into ID2D1PathGeometry"
            or outline.get("failure") is not None or outline.get("cleanup_failure") is not None
            or outline.get("color_font") is not False or not isinstance(run.get("face"), dict)
            or run["face"].get("source") != "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun"
            or run["face"].get("color_font") is not False
            or any(type(outline.get(key)) is not int or outline[key] < 0 for key in
                   ("create_path_hresult", "open_hresult", "outline_hresult", "close_hresult", "segment_count_hresult", "figure_count_hresult"))
            or any(type(outline.get(key)) is not int or outline[key] != 0 for key in ("figure_count", "segment_count"))): return False
    raw = evidence.get("raw_bounds")
    if not isinstance(raw, dict): return False
    coordinates = []
    for key in ("left", "top", "right", "bottom"):
        value = raw.get(key)
        if not isinstance(value, dict) or value.get("ieee754_format") != "binary32": return False
        bits = value.get("ieee754_bits")
        if not isinstance(bits, str) or len(bits) != 8: return False
        try:
            data = bytes.fromhex(bits)
            coordinate = struct.unpack("!f", data)[0]
            if math.isfinite(coordinate):
                if not number(value.get("value")) or struct.pack("!f", value["value"]) != data: return False
            elif (value.get("value") is not None or value.get("raw_value") !=
                  ("NaN" if math.isnan(coordinate) else "Infinity" if coordinate > 0 else "-Infinity")): return False
        except (ValueError, OverflowError, struct.error): return False
        coordinates.append(coordinate)
    expected = ("nonfinite" if any(not math.isfinite(v) for v in coordinates) else
                "finite-ordered" if coordinates[0] <= coordinates[2] and coordinates[1] <= coordinates[3] else "reversed")
    if expected == "finite-ordered" or evidence.get("raw_bounds_classification") != expected: return False
    binding = outline.get("binding")
    if not isinstance(binding, dict): return False
    for key in ("callback_run_pointer", "font_face_process_pointer"):
        pointer = run.get(key)
        if not isinstance(pointer, str): return False
        try:
            if int(pointer, 16) <= 0: return False
        except ValueError: return False
        owner = outline if key == "callback_run_pointer" else binding
        if owner.get(key) != pointer: return False
    return (type(run.get("ordinal")) is int and type(outline.get("glyph_run_ordinal")) is int and outline["glyph_run_ordinal"] == run["ordinal"]
            and isinstance(run.get("glyph_indices"), list) and type(binding.get("glyph_count")) is int
            and binding["glyph_count"] == len(run["glyph_indices"])
            and all(type(glyph) is int and 0 <= glyph <= 65535 for glyph in run["glyph_indices"])
            and number(run.get("em_size")) and run["em_size"] > 0 and type(run.get("sideways")) is bool
            and all(binding.get(key) == run.get(key) for key in ("em_size", "glyph_indices", "glyph_advances", "glyph_offsets", "sideways", "bidi_level"))
            and type(run.get("bidi_level")) is int and type(binding.get("right_to_left")) is bool
            and binding["right_to_left"] == bool(run["bidi_level"] & 1))


def native_label_geometry(node, surface_node=None):
    """Return (named geometry quantities, explicit measurement issues).

    surface_node must be the real Image carrying actual owner/COM binding
    evidence. Its measured transform and size map the real SIS pixels to the
    window; label dimensions are never substituted for the Image placement.
    """
    issues = []
    output = {"source": "Actual NativeLabel layout, production DWrite callbacks and bound XAML Image placement",
              "coordinate_space": "content-window", "element_layout": None, "element_clipped_layout": None,
              "advance_selection": [], "font_metric_advance": [], "glyph_ink": [],
              "ellipsis_layout": [], "ellipsis_ink": [], "layout_state": None,
              "final_pixel_contribution": None}

    def gap(property_name, reason, **extra):
        issues.append({"id": node.get("id"), "property": "geometry.native_label." + property_name, "reason": reason, **extra})

    for source, target in (("bounds", "element_layout"), ("visible_bounds", "element_clipped_layout")):
        if rect(node.get(source)):
            output[target] = {"bounds": copy.deepcopy(node[source]),
                              "quantity": "XAML element layout rectangle" if source == "bounds" else "XAML layout rectangle after measured clips; not glyph ink"}
    receipt = node.get("native_label_evidence")
    if not isinstance(receipt, dict):
        gap("draw", "No production draw receipt; measured XAML element boxes are retained")
        return output, issues
    draw, state = receipt.get("draw"), receipt.get("current_submission")
    versions = (("layout_revision", "current_layout_revision"), ("surface_revision", "current_surface_revision"), ("draw_ordinal", "current_draw_ordinal"))
    current = (isinstance(draw, dict) and isinstance(state, dict)
               and receipt.get("source") == "NativeLabel production SurfaceImageSource / DirectWrite renderer"
               and state.get("is_loaded") is True and state.get("queued") is False and state.get("rendering") is False
               and state.get("surface_binding_same_com_identity") is True and receipt.get("last_failure") is None
               and draw.get("surface_end_draw_succeeded") is True
               and all(type(draw.get(k)) is int and draw[k] >= 0 for k in ("draw_hresult", "surface_end_draw_hresult"))
               and all(type(draw.get(a)) is int and draw[a] > 0 and type(receipt.get(b)) is int and draw[a] == receipt[b] for a, b in versions))
    if not current:
        gap("draw", "Production draw is stale, pending, failed or not bound; measured XAML element boxes are retained")
        return output, issues
    lines = draw.get("line_metrics")
    single = (isinstance(lines, list) and len(lines) == 1 and isinstance(lines[0], dict)
              and type(lines[0].get("is_trimmed")) is bool)
    fmt, trim = draw.get("actual_text_format"), draw.get("trimming")
    output["layout_state"] = {"line_metrics": copy.deepcopy(lines), "trimming": copy.deepcopy(trim),
                              "word_wrapping": fmt.get("word_wrapping") if isinstance(fmt, dict) else None,
                              "is_trimmed": lines[0]["is_trimmed"] if single else None}

    image = surface_node if isinstance(surface_node, dict) else {}
    binding = image.get("native_label_surface_evidence")
    size, offset, image_size = draw.get("surface_pixels"), draw.get("surface_begin_draw_offset_pixels"), draw.get("image_actual_dip")
    image_matrix = matrix(image.get("transform"), "offset_x", "offset_y")
    placed = (image.get("type") == "Image" and image.get("parent") == node.get("id")
              and isinstance(binding, dict) and binding.get("owner_id") == node.get("id")
              and binding.get("source") == "actual NativeLabel production Image object identity and SurfaceImageSource COM binding"
              and binding.get("same_image_object") is True and binding.get("surface_binding_same_com_identity") is True
              and binding.get("source_type") == "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource"
              and all(binding.get(a) == draw[a] for a, _ in versions)
              and isinstance(size, dict) and all(type(size.get(k)) is int and size[k] > 0 for k in ("width", "height"))
              and isinstance(offset, dict) and all(number(offset.get(k)) for k in ("x", "y"))
              and isinstance(image_size, dict) and image_size.get("stretch") == "Fill"
              and rect(image.get("local_bounds")) and image["local_bounds"]["x"] == image["local_bounds"]["y"] == 0
              and all(number(image_size.get(k)) and image_size[k] > 0 and image_size[k] == image["local_bounds"][k] for k in ("width", "height"))
              and inverse(image_matrix) is not None)
    if not placed: gap("image_placement", "Actual Image ownership, pixel dimensions, Fill placement or invertible transform is missing")

    def mapping(context):
        if not placed or not isinstance(context, dict): return None
        world = matrix(context.get("world_transform"))
        dpi = context.get("dpi")
        if (context.get("source") != "Actual ID2D1DeviceContext getters at the production draw callback"
                or context.get("unit_mode") != 0 or not isinstance(dpi, dict)
                or not all(number(dpi.get(k)) and dpi[k] > 0 for k in ("x", "y")) or inverse(world) is None): return None

        def to_window(p):
            pixels = [p[0] * dpi["x"] / 96 - offset["x"], p[1] * dpi["y"] / 96 - offset["y"]]
            return point(image_matrix, [pixels[0] * image_size["width"] / size["width"], pixels[1] * image_size["height"] / size["height"]])

        def bounds(r, is_world=False):
            points = polygon(r) if is_world else [point(world, p) for p in polygon(r)]
            window_points = [to_window(p) for p in points]
            window_bounds = envelope(window_points)
            if window_bounds is None:
                gap("finite_transform", "Actual measured transform produced non-finite window coordinates")
                return None
            result = {"bounds": window_bounds, "window_polygon": window_points,
                      "inverse_world_transform": inverse(world), "actual_context": copy.deepcopy(context),
                      "visible_bounds": None, "visible_bounds_quantity": "Unmeasured until actual axis-aligned clip bounds are available"}
            if image.get("axis_aligned_transform") is True and rect(image.get("ancestor_clip")):
                result["visible_bounds"] = intersect(result["bounds"], image["ancestor_clip"])
                result["visible_bounds_quantity"] = "Measured rectangle envelope intersected with actual XAML clip; not raster coverage or occlusion proof"
            return result
        return bounds

    runs = draw.get("glyph_runs") if isinstance(draw.get("glyph_runs"), list) else []
    contexts = [r.get("actual_d2d_context") for r in runs if isinstance(r, dict)]
    common_context = contexts[0] if contexts and all(c == contexts[0] for c in contexts) else None
    common_map = mapping(common_context)
    hits = draw.get("hit_test_range_metrics")
    if not isinstance(hits, list): gap("selection", "Actual HitTestTextRange records are missing")
    for index, hit in enumerate(hits if isinstance(hits, list) else []):
        if not isinstance(hit, dict): continue
        local = {"x": hit.get("left"), "y": hit.get("top"), "width": hit.get("width"), "height": hit.get("height")}
        record = {"index": index, "quantity": "DWrite HitTestTextRange advance/selection region, including zero-height inline layout regions",
                  "source_metrics": copy.deepcopy(hit), "local_bounds": local if rect(local) else None,
                  "window": common_map(local) if common_map and rect(local) else None}
        output["advance_selection"].append(record)
    if output["advance_selection"] and common_map is None: gap("selection_transform", "Selection regions are retained locally; actual common draw context/Image mapping is incomplete")

    for run in runs:
        if not isinstance(run, dict): continue
        ordinal = run.get("ordinal")
        mapped = mapping(run.get("actual_d2d_context"))
        ink = run.get("ink_bounds_world_dip")
        empty_outline = empty_native_glyph_outline(run)
        ink_rect = ({"x": ink.get("left"), "y": ink.get("top"), "width": ink["right"] - ink["left"], "height": ink["bottom"] - ink["top"]}
                    if isinstance(ink, dict) and all(number(ink.get(k)) for k in ("left", "top", "right", "bottom")) else None)
        output["glyph_ink"].append({"glyph_run_ordinal": ordinal, "inline_draw_ordinal": run.get("inline_draw_ordinal"),
                                    "submitted_to_d2d": run.get("submitted_to_d2d"),
                                    "quantity": ("Actual same-run empty base outline; no rectangle is invented and advance is unchanged" if empty_outline else
                                                 "Actual D2D GetGlyphRunWorldBounds ink envelope; not selected text or exact raster coverage"),
                                    "outline_empty": empty_outline, "bounds_evidence": copy.deepcopy(run.get("ink_bounds_evidence")),
                                    "world_bounds": ink_rect, "window": mapped(ink_rect, True) if mapped and rect(ink_rect) else None})
        if not mapped: gap("run_transform", "Actual finite invertible D2D context and Image placement are required for window ink/advance geometry", glyph_run_ordinal=ordinal)
        if not rect(ink_rect) and not empty_outline: gap("glyph_ink", "Actual glyph ink bounds are unavailable", glyph_run_ordinal=ordinal)
        face, description = run.get("face"), run.get("description")
        metrics = face.get("metrics_design_units") if isinstance(face, dict) else None
        glyphs, advances = run.get("glyph_indices"), run.get("glyph_advances")
        valid = (single and run.get("submitted_to_d2d") is True and run.get("sideways") is False
                 and run.get("source") == "IDWriteTextLayout.Draw -> IDWriteTextRenderer.DrawGlyphRun -> ID2D1RenderTarget.DrawGlyphRun"
                 and type(run.get("from_inline_object")) is bool
                 and number(run.get("baseline_x")) and number(run.get("baseline_y")) and number(run.get("em_size")) and run["em_size"] > 0
                 and type(run.get("bidi_level")) is int and run["bidi_level"] >= 0
                 and isinstance(metrics, dict) and number(metrics.get("units_per_em")) and metrics["units_per_em"] > 0
                 and face.get("source") == "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun"
                 and all(number(metrics.get(k)) and metrics[k] >= 0 for k in ("ascent", "descent"))
                 and isinstance(glyphs, list) and bool(glyphs) and all(type(g) is int and 0 <= g <= 65535 for g in glyphs)
                 and isinstance(advances, list) and len(advances) == len(glyphs) and all(number(a) for a in advances)
                 and isinstance(description, dict) and isinstance(description.get("text"), str)
                 and type(description.get("text_position_utf16")) is int and description["text_position_utf16"] >= 0
                 and type(description.get("text_length_utf16")) is int
                 and len(description["text"].encode("utf-16-le", "surrogatepass")) == 2 * description["text_length_utf16"]
                 and isinstance(description.get("cluster_map"), list) and len(description["cluster_map"]) == description["text_length_utf16"]
                 and all(type(c) is int and 0 <= c < len(glyphs) for c in description["cluster_map"]))
        if valid and run.get("from_inline_object") is False:
            full = receipt.get("text")
            start, length = description["text_position_utf16"], description["text_length_utf16"]
            source = full.encode("utf-16-le", "surrogatepass") if isinstance(full, str) else b""
            valid = ((start + length) * 2 <= len(source)
                     and source[start * 2:(start + length) * 2] == description["text"].encode("utf-16-le", "surrogatepass"))
        if not valid:
            gap("font_metric_advance", "Single-line actual baseline, font-face metrics, advances or source/cluster association is incomplete", glyph_run_ordinal=ordinal)
            continue
        ratio = run["em_size"] / metrics["units_per_em"]
        x, baseline = run["baseline_x"], run["baseline_y"]
        end = x + (-1 if run["bidi_level"] % 2 else 1) * sum(advances)
        local = {"x": min(x, end), "y": baseline - metrics["ascent"] * ratio,
                 "width": abs(end - x), "height": (metrics["ascent"] + metrics["descent"]) * ratio}
        output["font_metric_advance"].append({"glyph_run_ordinal": ordinal, "inline_draw_ordinal": run.get("inline_draw_ordinal"),
            "quantity": "Actual rendered face ascent/descent around actual baseline, and actual glyph advance width; excludes line leading and glyph ink",
            "text_scope": "inline-object-local" if run.get("from_inline_object") else "layout-source",
            "description": copy.deepcopy(description), "local_bounds": local, "window": mapped(local) if mapped else None,
            "face_metrics_design_units": copy.deepcopy(metrics), "em_size": run["em_size"], "glyph_advances": copy.deepcopy(advances)})

    inlines = draw.get("inline_object_draws")
    for inline in inlines if isinstance(inlines, list) else []:
        if not isinstance(inline, dict) or inline.get("is_configured_trimming_sign") is not True: continue
        ordinal, metrics = inline.get("ordinal"), inline.get("inline_metrics")
        local = ({"x": inline.get("origin_x"), "y": inline.get("origin_y"), "width": metrics.get("width"), "height": metrics.get("height")}
                 if isinstance(metrics, dict) else None)
        mapped = mapping(inline.get("actual_d2d_context"))
        output["ellipsis_layout"].append({"inline_draw_ordinal": ordinal,
            "quantity": "Actual DrawInlineObject top-left origin plus inline layout metrics; zero height is retained, not interpreted as hidden",
            "local_bounds": local if rect(local) else None, "window": mapped(local) if mapped and rect(local) else None,
            "inline_com_identity": inline.get("inline_com_identity"), "draw_succeeded": inline.get("draw_succeeded")})
        selected = [r for r in output["glyph_ink"] if r["inline_draw_ordinal"] == ordinal]
        measured = [r["window"]["bounds"] for r in selected if r["window"] is not None and rect(r["window"].get("bounds"))]
        output["ellipsis_ink"].append({"inline_draw_ordinal": ordinal,
            "quantity": "Envelope of actual glyph ink bounds belonging to this exact omission Draw callback; not inline layout height",
            "glyph_run_ordinals": [r["glyph_run_ordinal"] for r in selected],
            "known_glyph_bounds": measured, "complete": bool(selected) and len(measured) == len(selected) and inline.get("draw_succeeded") is True,
            "bounds": envelope([p for r in measured for p in polygon(r)]) if measured and len(measured) == len(selected) else None})
        if not mapped or not rect(local): gap("ellipsis_layout", "Actual omission layout metrics or context mapping is incomplete", inline_draw_ordinal=ordinal)
        if not selected or len(measured) != len(selected): gap("ellipsis_ink", "Not every actual omission glyph callback has measured window ink bounds", inline_draw_ordinal=ordinal)
    return output, issues
