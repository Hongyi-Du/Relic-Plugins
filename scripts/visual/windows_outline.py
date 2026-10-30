"""Actual WinUI primitive own-paint outline proof; absent fields stay unknown.

Children, control templates and app hand-in Composition paint do not inherit an
ordinary primitive's proof. No reference element or expected pixel is read.
"""
from copy import deepcopy


SOURCE = "winui-own-outline-v1"
RUN_SOURCE = "actual TextElement runtime type and owner ContentStart/ContentEnd range"
CONTRACTS = {
    "Microsoft.UI.Xaml.Controls.Border": "native-border-fill-and-border",
    "Microsoft.UI.Xaml.Controls.ContentPresenter": "native-presenter-fill-border-and-content",
    **{"Microsoft.UI.Xaml.Controls." + name: "native-panel-background" for name in ("Grid", "StackPanel", "Canvas")},
    **{"Microsoft.UI.Xaml.Shapes." + name: "native-shape-fill-and-stroke" for name in ("Rectangle", "Ellipse", "Line", "Path", "Polygon", "Polyline")},
    **{"Microsoft.UI.Xaml.Controls." + name: "native-text-glyphs" for name in ("TextBlock", "RichTextBlock")},
    "Microsoft.UI.Xaml.Controls.Image": "native-image-content",
}


def ancestry(node_id, by_id):
    result = []
    while node_id is not None:
        if node_id in result or node_id not in by_id:
            return None
        result.append(node_id)
        node_id = by_id[node_id].get("parent")
    return result


