"""Keep configured font requests separate from actual render-face weights.

No face name, requested family, configured weight or trait-name interpolation
can establish an actual OpenType weight. Missing quantities remain failures.
"""
from copy import deepcopy
import base64
import binascii
import math

from native_label_fonts import BINDING_SOURCE, IMAGE_SOURCE, LABEL_SOURCE, _submitted_font_set
from windows_selector_labels import CONTRACT as SELECTOR_LABEL_CONTRACT, SOURCE as SELECTOR_LABEL_SOURCE

VERSION = 1
WGHT_CORETEXT_TAG = str(int.from_bytes(b"wght", "big"))
MAC_DRAW_SOURCE = "production NSLayoutManager.showCGGlyphs callback"
MAC_WEIGHT_SOURCE = "CTFont tables and variations of the actual showCGGlyphs font"
OS2_TABLE_TAG = int.from_bytes(b"OS/2", "big")
FVAR_TABLE_TAG = int.from_bytes(b"fvar", "big")
WINDOWS_FACE_SOURCE = "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun"
WINDOWS_FORMAT_SOURCE = "IDWriteTextFormat getters on the same production IDWriteTextLayout passed to Draw"
WINDOWS_XAML_SOURCE = "actual XAML text-owner FontWeight.Weight getter"
WINDOWS_XAML_BINDING_SOURCE = "actual XAML text_source selected by existing projection"
WINDOWS_SUBMITTED_SCOPE = "actual-current-submitted-glyph-font-set"


def weight(value):
    return type(value) in (int, float) and math.isfinite(value) and 1 <= value <= 1000


def applicable(element):
    icon = element.get("icon")
    return (bool(element.get("text")) or element.get("kind") == "text"
            or element.get("kind") == "icon" and isinstance(icon, dict)
            and icon.get("source") not in ("svg", "image", "path", "geometry", "vector-image-v1"))


def _record(value, source, raw, reason=None):
    result = {"value": value, "source": source, "raw": deepcopy(raw)}
    if reason:
        result["reason"] = reason
    return result


def _selector_configured_label(element, evidence, binding):
    """Bind a full TextBlock Run to the existing measured tab-content audit.

    selector_content_labels already checked the receipt against the raw tree.
    Recheck its retained owner/content/text identities here before accepting the
    Run getter. A projection reason or measured flag alone is not that binding.
    This does not establish a resolved face, paint or final-PNG contribution.
    """
    audit = evidence.get("selector_content_label")
    run = binding.get("text_run_source")
    if (element.get("kind") != "tab" or evidence.get("type") != "SelectorBarItem"
            or not isinstance(element.get("id"), str) or not element["id"]
            or binding.get("source_type") != "Run" or not isinstance(run, dict)
            or not isinstance(audit, dict) or audit.get("status") != "measured"
            or not isinstance(audit.get("source_id"), str) or not audit["source_id"]
            or not isinstance(audit.get("text"), str) or not audit["text"]
            or evidence.get("label_source") != binding.get("source_id")
            or audit.get("source_id") != run.get("owner")
            or audit.get("text") != binding.get("text") or audit.get("text") != element.get("text")):
        return False
    proof = audit.get("evidence")
    if (not isinstance(proof, dict) or proof.get("contract") != SELECTOR_LABEL_CONTRACT
            or proof.get("source") != SELECTOR_LABEL_SOURCE or proof.get("status") != "measured"
            or proof.get("owner_id") != element.get("id")
            or proof.get("owner_runtime_type") != "Microsoft.UI.Xaml.Controls.SelectorBarItem"
            or proof.get("errors") != []
            or any(proof.get(key) is not True for key in
                   ("ui_thread_access", "template_present", "same_subtree_after", "same_tag_after",
                    "same_template_after", "same_presenter_content_after", "tag_in_actual_subtree",
                    "captured_subtree_complete"))):
        return False
    entries, sources = proof.get("actual_subtree"), proof.get("text_sources")
    if (not isinstance(entries, list) or not entries
            or any(not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]
                   or not isinstance(entry.get("runtime_type"), str) or not entry["runtime_type"]
                   or entry.get("captured_parent_matches") is not True
                   or type(entry.get("child_index")) is not int or entry["child_index"] < 0 for entry in entries)
            or not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict)):
        return False
    by_id = {entry["id"]: entry for entry in entries}
    owner_id, label_id = element["id"], audit["source_id"]
    if (len(by_id) != len(entries) or owner_id not in by_id or label_id not in by_id
            or by_id[owner_id].get("parent_id") is not None
            or by_id[owner_id]["runtime_type"] != proof["owner_runtime_type"]
            or by_id[label_id]["runtime_type"] != "Microsoft.UI.Xaml.Controls.TextBlock"):
        return False
    paths = {}
    for entry_id in by_id:
        path, current = [], entry_id
        while isinstance(current, str) and current in by_id and current not in path:
            path.append(current)
            current = by_id[current].get("parent_id")
        if current is not None or not path or path[-1] != owner_id:
            return False  # Detached, cyclic or incomplete current subtree.
        paths[entry_id] = path
    tag_id, presenters = proof.get("tag_content_id"), proof.get("presenter_ids")
    if (not isinstance(tag_id, str) or tag_id not in by_id or tag_id == label_id or tag_id == owner_id
            or not isinstance(presenters, list) or len(presenters) != 1
            or not isinstance(presenters[0], str) or presenters[0] not in by_id
            or by_id[presenters[0]]["runtime_type"] != "Microsoft.UI.Xaml.Controls.ContentPresenter"
            or presenters[0] == tag_id or presenters[0] not in paths[tag_id]
            or tag_id not in paths[label_id]):
        return False
    source = sources[0]
    observed_text_ids = {entry["id"] for entry in entries if entry["runtime_type"] in
                         {"Microsoft.UI.Xaml.Controls.TextBlock", "Microsoft.UI.Xaml.Controls.RichTextBlock", "Relic.NativeLabel"}}
    return (observed_text_ids == {label_id} and source.get("id") == label_id
            and source.get("runtime_type") == by_id[label_id]["runtime_type"]
            and source.get("captured_text_matches") is True and source.get("text") == audit["text"])


