"""Fonts submitted by the current, source-bound NativeLabel production draw.

This measures the complete actual submitted renderer glyph/font set. It does
not certify final PNG attribution, glyph visibility, geometry, or whole-capture
coverage. The caller must keep those independent measurement failures intact.
No requested font list, cmap lookup, UIA font property, or new shaping is used.
"""
from copy import deepcopy
import math


LABEL_SOURCE = "NativeLabel production SurfaceImageSource / DirectWrite renderer"
STATE_SOURCE = "Actual NativeLabel state at receipt capture"
IMAGE_SOURCE = "actual NativeLabel production Image object identity and SurfaceImageSource COM binding"
BINDING_SOURCE = "Actual NativeLabel object ReferenceEquals against the capture observer label array"
FRAME_SOURCE = "Actual NativeLabel object references observed around desktop readback"
READBACK_SOURCE = "Actual SurfaceImageSource BeginDraw target copied after production glyph drawing and before SurfaceImageSource.EndDraw"
RUN_SOURCE = "IDWriteTextLayout.Draw -> IDWriteTextRenderer.DrawGlyphRun -> ID2D1RenderTarget.DrawGlyphRun"
FACE_SOURCE = "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun"
TRIMMING_SOURCE = "GetTrimming on the same IDWriteTextLayout used for the production Draw"
INLINE_SOURCE = "Actual IDWriteTextRenderer.DrawInlineObject callback and IDWriteInlineObject.Draw forwarding"
VERSIONS = ("layout_revision", "surface_revision", "draw_ordinal")
CHECKPOINTS = ("after_render_and_commit_requests", "before_desktop_readback",
               "after_desktop_readback", "before_element_extraction")


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _same_versions(source, draw, prefix=""):
    return (isinstance(source, dict)
            and all(_integer(source.get(prefix + key), 1) and source[prefix + key] == draw[key] for key in VERSIONS))


def _one(rows, index):
    if not isinstance(rows, list):
        return None
    found = [row for row in rows if isinstance(row, dict)
             and type(row.get("capture_label_index")) is int and row["capture_label_index"] == index]
    return found[0] if len(found) == 1 else None


def _utf16(text):
    # JSON and .NET can preserve lone UTF-16 surrogates too. Never silently
    # change the source or use Python's Unicode code-point offsets as UTF-16.
    return text.encode("utf-16-le", errors="surrogatepass")


def _names(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(row, dict) and isinstance(row.get("locale"), str) and bool(row["locale"])
                    and isinstance(row.get("value"), str) and bool(row["value"]) for row in value))


def _actual_name(rows, *, postscript=False):
    """Select a recorded en-us entry, never a name alias or requested family."""
    audit = {"policy": "Unique actual en-us entry; no synthesized aliases",
             "recorded_names": deepcopy(rows), "selected_locale": None, "selected_value": None}
    if not _names(rows):
        audit["reason"] = "Actual localized name entries are unavailable or malformed"
        return None, audit
    english = {row["value"] for row in rows if row["locale"].casefold() == "en-us"}
    if len(english) == 1:
        audit["selected_locale"] = "en-us"
        audit["selected_value"] = next(iter(english))
    elif not postscript and not english and len({row["value"] for row in rows}) == 1:
        # Identical observed family strings are unambiguous without English.
        # PostScript selection deliberately stays null without an en-us entry.
        audit["selected_value"] = rows[0]["value"]
        audit["policy"] = "Every recorded actual family-name entry is identical"
        audit["selected_locale"] = "all-recorded-locales-agree"
    else:
        audit["reason"] = "No unique actual en-us entry" if postscript else "Actual family-name entries are ambiguous"
    return audit["selected_value"], audit