def native_outline(node, by_id):
    """Return (canonical value, audit receipt, coverage gaps) for one owner."""
    raw = node.get("outline_owner_evidence")
    evidence = {"source": SOURCE, "absence_proven": False, "raw": deepcopy(raw),
                "scope": "This exact primitive's own paint only; independently emitted children keep their own obligations"}
    issues = []

    def gap(reason):
        issues.append({"id": node.get("id"), "property": "style.outline", "reason": reason})

    run = node.get("text_run_source")
    if node.get("type") == "Run" and isinstance(run, dict):
        # These are real TextElement records projected from the current owner's
        # measured ranges, not fake FrameworkElements with copied focus fields.
        owner = by_id.get(run.get("owner"))
        runs = owner.get("layout", {}).get("rich_text_runs") if isinstance(owner, dict) else None
        index = run.get("index")
        record = runs[index] if isinstance(runs, list) and type(index) is int and 0 <= index < len(runs) else None
        proof = record.get("own_paint_evidence") if isinstance(record, dict) else None
        valid = (isinstance(proof, dict) and proof.get("source") == RUN_SOURCE
                 and proof.get("runtime_type") == "Microsoft.UI.Xaml.Documents.Run"
                 and proof.get("exact_run_type") is True and proof.get("owner_id") == owner.get("id")
                 and record.get("type") == "Run" and record.get("text") == node.get("text")
                 and node.get("parent") == owner.get("id")
                 and all(type(run.get(key)) is int and proof.get(key) == run[key] == record.get(key)
                         for key in ("start_offset", "end_offset")))
        evidence["text_element"] = deepcopy(proof)
        if valid:
            evidence.update(absence_proven=True, source=RUN_SOURCE,
                            scope="Actual Run glyph-only operation; the owning text container and its focus/Composition layers remain separate")
            return "none", evidence, issues
        gap("Projected text leaf has no exact actual Run identity and owner-range proof; no own-outline absence is inferred")
        return None, evidence, issues

    if not isinstance(raw, dict) or raw.get("source") != SOURCE or raw.get("status") != "measured":
        gap("Current primitive outline-owner receipt is missing or failed")
        return None, evidence, issues
    runtime = raw.get("runtime_type")
    if (not isinstance(runtime, str) or runtime not in CONTRACTS
            or raw.get("own_paint_contract") != CONTRACTS.get(runtime)
            or runtime.rsplit(".", 1)[-1] != node.get("type") or raw.get("owner_id") != node.get("id")):
        gap("No exact known native primitive own-paint contract; derived and compound renderers remain unmeasured")
    composition = raw.get("composition")
    if (not isinstance(composition, dict) or composition.get("status") != "measured"
            or not {"child_visual_present", "child_visual_type", "shadow_present", "shadow_type"}.issubset(composition)
            or composition.get("api") != "ElementCompositionPreview.GetElementChildVisual(actual owner)"
            or composition.get("child_visual_present") is not False or composition.get("child_visual_type") is not None
            or composition.get("shadow_present") is not False or composition.get("shadow_type") is not None):
        gap("Actual app hand-in Composition visual or Shadow is present, unknown or failed; no independent outline ownership has been established")
    children = raw.get("children")
    items = children.get("items") if isinstance(children, dict) else None
    valid_children = isinstance(children, dict) and children.get("status") == "measured" and children.get("complete") is True and isinstance(items, list)
    if valid_children:
        expected = sorted((child for child in by_id.values() if child.get("parent") == node["id"]
                           and not child.get("text_run_source")), key=lambda child: child.get("render_sibling_order", -1))
        valid_children = (len(items) == len(expected)
                          and all(isinstance(item, dict) and item.get("id") == child.get("id")
                                  and type(item.get("index")) is int and item["index"] == index == child.get("render_sibling_order")
                                  and item.get("same_parent_object") is True
                                  for index, (item, child) in enumerate(zip(items, expected))))
    if not valid_children:
        gap("Current direct visual-child identities are incomplete; separate children cannot be assumed accounted for")

    focus = raw.get("focus")
    global_focus = focus.get("global") if isinstance(focus, dict) else None
    valid_focus = (isinstance(focus, dict) and focus.get("status") == "measured"
                   and focus.get("state") == "Unfocused"
                   and type(focus.get("use_system_focus_visuals")) is bool
                   and type(focus.get("is_template_focus_target")) is bool
                   and isinstance(global_focus, dict) and global_focus.get("source") == SOURCE
                   and global_focus.get("status") == "measured")
    owner_path = ancestry(node.get("id"), by_id)
    valid_focus = valid_focus and focus.get("owner_ancestry_complete") is True and owner_path is not None and focus.get("owner_ancestry") == owner_path
    if valid_focus and global_focus.get("focused_object_is_null") is True:
        valid_focus = (focus.get("relationship") == "no-focused-object"
                       and {"focused_object_id", "focused_object_type", "focused_object_focus_state",
                            "focused_object_use_system_focus_visuals"}.issubset(global_focus)
                       and all(global_focus.get(key) is None for key in ("focused_object_id", "focused_object_type",
                                                                       "focused_object_focus_state", "focused_object_use_system_focus_visuals")))
    elif valid_focus and global_focus.get("focused_object_is_null") is False:
        focused_id = global_focus.get("focused_object_id")
        focused_path = ancestry(focused_id, by_id) if isinstance(focused_id, str) else None
        valid_focus = (isinstance(global_focus.get("focused_object_type"), str)
                       and global_focus.get("focused_object_focus_state") in ("Keyboard", "Pointer", "Programmatic")
                       and type(global_focus.get("focused_object_use_system_focus_visuals")) is bool
                       and focus.get("focused_ancestry_complete") is True and focused_path is not None
                       and focus.get("focused_ancestry") == focused_path
                       and focused_id not in owner_path and node["id"] not in focused_path
                       and focus.get("relationship") == "unrelated-in-captured-visual-tree")
    else:
        valid_focus = False
    if not valid_focus:
        gap("Actual focused object/state/visual-tree relationship is missing or related to this owner; template/system focus paint remains unmeasured")
    evidence["absence_proven"] = not issues
    return ("none" if not issues else None), evidence, issues