def _xaml_configured_weight(element, evidence, style):
    """Validate the same actual XAML text owner, never a containing control.

    Getters measure an effective property request (including inheritance).
    They cannot establish the font face or weight eventually used for a glyph.
    The receipt is additive: old captures without it remain unmeasured.
    """
    receipt = evidence.get("xaml_font_weight_configuration")
    if receipt is None:
        return None
    binding = evidence.get("xaml_font_weight_binding")
    raw = {"configuration": receipt, "binding": binding}
    def unknown(reason):
        return _record(None, WINDOWS_XAML_SOURCE, raw, reason)

    if (not isinstance(receipt, dict) or type(receipt.get("version")) is not int or receipt["version"] != 1
            or receipt.get("source") != WINDOWS_XAML_SOURCE or not isinstance(binding, dict)
            or binding.get("source") != WINDOWS_XAML_BINDING_SOURCE
            or binding.get("canonical_owner_id") != element.get("id")):
        return unknown("XAML configured weight has no versioned receipt bound to this projected element")
    typ = binding.get("source_type")
    runtime = {"TextBlock": "Microsoft.UI.Xaml.Controls.TextBlock",
               "RichTextBlock": "Microsoft.UI.Xaml.Controls.RichTextBlock",
               "Run": "Microsoft.UI.Xaml.Documents.Run"}.get(typ)
    source_id = binding.get("source_id")
    if (runtime is None or receipt.get("runtime_type") != runtime
            or receipt.get("property") != typ + ".FontWeight.Weight"
            or not isinstance(source_id, str) or not source_id or receipt.get("source_id") != source_id):
        return unknown("Configured getter does not belong to the actual supported XAML text owner")
    if source_id != element.get("id"):
        ownership = binding.get("ownership")
        if (not isinstance(ownership, dict) or ownership.get("source_id") != source_id
                or ownership.get("owner_id") != element.get("id")):
            return unknown("A containing element has no existing single-text-source ownership for this getter")
        if ownership.get("reason") == "actual current SelectorBarItem content label":
            if not _selector_configured_label(element, evidence, binding):
                return unknown("Tab Run getter is not bound to the actual current SelectorBarItem content label")
            raw["selector_content_label"] = evidence["selector_content_label"]
        elif ownership.get("reason") != "single simple control label":
            return unknown("A containing element has no existing single-text-source ownership for this getter")
    elif binding.get("ownership") is not None:
        return unknown("Direct text owner unexpectedly claims a different projection owner")
    text = binding.get("text")
    value = receipt.get("value")
    if (not isinstance(text, str) or not text or receipt.get("text") != text or element.get("text") != text
            or not weight(value) or not weight(receipt.get("raw_style_font_weight"))
            or not weight(binding.get("style_font_weight")) or not weight(style.get("font_weight"))
            or value != receipt["raw_style_font_weight"] or value != binding["style_font_weight"]
            or value != style["font_weight"]):
        return unknown("Configured weight/text differs between the actual getter, raw source and projected text")
    runs = binding.get("rich_text_runs")
    run_source = binding.get("text_run_source")
    if typ == "Run":
        if not isinstance(run_source, dict) or not isinstance(runs, list) or len(runs) != 1 or not isinstance(runs[0], dict):
            return unknown("Run configured weight has no unique retained actual leaf record")
        run = runs[0]
        owner, index = run_source.get("owner"), run_source.get("index")
        start, end = run_source.get("start_offset"), run_source.get("end_offset")
        own = run.get("own_paint_evidence")
        if (not isinstance(owner, str) or not owner or type(index) is not int or index < 0
                or type(start) is not int or type(end) is not int or start < 0 or end <= start
                or source_id != owner + ":run:" + str(index)
                or receipt.get("owner_id") != owner or receipt.get("run_index") != index
                or type(receipt.get("run_index")) is not int
                or any(type(receipt.get(key)) is not int or receipt[key] != run_source[key]
                       or type(run.get(key)) is not int or run[key] != run_source[key]
                       for key in ("start_offset", "end_offset"))
                or run.get("type") != "Run" or run.get("text") != text or not weight(run.get("font_weight"))
                or run["font_weight"] != value or run.get("font_weight_configuration") != receipt
                or not isinstance(own, dict) or own.get("source") != "actual TextElement runtime type and owner ContentStart/ContentEnd range"
                or own.get("runtime_type") != runtime or own.get("owner_id") != owner or own.get("exact_run_type") is not True
                or any(type(own.get(key)) is not int or own[key] != run_source[key] for key in ("start_offset", "end_offset"))):
            return unknown("Run configured weight does not match the actual leaf identity, text and source span")
    elif (receipt.get("owner_id") != source_id or run_source is not None or runs not in (None, [])
          or any(key in receipt for key in ("run_index", "start_offset", "end_offset"))):
        return unknown("Parent text-owner request cannot stand in for separately measured rich-text leaves")
    return _record(value, WINDOWS_XAML_SOURCE, raw)