def native_label_fonts(node, surface_node=None, frame=None):
    """Return (actual-font measurement, explicit issues), without mutations.

    The caller supplies the unique actual Image whose recorded owner_id is this
    NativeLabel; absent/ambiguous ownership must be passed as None. ``frame`` is
    the actual capture's NativeLabel frame receipt, not a reference scene. The
    XAML receipt contains four checkpoints through the start of extraction; a
    final sidecar can additionally contain after_element_extraction. Every
    supplied checkpoint is checked, and all four pre-export stages are required.

    On success ``fonts`` can populate style.rendered_fonts. Rows retain actual
    run/face identity, rather than collapsing different faces sharing a family.
    ``source_span_complete`` remains original source coverage. A verified trimmed
    submission can measure all its submitted fonts while that flag remains false.
    """
    output = {"source": "Actual NativeLabel production renderer fontFace measurement for the complete current submitted glyph-run set",
              "status": "unmeasured", "fonts": None, "source_span_complete": None,
              "original_source_span_complete": None, "submitted_glyph_runs_complete": False,
              "source_utf16_length": None, "runs": [], "binding": None,
              "final_png_attribution_proven": False,
              "does_not_measure": "Final PNG contribution, visible glyph subset, text geometry and whole-capture coverage"}
    issues = []

    def gap(reason, **extra):
        issues.append({"id": node.get("id") if isinstance(node, dict) else None,
                       "property": "style.rendered_fonts", "reason": reason, **extra})
        output["reason"] = reason
        return output, issues

    if not isinstance(node, dict) or node.get("type") != "NativeLabel" or not isinstance(node.get("text"), str) or not node["text"]:
        return gap("No nonempty actual NativeLabel source element")
    receipt = node.get("native_label_evidence")
    if not isinstance(receipt, dict) or receipt.get("source") != LABEL_SOURCE or receipt.get("text") != node["text"]:
        return gap("The production receipt is not bound to this exact source text")
    source = _utf16(node["text"]); source_length = len(source) // 2
    output["source_utf16_length"] = source_length
    state, draw = receipt.get("current_submission"), receipt.get("draw")
    if (not isinstance(draw, dict) or not all(_integer(draw.get(key), 1) for key in VERSIONS)
            or not _same_versions(receipt, draw, "current_")
            or not isinstance(draw.get("layout_com_identity"), str) or not draw["layout_com_identity"]
            or not isinstance(state, dict) or state.get("source") != STATE_SOURCE
            or state.get("is_loaded") is not True or state.get("queued") is not False or state.get("rendering") is not False
            or state.get("surface_binding_same_com_identity") is not True
            or "last_failure" not in receipt or receipt["last_failure"] is not None
            or draw.get("surface_end_draw_succeeded") is not True
            or not all(_integer(draw.get(key)) for key in ("draw_hresult", "surface_end_draw_hresult"))):
        return gap("Actual production draw is missing, stale, pending, failed or not currently bound")
    image = surface_node.get("native_label_surface_evidence") if isinstance(surface_node, dict) else None
    if (not isinstance(image, dict) or surface_node.get("type") != "Image" or image.get("source") != IMAGE_SOURCE
            or image.get("owner_id") != node.get("id") or not isinstance(node.get("id"), str) or not node["id"]
            or image.get("same_image_object") is not True or image.get("surface_binding_same_com_identity") is not True
            or image.get("source_type") != "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource" or not _same_versions(image, draw)):
        return gap("A unique actual Image/SIS object with matching owner and draw revisions is unavailable")
    binding = receipt.get("capture_binding")
    if (not isinstance(binding, dict) or binding.get("source") != BINDING_SOURCE or binding.get("same_object_reference") is not True
            or not _integer(binding.get("capture_label_index")) or not isinstance(binding.get("case_id"), str) or not binding["case_id"]
            or not isinstance(frame, dict) or frame.get("source") != FRAME_SOURCE or frame.get("case_id") != binding["case_id"]
            or frame.get("failure") is not None or frame.get("surface_readback_errors") != []):
        return gap("The actual capture frame/object-reference binding is incomplete or failed")
    index = binding["capture_label_index"]
    baseline, production, readback = (_one(frame.get(key), index) for key in ("baseline", "production_draws", "surface_readbacks"))
    baseline_state = baseline.get("state") if isinstance(baseline, dict) else None
    production_receipt = production.get("production_receipt") if isinstance(production, dict) else None
    production_state = production_receipt.get("current_submission") if isinstance(production_receipt, dict) else None
    if (not isinstance(baseline_state, dict) or baseline_state.get("text") != node["text"]
            or not _same_versions(baseline_state, draw) or baseline_state.get("surface_binding_same_com_identity") is not True
            or baseline_state.get("queued") is not False or baseline_state.get("rendering") is not False
            or not isinstance(production_receipt, dict) or production_receipt.get("source") != LABEL_SOURCE
            or production_receipt.get("text") != node["text"] or production_receipt.get("draw") != draw
            or not _same_versions(production_receipt, draw, "current_")
            or "last_failure" not in production_receipt or production_receipt["last_failure"] is not None
            or not isinstance(production_state, dict) or production_state.get("source") != STATE_SOURCE
            or production_state.get("is_loaded") is not True or production_state.get("queued") is not False
            or production_state.get("rendering") is not False or production_state.get("surface_binding_same_com_identity") is not True):
        return gap("Actual frame baseline and production draw do not uniquely describe this current label")
    local_readback = receipt.get("surface_readback")
    for evidence in (local_readback, readback):
        if (not isinstance(evidence, dict) or evidence.get("source") != READBACK_SOURCE
                or evidence.get("status") != "surface-pixels-read" or not _same_versions(evidence, draw)
                or evidence.get("case_id") != binding["case_id"] or type(evidence.get("capture_label_index")) is not int
                or evidence["capture_label_index"] != index or evidence.get("is_current_draw_at_export") is not True
                or evidence.get("surface_submission_succeeded") is not True
                or not _integer(evidence.get("surface_end_draw_hresult"))
                or evidence["surface_end_draw_hresult"] != draw["surface_end_draw_hresult"]):
            return gap("Current successful readback is not bound to this same submitted draw and case")
    if any(key not in readback or readback[key] != value for key, value in local_readback.items()):
        return gap("Element and frame readback records disagree")
    checkpoints = frame.get("checkpoints")
    if not isinstance(checkpoints, list):
        return gap("Actual frame continuity checkpoints are missing")
    positions = []
    for required in CHECKPOINTS:
        found = [i for i, row in enumerate(checkpoints) if isinstance(row, dict) and row.get("stage") == required]
        if len(found) != 1:
            return gap("A required actual frame checkpoint is missing or ambiguous", stage=required)
        positions.append(found[0])
    if positions != sorted(positions):
        return gap("Actual frame checkpoints are not in capture order")
    for row in checkpoints:
        current = _one(row.get("state"), index) if isinstance(row, dict) else None
        observed = current.get("state") if isinstance(current, dict) else None
        if (not isinstance(row, dict) or row.get("same_object_references") is not True or row.get("same_observed_state") is not True
                or not isinstance(row.get("stage"), str) or not row["stage"]
                or row.get("failure") is not None or not isinstance(observed, dict) or observed != baseline_state
                or not _same_versions(observed, draw) or observed.get("surface_binding_same_com_identity") is not True
                or observed.get("queued") is not False or observed.get("rendering") is not False):
            return gap("Actual label object, source, submitted draw or observed state changed across the frame")
    output["binding"] = {"capture": deepcopy(binding), "image": deepcopy(image), "layout_com_identity": draw["layout_com_identity"],
                         "revisions": {key: draw[key] for key in VERSIONS}, "checkpoint_stages": [row["stage"] for row in checkpoints],
                         "current_readback": deepcopy(local_readback), "presentation_identity_proven": frame.get("presentation_identity_proven")}

    submitted, problem = _submitted_font_set(node["text"], draw)
    output.update(submitted)
    if problem is not None:
        return gap(problem.pop("reason"), **problem)
    output["status"] = "measured-current-submission"
    return output, issues


