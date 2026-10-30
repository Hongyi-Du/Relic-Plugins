"""Validate one current AppKit field-editor alias without asserting paint equivalence.

The producer owns the currentEditor/firstResponder relationship. Its retained
AX editor is still independently audited by the ordinary measurement checks;
it never supplies the owner's geometry, style, value, or focus state.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math


CONTRACT = "appkit-current-field-editor-v2"
PROVIDER = "mounted NSTextFieldCell.controlView, NSTextField.currentEditor and NSWindow.firstResponder"
SOURCE = "live-AppKit-AX-selectors"
STRUCTURE_SOURCE = "production parent environment and current NSView.subviews ancestry"
INPUT_ROLES = {"AXTextField", "AXTextArea", "AXSearchField"}
STYLE_KEYS = {
    "font_size": "fontSize", "font_weight": "fontWeight", "foreground": "color",
    "background": "backgroundColor", "border_color": "borderColor", "border_width": "borderWidth",
    "corner_radius": "borderRadius", "border_widths": "border_widths", "border_styles": "border_styles",
    "border_colors": "border_colors", "corner_radii": "corner_radii", "opacity": "opacity",
    "background_image": "background_image", "shadow": "shadow", "outline": "outline",
    "rendered_fonts": "rendered_fonts",
}


def _string(value):
    return isinstance(value, str) and bool(value)


def _rect(value):
    if not isinstance(value, dict):
        return False
    for key in ("x", "y", "width", "height"):
        number = value.get(key)
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            return False
        try:
            if not math.isfinite(number):
                return False
        except OverflowError:
            return False
    return value["width"] > 0 and value["height"] > 0


def _evidence(element):
    value = element.get("evidence") if isinstance(element, dict) else None
    return value if isinstance(value, dict) else {}


def retained_editor_measurements(raw):
    """Audit-only spelling conversion of actual raw fields, never a paired element.

    Inapplicable state remains the actual AX value; absent measurements remain
    absent/null. The complete node stays in evidence. No owner property or
    currentEditor boolean fills a missing editor measurement.
    """
    style = raw.get("style")
    style = style if isinstance(style, dict) else {}
    evidence = deepcopy(raw)
    evidence["raw_node_id"] = raw.get("id")
    # Match the exporter's actual independent outline source, not the owner's.
    surface = raw.get("surface_evidence")
    if isinstance(surface, dict) and "outline" in surface:
        evidence["outline"] = deepcopy(surface["outline"])
    projection = raw.get("projection")
    if style.get("outline") == "none" and isinstance(projection, dict) and "native_text_outline" in projection:
        evidence["outline"] = deepcopy(projection["native_text_outline"])
    if isinstance(projection, dict) and "line_break_configuration" in projection:
        evidence["line_break_configuration"] = deepcopy(projection["line_break_configuration"])
    result = {key: deepcopy(raw.get(key)) for key in ("id", "parent", "region", "order", "kind", "text", "name", "icon")}
    result.update(bounds=deepcopy(raw.get("rect")), visible_bounds=deepcopy(raw.get("visibleRect")),
                  style={target: deepcopy(style.get(source)) for target, source in STYLE_KEYS.items()},
                  state=deepcopy(raw.get("state")), layout=deepcopy(raw.get("layout")), evidence=evidence)
    return result


def field_editor_aliases(elements):
    """Return per-owner binding issues and retained measurement nodes, without mutation.

    Both pre-be16164 system editors and actual ObservedFieldEditor instances are
    supported by their independently recorded class/identity, not a class-name
    substitution. The v2 owner is the final MemberRenameField.PaddedCell, not
    its AX-ignored NSTextField Control. V1 is never accepted as a cell binding.
    This result proves only the current alias relation, never frame continuity,
    presentation, glyph drawing or absence of independent editor paint.
    """
    if not isinstance(elements, list):
        return []
    canonical_ids = Counter(item.get("id") for item in elements if isinstance(item, dict) and _string(item.get("id")))
    canonical_objects = Counter(raw.get("object_identity") for item in elements
                                if _string((raw := _evidence(item)).get("object_identity")))
    retained = [_evidence(item).get("owned_editor_evidence") for item in elements]
    retained_ids = Counter(raw.get("id") for raw in retained if isinstance(raw, dict) and _string(raw.get("id")))
    retained_objects = Counter(raw.get("object_identity") for raw in retained
                               if isinstance(raw, dict) and _string(raw.get("object_identity")))
    results = []
    for item in elements:
        raw = _evidence(item)
        if "native_field_editor" not in raw and "owned_editor_evidence" not in raw:
            continue
        receipt, editor = raw.get("native_field_editor"), raw.get("owned_editor_evidence")
        issues = []
        result = {"owner": item.get("id"), "binding_valid": False, "issues": issues, "measurement_issues": [],
                  "retained_measurements": retained_editor_measurements(editor) if isinstance(editor, dict) else None}
        results.append(result)

        def require(condition, reason):
            if not condition:
                issues.append(reason)

        # Preserve recorded failures even when the alias proof itself is absent
        # or malformed; rejecting ownership must not discard source errors.
        if isinstance(editor, dict):
            for key in ("native_measurement_errors", "errors", "extraction_errors"):
                if key in editor:
                    errors = editor[key]
                    if not isinstance(errors, list):
                        issues.append("Retained editor " + key + " is malformed")
                    else:
                        issues.extend("Retained editor " + key + ": " + str(error) for error in errors)
            selector = editor.get("selectorEvidence")
            if isinstance(selector, dict) and selector.get("errors"):
                issues.append("Retained editor AX selector errors: " + str(selector["errors"]))
        if not isinstance(receipt, dict) or not isinstance(editor, dict):
            issues.append("Current-editor receipt and complete retained raw editor are both required")
            continue
        require(receipt.get("contract") == CONTRACT and receipt.get("provider") == PROVIDER,
                "Unknown or missing actual currentEditor/firstResponder contract")
        if receipt.get("contract") == CONTRACT:
            # The v2 producer exports the control's screen frame, not a second
            # measured cell.accessibilityFrame call or the capture coordinate
            # origin. Size agreement below is not a proof of screen position.
            result["measurement_issues"].append({
                "reason": "Cell screen-position cross-check is unmeasured: no independently checked actual cell accessibilityFrame and capture content-screen frame",
                "quantities": {
                    "cell_ax_window_frame": {"source": "retained cell AX frame after capture topLeft conversion", "bounds": deepcopy(raw.get("rect"))},
                    "control_screen_frame": {"source": "actual control.convert(bounds,to:nil) then window.convertToScreen", "bounds": deepcopy(receipt.get("owner_screen_bounds"))},
                    "screen_position_relation_proven": False}})
        owner_id, editor_id = raw.get("id"), editor.get("id")
        owner_object, editor_object = receipt.get("owner_identity"), receipt.get("editor_identity")
        control_object = receipt.get("control_identity")
        require(_string(owner_id) and item.get("id") == owner_id == raw.get("raw_node_id")
                and canonical_ids[owner_id] == 1, "Owner is not one uniquely retained canonical/raw input")
        require(_string(editor_id) and editor_id != owner_id and retained_ids[editor_id] == 1
                and canonical_ids[editor_id] == 0, "Retained editor ID is missing, ambiguous, or still independently emitted")
        require(_string(owner_object) and raw.get("object_identity") == owner_object
                and canonical_objects[owner_object] == 1 and retained_objects[owner_object] == 0,
                "Owner object identity is missing, foreign, or ambiguous")
        require(_string(editor_object) and editor.get("object_identity") == editor_object
                and editor_object != owner_object and receipt.get("current_editor_identity") == editor_object
                and canonical_objects[editor_object] == 0 and retained_objects[editor_object] == 1,
                "Editor is not the one unique actual currentEditor object")
        require(_string(control_object) and control_object != owner_object and control_object != editor_object
                and receipt.get("owner_control_view_identity") == control_object
                and receipt.get("control_cell_identity") == owner_object,
                "Cell/control ownership is not the actual bidirectional controlView/cell object relation")
        require(item.get("kind") == raw.get("kind") == editor.get("kind") == "input"
                and raw.get("role") == "AXTextField"
                and isinstance(editor.get("role"), str) and editor["role"] in INPUT_ROLES,
                "Owner and retained editor must both preserve actual input roles")
        require(raw.get("source") == editor.get("source") == SOURCE,
                "Owner or retained editor has no original live AppKit AX source")
        require(receipt.get("owner_class") == raw.get("class") == "PaddedCell",
                "Alias owner is not the contract's actual MemberRenameField.PaddedCell")
        require(_string(receipt.get("editor_class")) and receipt["editor_class"] == editor.get("class"),
                "Retained editor class disagrees with the actual currentEditor class")
        require(_string(receipt.get("owner_identifier")) and receipt["owner_identifier"] == raw.get("identifier"),
                "Current owner identifier is absent or differs from the raw input")
        require(receipt.get("is_field_editor") is True and receipt.get("same_window") is True
                and _string(receipt.get("window_identity")), "Editor has no same-window field-editor identity")
        require(receipt.get("first_responder_is_editor") is True,
                "Actual NSWindow.firstResponder is not the current field editor")
        value = receipt.get("owner_value")
        require(isinstance(value, str) and receipt.get("editor_value") == value
                and raw.get("value") == value and editor.get("value") == value,
                "Current owner/editor values disagree with retained raw AX values")
        for label, node in (("owner", raw), ("editor", editor)):
            require(node.get("visible") is True and _rect(node.get("rect")) and _rect(node.get("visibleRect")),
                    label + " has no actual positive visible input geometry")
            require(isinstance(node.get("style"), dict) and isinstance(node.get("state"), dict)
                    and isinstance(node.get("selectorEvidence"), dict), label + " raw measurement node is incomplete")
            state = node.get("state")
            require(isinstance(state, dict) and isinstance(state.get("focused"), bool),
                    label + " raw AX focused value was not retained")
            # AXFocused and window.firstResponder are distinct APIs. In actual
            # AppKit capture the active editor's AXFocused can be false.
            measured = receipt.get(label + "_screen_bounds")
            if label == "editor":
                geometry = node.get("native_view_geometry")
                require(isinstance(geometry, dict) and _rect(measured)
                        and geometry.get("screen_bounds") == measured,
                        "Editor current screen bounds disagree with the actual retained NSView geometry")
            else:
                # NSTextFieldCell is not an NSView. Its raw rect is the actual
                # accessibilityFrame in top-left window coordinates; the
                # receipt retains control.convert(bounds) in screen coordinates.
                # PaddedCell.accessibilityFrame uses that same control operation.
                # topLeft changes origin only, not size. Do not fabricate a
                # cell native_view_geometry or compare unlike x/y coordinates.
                ax_rect = node.get("rect")
                require(_rect(measured) and _rect(ax_rect)
                        and all(measured[key] == ax_rect[key] for key in ("width", "height")),
                        "Cell AX frame and actual control screen frame have missing or conflicting sizes")
            structure = node.get("native_structure")
            if isinstance(structure, dict):
                require(structure.get("source") == STRUCTURE_SOURCE
                        and structure.get("window_identity") == receipt.get("window_identity"),
                        label + " mounted structure belongs to a different or unknown window")
        selection = receipt.get("selection")
        valid_selection = isinstance(selection, dict) and all(isinstance(selection.get(key), int)
            and not isinstance(selection[key], bool) and selection[key] >= 0 for key in ("location", "length"))
        require(valid_selection and isinstance(value, str)
                and selection["location"] + selection["length"] <= len(value.encode("utf-16-le", "surrogatepass")) // 2,
                "Current editor selection is not a measured UTF-16 range of the retained value")
        # Do not silently accept a half-removed alias or a child still parented
        # to the removed input. A separate child's paint stays independently in
        # the canonical list and ordinary validation.
        require(not any(isinstance(child, dict) and child.get("parent") == editor_id for child in elements),
                "A visible child still refers to the removed field-editor input")
        require("native_field_editor" not in editor and "owned_editor_evidence" not in editor,
                "Nested field-editor alias is not covered by this single-input contract")
        result["binding_valid"] = not issues
    return results