def _mac_projection(element, evidence):
    fields = ("native_font_weight_configuration", "native_font_drawing")
    candidates = []
    direct = evidence.get("projection")
    if (isinstance(direct, dict) and any(field in direct for field in fields)
            and direct.get("text") == element.get("text")):
        candidates.append(("evidence.projection", direct))
    owned = evidence.get("owned_text_evidence")
    child = owned.get("projection") if isinstance(owned, dict) else None
    if (isinstance(child, dict) and any(field in child for field in fields)
            and isinstance(evidence.get("owned_text_id"), str) and owned.get("id") == evidence["owned_text_id"]
            and isinstance(evidence.get("identifier"), str) and evidence["identifier"]
            and owned.get("production_owner") == evidence["identifier"]
            and owned.get("text") == element.get("text") and child.get("text") == element.get("text")):
        candidates.append(("evidence.owned_text_evidence.projection", child))
    if len(candidates) != 1:
        return None, None, [path for path, _ in candidates]
    return candidates[0][0], candidates[0][1], [candidates[0][0]]


def _mac_face_weight(font):
    """Read only the face already bound to the actual drawing/source span.

    A static face's OS/2 class and a variable instance's wght coordinate are
    separate measured quantities. OS/2 cannot resolve an unknown instance.
    """
    axes = font.get("actual_variations")
    actual = axes.get(WGHT_CORETEXT_TAG) if isinstance(axes, dict) else None
    source = "CTFontCopyVariation of the actual showCGGlyphs font"
    if "weight_measurement" not in font:
        result = _record(actual, source, font,
                         None if weight(actual) else "The actual callback font has no measured wght axis")
        result["quantity"] = "actual-wght-coordinate" if weight(actual) else None
        return result

    receipt = font["weight_measurement"]
    def unknown(reason):
        return {**_record(None, MAC_WEIGHT_SOURCE, font, reason), "quantity": None}

    if (not isinstance(receipt, dict) or type(receipt.get("version")) is not int or receipt["version"] != 1
            or receipt.get("source") != MAC_WEIGHT_SOURCE or receipt.get("status") != "measured"
            or not isinstance(font.get("postscript_name"), str) or not font["postscript_name"]
            or receipt.get("postscript_name") != font["postscript_name"]):
        return unknown("Actual callback weight receipt has missing/changed source, version, status or PostScript identity")
    if receipt.get("quantity") == "actual-wght-coordinate":
        if (not weight(actual) or not isinstance(receipt.get("actual_variations"), dict)
                or not weight(receipt["actual_variations"].get(WGHT_CORETEXT_TAG))
                or receipt["actual_variations"] != axes
                or not weight(receipt.get("value")) or receipt["value"] != actual):
            return unknown("Variable weight receipt does not match the actual callback wght coordinate")
        return {**_record(actual, source, font), "quantity": "actual-wght-coordinate"}
    if receipt.get("quantity") != "static-face-os2-usWeightClass":
        return unknown("Actual callback weight receipt has no supported measured quantity")
    tags = receipt.get("available_table_tags")
    if (not isinstance(tags, list) or not tags
            or any(type(tag) is not int or not 0 <= tag <= 0xffffffff for tag in tags)
            or OS2_TABLE_TAG not in tags or FVAR_TABLE_TAG in tags):
        return unknown("Static-face weight requires the actual table inventory with OS/2 and without fvar")
    if ("variation_axes" not in receipt
            or receipt["variation_axes"] is not None and receipt["variation_axes"] != []
            or "actual_variations" not in receipt
            or receipt["actual_variations"] is not None and receipt["actual_variations"] != {}
            or "actual_variations" not in font or axes is not None and axes != {}):
        return unknown("Static-face weight cannot replace nonempty or unmeasured actual variation axes/coordinates")
    encoded = receipt.get("os2_base64")
    if not isinstance(encoded, str):
        return unknown("Actual complete OS/2 table bytes are missing")
    try:
        table = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return unknown("Actual OS/2 table is not valid base64")
    # OpenType OS/2 versions 0..5 share the big-endian uint16 at offset 4.
    # The callback contract requires at least 68 retained bytes. This only
    # extracts the weight field, not validation of the remaining font tables.
    if len(table) < 68:
        return unknown("Actual OS/2 table is truncated below the 68-byte common table extent")
    version, value = int.from_bytes(table[:2], "big"), int.from_bytes(table[4:6], "big")
    if version not in range(6) or not weight(value):
        return unknown("Actual OS/2 version or usWeightClass is outside the supported format/range")
    if not weight(receipt.get("value")) or receipt["value"] != value:
        return unknown("Recorded static-face value differs from the actual OS/2 bytes")
    return {**_record(value, MAC_WEIGHT_SOURCE, font), "quantity": "static-face-os2-usWeightClass",
            "parsed_os2": {"version": version, "byte_length": len(table), "usWeightClass": value,
                           "offset": 4, "byte_order": "big"}}