def _submitted_font_set(source_text, draw):
    """Parse one recorded production draw; this alone proves no frame binding.

    The public reader calls this only after its unchanged live source, Image/SIS,
    frame checkpoints and readback checks. A trimmed sign has its own source;
    its offset zero must never fill the original text's omitted suffix.
    """
    source = _utf16(source_text); source_length = len(source) // 2
    runs, lines = draw.get("glyph_runs"), draw.get("line_metrics")
    output = {"fonts": None, "runs": deepcopy(runs) if isinstance(runs, list) else [],
              "source_span_complete": False, "original_source_span_complete": False,
              "submitted_glyph_runs_complete": False}
    def gap(reason, **extra):
        return output, {"reason": reason, **extra}
    if (not isinstance(lines, list) or not lines or any(not isinstance(line, dict)
            or type(line.get("is_trimmed")) is not bool or not _integer(line.get("length_utf16")) for line in lines)):
        return gap("Actual layout's original source-span evidence is unavailable")
    if sum(line["length_utf16"] for line in lines) != source_length:
        return gap("Actual line source lengths do not cover the complete source text")
    if not isinstance(runs, list) or not runs:
        return gap("No actual production glyph-run callbacks are recorded")
    trimmed = any(line["is_trimmed"] for line in lines)
    sign_run = None
    if trimmed:
        trimming, inline = draw.get("trimming"), draw.get("inline_object_draws")
        if (len(lines) != 1 or not isinstance(trimming, dict) or trimming.get("source") != TRIMMING_SOURCE
                or trimming.get("requested_character_ellipsis") is not True
                or type(trimming.get("granularity")) is not int or trimming["granularity"] != 1
                or type(trimming.get("delimiter")) is not int or trimming["delimiter"] != 0
                or type(trimming.get("delimiter_count")) is not int or trimming["delimiter_count"] != 0
                or trimming.get("same_sign_com_identity") is not True
                or not isinstance(trimming.get("configured_sign_com_identity"), str)
                or not trimming["configured_sign_com_identity"]
                or trimming.get("layout_sign_com_identity") != trimming["configured_sign_com_identity"]
                or not isinstance(inline, list) or len(inline) != 1 or not isinstance(inline[0], dict)):
            return gap("Trimmed submission lacks one current character-ellipsis sign and actual inline draw")
        sign = inline[0]
        sign_run = sign.get("first_glyph_run_ordinal")
        if (sign.get("source") != INLINE_SOURCE or type(sign.get("ordinal")) is not int or sign["ordinal"] != 0
                or "parent_inline_draw_ordinal" not in sign or sign["parent_inline_draw_ordinal"] is not None
                or sign.get("inline_com_identity") != trimming["layout_sign_com_identity"]
                or sign.get("is_configured_trimming_sign") is not True
                or sign.get("sideways") is not False or sign.get("right_to_left") is not False
                or sign.get("draw_succeeded") is not True or not _integer(sign.get("draw_hresult"))
                or sign.get("metadata_failure") is not None or sign.get("draw_failure") is not None
                or not _integer(sign_run) or sign_run != len(runs) - 1
                or type(sign.get("glyph_run_count")) is not int or sign["glyph_run_count"] != 1):
            return gap("Actual ellipsis inline object identity or its complete nested glyph-run interval is unbound")
        output["trimming_submission"] = {"trimming": deepcopy(trimming), "inline_draw": deepcopy(sign),
            "scope": "Current single-line LTR source prefix and its actual final ellipsis glyph submission; not visible PNG coverage"}
    elif draw.get("inline_object_draws") != []:
        return gap("Inline-object callbacks cannot be attributed to the original complete source span")
    spans, fonts, run_audit = [], [], []
    for ordinal, run in enumerate(runs):
        is_sign = ordinal == sign_run
        if (not isinstance(run, dict) or run.get("source") != RUN_SOURCE or run.get("submitted_to_d2d") is not True
                or type(run.get("ordinal")) is not int or run["ordinal"] != ordinal
                or run.get("from_inline_object") is not is_sign
                or (not is_sign and run.get("inline_draw_ordinal") is not None)
                or (is_sign and (type(run.get("inline_draw_ordinal")) is not int or run["inline_draw_ordinal"] != 0))
                or (trimmed and (run.get("sideways") is not False
                                 or type(run.get("bidi_level")) is not int or run["bidi_level"] != 0))):
            return gap("A recorded run is not an ordered original-source production glyph submission", run_ordinal=ordinal)
        description, glyphs, face = run.get("description"), run.get("glyph_indices"), run.get("face")
        if (not isinstance(description, dict) or not isinstance(description.get("text"), str)
                or not _integer(description.get("text_position_utf16")) or not _integer(description.get("text_length_utf16"), 1)
                or not isinstance(glyphs, list) or not glyphs or any(type(glyph) is not int or not 0 <= glyph <= 65535 for glyph in glyphs)):
            return gap("Actual source description or submitted glyph-index array is incomplete", run_ordinal=ordinal)
        start, length = description["text_position_utf16"], description["text_length_utf16"]
        if is_sign:
            if start != 0 or length != 1 or description["text"] != "\u2026":
                return gap("Actual trimming-sign callback does not describe its own single ellipsis source", run_ordinal=ordinal)
        elif start + length > source_length or _utf16(description["text"]) != source[start * 2:(start + length) * 2]:
            return gap("Actual callback UTF-16 source range differs from the captured label source", run_ordinal=ordinal)
        clusters = description.get("cluster_map")
        if (not isinstance(clusters, list) or len(clusters) != length
                or any(type(cluster) is not int or not 0 <= cluster < len(glyphs) for cluster in clusters)
                or min(clusters) != 0):
            return gap("Actual UTF-16 cluster-to-glyph ranges are missing, invalid or do not cover the run", run_ordinal=ordinal)
        if not is_sign:
            if trimmed and start != (spans[-1][1] if spans else 0):
                return gap("Actual trimmed LTR source callbacks are not one ordered contiguous prefix", run_ordinal=ordinal)
            spans.append((start, start + length))
        if (not isinstance(face, dict) or face.get("source") != FACE_SOURCE or face.get("measurement_failure") is not None
                or not _integer(face.get("face_index")) or not _integer(face.get("simulations"))):
            return gap("Actual submitted fontFace metadata is unavailable; configured or UIA families are not substitutes", run_ordinal=ordinal)
        family, family_choice = _actual_name(face.get("family_names"))
        postscript, ps_choice = _actual_name(face.get("postscript_names"), postscript=True)
        if family is None:
            return gap("Actual submitted fontFace has no unambiguous measured family name", run_ordinal=ordinal)
        axes = face.get("axes")
        if axes is not None and (not isinstance(axes, list) or any(not isinstance(axis, dict) or not isinstance(axis.get("tag"), str)
                or len(axis["tag"]) != 4 or type(axis.get("value")) not in (int, float) or not math.isfinite(axis["value"]) for axis in axes)):
            return gap("Recorded actual fontFace variation-axis metadata is malformed", run_ordinal=ordinal)
        source_range = None if is_sign else {"start": start, "length": length}
        fonts.append({"family_name": family, "postscript_name": postscript, "glyph_count": len(glyphs), "source": FACE_SOURCE,
                      "run_ordinal": ordinal, "source_range_utf16": source_range,
                      "face_index": face["face_index"], "simulations": face["simulations"], "axes": deepcopy(axes)})
        run_audit.append({"run_ordinal": ordinal, "source_range_utf16": deepcopy(source_range),
                          "family_selection": family_choice, "postscript_selection": ps_choice, "actual_face": deepcopy(face)})
        if is_sign:
            for record in (fonts[-1], run_audit[-1]):
                record.update(inline_draw_ordinal=0, inline_source_range_utf16={"start": start, "length": length},
                              inline_source_text=description["text"])
    cursor = 0
    for start, end in sorted(spans):
        if start != cursor:
            output["source_span_complete"] = False
            return gap("Actual glyph callbacks overlap or leave a gap in the complete source span")
        cursor = end
    if not trimmed and cursor != source_length:
        return gap("Actual glyph callbacks cover only part of the original source span")
    if trimmed and cursor >= source_length:
        return gap("Actual trimmed submission does not leave an omitted original-source suffix")
    output.update(fonts=fonts, source_span_complete=not trimmed, original_source_span_complete=not trimmed,
                  submitted_glyph_runs_complete=True, run_font_evidence=run_audit,
                  submitted_original_source_range_utf16={"start": 0, "length": cursor},
                  unsubmitted_original_source_range_utf16={"start": cursor, "length": source_length - cursor})
    return output, None