def _windows_faces(fonts):
    faces = []
    for font in fonts:
        axes = font.get("axes")
        matches = [axis.get("value") for axis in axes if isinstance(axis, dict) and axis.get("tag") == "wght"] if isinstance(axes, list) else []
        actual = matches[0] if len(matches) == 1 and font.get("source") == WINDOWS_FACE_SOURCE else None
        faces.append({"family_name": font.get("family_name"), "postscript_name": font.get("postscript_name"),
                      **_record(actual, "Actual DrawGlyphRun fontFace variation axis", font,
                                None if weight(actual) else "No unique measured wght axis on the actual submitted face")})
    return faces


def _windows_submitted_coverage(element, rendered, fonts):
    """Narrow additive coverage for an already-bound trimmed NativeLabel draw.

    Re-read its original callback records with the existing submitted-font reader;
    a completion flag, face-name set or cached resolved value cannot replace a run.
    Original-source coverage stays false. Frame/PNG visibility is not inferred.
    """
    evidence = element.get("evidence") if isinstance(element.get("evidence"), dict) else {}
    native = evidence.get("native_label_evidence")
    draw = native.get("draw") if isinstance(native, dict) else None
    binding = rendered.get("binding") if isinstance(rendered, dict) else None
    if (evidence.get("type") != "NativeLabel" or not isinstance(element.get("text"), str) or not element["text"]
            or not isinstance(native, dict) or native.get("source") != LABEL_SOURCE
            or native.get("text") != element["text"] or not isinstance(draw, dict)
            or not isinstance(rendered, dict) or rendered.get("status") != "measured-current-submission"
            or rendered.get("source_span_complete") is not False or rendered.get("original_source_span_complete") is not False
            or rendered.get("submitted_glyph_runs_complete") is not True
            or not isinstance(fonts, list) or not fonts or any(not isinstance(font, dict) for font in fonts)
            or rendered.get("fonts") != fonts or not isinstance(binding, dict)):
        return None
    image, capture = binding.get("image"), binding.get("capture")
    if (not isinstance(image, dict) or image.get("source") != IMAGE_SOURCE or image.get("owner_id") != element.get("id")
            or image.get("same_image_object") is not True or image.get("surface_binding_same_com_identity") is not True
            or not isinstance(capture, dict) or capture.get("source") != BINDING_SOURCE
            or capture.get("same_object_reference") is not True
            or capture != native.get("capture_binding")
            or not isinstance(draw.get("layout_com_identity"), str) or not draw["layout_com_identity"]
            or binding.get("layout_com_identity") != draw["layout_com_identity"]
            or binding.get("revisions") != {key: draw.get(key) for key in ("layout_revision", "surface_revision", "draw_ordinal")}):
        return None
    submitted, error = _submitted_font_set(element["text"], draw)
    fields = ("fonts", "runs", "source_span_complete", "original_source_span_complete", "submitted_glyph_runs_complete",
              "run_font_evidence", "trimming_submission", "submitted_original_source_range_utf16",
              "unsubmitted_original_source_range_utf16")
    if (error is not None or submitted.get("submitted_glyph_runs_complete") is not True
            or submitted.get("source_span_complete") is not False
            or any(key not in rendered or rendered[key] != submitted.get(key) for key in fields)
            or any(not weight(face["value"]) for face in _windows_faces(fonts))):
        return None
    return {"quantity": WINDOWS_SUBMITTED_SCOPE, "complete": True,
            "source_evidence_path": "evidence.native_label_fonts", "original_source_span_complete": False,
            "run_ordinals": [font["run_ordinal"] for font in fonts]}


def project_font_weights(element):
    """Project only measurements already bound to this actual source element.

    macOS owns its extractor; its existing actual attributed-input and completed
    draw receipts are consumed without rewriting its files or canonical values.
    """
    evidence = element.get("evidence") if isinstance(element.get("evidence"), dict) else {}
    if isinstance(evidence.get("font_weight_quantities"), dict):
        return deepcopy(evidence["font_weight_quantities"])
    style = element.get("style") if isinstance(element.get("style"), dict) else {}
    result = {"version": VERSION, "applicable": applicable(element), "owner": element.get("id"),
              "legacy": {"value": style.get("font_weight"), "quantity": "unclassified provider value"},
              "configured": _record(None, None, None, "No independently measured configured weight"),
              "resolved": {"source_span_complete": False, "faces": None,
                           "reason": "No actual render-face weight measurement"}}
    if not result["applicable"]:
        result["reason"] = "This element owns neither visible text nor a font glyph"
        return result

    xaml_configured = _xaml_configured_weight(element, evidence, style)
    if xaml_configured is not None:
        result["configured"] = xaml_configured
        if weight(xaml_configured.get("value")):
            result["legacy"]["quantity"] = "configured"

    request = evidence.get("font_request")
    if isinstance(request, dict) and request.get("source") == "getComputedStyle":
        result["legacy"]["quantity"] = "configured"
        result["configured"] = _record(request.get("weight"), "getComputedStyle", request)
        result["resolved"]["reason"] = "CSS.getPlatformFontsForNode records actual faces, not resolved weight or variation axes"

    projection_path, projection, candidate_paths = _mac_projection(element, evidence)
    result["native_font_projection_paths"] = candidate_paths
    if len(candidate_paths) > 1:
        result["configured"]["reason"] = "Multiple actual font-owning projections; parent and child measurements are not combined"
        result["resolved"]["reason"] = result["configured"]["reason"]
    if isinstance(projection, dict):
        result["source_evidence_path"] = projection_path
        result["legacy"]["quantity"] = "native descriptor-trait conversion; not an actual wght-axis measurement"
        configured = projection.get("native_font_weight_configuration")
        if isinstance(configured, dict) and configured.get("source") == "actual native attributed text style input":
            result["configured"] = _record(configured.get("value"), configured["source"], configured)
        drawing = projection.get("native_font_drawing")
        fonts = style.get("rendered_fonts")
        if (isinstance(drawing, dict) and drawing.get("provider") == MAC_DRAW_SOURCE
                and drawing.get("status") == "measured-current-draw"
                and isinstance(fonts, list) and fonts and all(isinstance(font, dict) for font in fonts)
                and drawing.get("fonts") == fonts):
            faces = []
            for font in fonts:
                faces.append({"family_name": font.get("family_name"), "postscript_name": font.get("postscript_name"),
                              **_mac_face_weight(font)})
            result["resolved"] = {"source_span_complete": True, "faces": faces,
                                  "source": MAC_DRAW_SOURCE,
                                  "source_evidence_path": projection_path + ".native_font_drawing"}

    submission = evidence.get("native_label_submission")
    native = evidence.get("native_label_evidence")
    draw = native.get("draw") if isinstance(native, dict) else None
    fmt = draw.get("actual_text_format") if isinstance(draw, dict) else None
    submitted_style = submission.get("style") if isinstance(submission, dict) else None
    if (isinstance(submitted_style, dict) and isinstance(fmt, dict) and fmt.get("source") == WINDOWS_FORMAT_SOURCE
            and weight(fmt.get("font_weight")) and submitted_style.get("font_weight") == fmt["font_weight"]
            and style.get("font_weight") == fmt["font_weight"]):
        # native_label_submission has already checked current draw versions,
        # the bound production source and the corresponding style receipt.
        result["configured"] = _record(fmt["font_weight"], WINDOWS_FORMAT_SOURCE, fmt)
        result["legacy"]["quantity"] = "configured"
    rendered = evidence.get("native_label_fonts")
    fonts = style.get("rendered_fonts")
    submitted_coverage = _windows_submitted_coverage(element, rendered, fonts)
    if (isinstance(rendered, dict) and rendered.get("status") == "measured-current-submission"
            and (rendered.get("source_span_complete") is True or submitted_coverage is not None)
            and isinstance(fonts, list) and fonts
            and all(isinstance(font, dict) for font in fonts)
            and rendered.get("fonts") == fonts):
        result["resolved"] = {"source_span_complete": rendered.get("source_span_complete") is True,
                              "faces": _windows_faces(fonts),
                              "source": WINDOWS_FACE_SOURCE, "source_evidence_path": "evidence.native_label_fonts"}
        if submitted_coverage is not None:
            result["resolved"]["coverage"] = submitted_coverage
    return result


def _identity(font):
    if not isinstance(font, dict):
        return None, None
    family, postscript = font.get("family_name"), font.get("postscript_name")
    return (family if isinstance(family, str) else None,
            postscript if isinstance(postscript, str) else None)


def font_weight_issues(element, measurement=None):
    if not applicable(element):
        return []
    measured = project_font_weights(element) if measurement is None else measurement
    issues = []
    if (not isinstance(measured, dict) or type(measured.get("version")) is not int or measured.get("version") != VERSION
            or measured.get("applicable") is not True or measured.get("owner") != element.get("id")):
        return [{"field": "font_weight.quantities", "reason": "Missing or unbound version-1 configured/resolved weight evidence"}]
    legacy = measured.get("legacy")
    style = element.get("style") if isinstance(element.get("style"), dict) else {}
    if not isinstance(legacy, dict) or legacy.get("value") != style.get("font_weight"):
        issues.append({"field": "font_weight.quantities", "reason": "Font-weight evidence does not preserve this element's original provider value"})
    configured = measured.get("configured")
    if (not isinstance(configured, dict) or not weight(configured.get("value"))
            or not isinstance(configured.get("source"), str) or not configured["source"] or not isinstance(configured.get("raw"), dict)):
        issues.append({"field": "font_weight.configured", "reason": "Configured weight has no actual numeric request measurement"})
    resolved = measured.get("resolved")
    faces = resolved.get("faces") if isinstance(resolved, dict) else None
    fonts = style.get("rendered_fonts")
    covered = isinstance(resolved, dict) and resolved.get("source_span_complete") is True
    if isinstance(resolved, dict) and "coverage" in resolved:
        # This new quantity is accepted only with its exact current Windows
        # source and every per-run face/value. Old complete-source receipts
        # retain their previous path and do not acquire a synthetic new scope.
        evidence = element.get("evidence") if isinstance(element.get("evidence"), dict) else {}
        actual_coverage = _windows_submitted_coverage(element, evidence.get("native_label_fonts"), fonts)
        covered = (actual_coverage is not None and resolved["coverage"] == actual_coverage
                   and resolved.get("source_span_complete") is False
                   and resolved.get("source") == WINDOWS_FACE_SOURCE
                   and resolved.get("source_evidence_path") == "evidence.native_label_fonts"
                   and faces == _windows_faces(fonts))
    if (not isinstance(resolved, dict) or not covered
            or not isinstance(faces, list) or not faces or not isinstance(fonts, list) or not fonts
            or {_identity(face) for face in faces} != {_identity(font) for font in fonts}):
        issues.append({"field": "font_weight.resolved", "reason": "Resolved weight does not cover the independently measured actual font faces"})
    elif any(not isinstance(face, dict) or not weight(face.get("value")) or not isinstance(face.get("source"), str) or not face["source"]
             or not isinstance(face.get("raw"), dict) or not isinstance(face.get("family_name"), str)
             or not face["family_name"] for face in faces):
        issues.append({"field": "font_weight.resolved", "reason": "An actual rendered face has no measured numeric weight; names and configured requests are not substitutes"})
    return issues


def compare_font_weights(reference, native):
    if not any(applicable(item) for item in (reference, native)):
        return []
    left, right = project_font_weights(reference), project_font_weights(native)
    issues = [(side, issue) for side, element, measured in (("reference", reference, left), ("native", native, right))
              for issue in font_weight_issues(element, measured)]
    issues.extend((side, {"field": "font_weight.quantities", "reason": "This counterpart has no text/font-glyph weight measurement"})
                  for side, element in (("reference", reference), ("native", native)) if not applicable(element))
    result = []
    for field in ("configured", "resolved"):
        relevant = [(side, issue) for side, issue in issues if issue["field"] in ("font_weight." + field, "font_weight.quantities")]
        a, b = left.get(field), right.get(field)
        if relevant:
            result.append({"field": "font_weight." + field, "expected": a, "actual": b,
                           "reason": "Missing comparable actual font-weight quantity", "measurement_errors": relevant})
            continue
        if field == "configured":
            if a["value"] != b["value"]:
                result.append({"field": "font_weight.configured", "expected": a["value"], "actual": b["value"], "tolerance": 0})
            continue
        faces_a, faces_b = a["faces"], b["faces"]
        use_postscript = all(isinstance(face.get("postscript_name"), str) and face["postscript_name"] for face in faces_a + faces_b)
        def signature(faces):
            values = {}
            for face in faces:
                name = face["postscript_name"] if use_postscript else face["family_name"]
                values.setdefault(name, set()).add(face["value"])
            return {name: sorted(weights) for name, weights in sorted(values.items())}
        values_a, values_b = signature(faces_a), signature(faces_b)
        if values_a != values_b:
            result.append({"field": "font_weight.resolved", "expected": values_a, "actual": values_b,
                           "tolerance": 0, "identity_quantity": "postscript_name" if use_postscript else "family_name"})
    return result
