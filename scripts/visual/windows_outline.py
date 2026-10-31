"""Actual WinUI primitive own-paint outline proof; absent fields stay unknown.

Children, control templates and app hand-in Composition paint do not inherit an
ordinary primitive's proof. No reference element or expected pixel is read.
"""
from copy import deepcopy


SOURCE = "winui-own-outline-v1"
RUN_SOURCE = "actual TextElement runtime type and owner ContentStart/ContentEnd range"
VECTOR_RUNTIME = "Relic.MainWindow+ReferenceVectorIcon"
VECTOR_CONTRACT = "relic-reference-vector-usercontrol-child-only"
VECTOR_SOURCE = "actual ReferenceVectorIcon Content/VectorCanvas/VectorPath object identities"
LABEL_RUNTIME = "Relic.NativeLabel"
LABEL_CONTRACT = "relic-native-label-panel-bound-image"
LABEL_SOURCE = "actual sealed NativeLabel runtime and sole production Image object identity"
LABEL_SURFACE_SOURCE = "actual NativeLabel production Image object identity and SurfaceImageSource COM binding"
PERSON_RUNTIME = "Microsoft.UI.Xaml.Controls.PersonPicture"
PERSON_CONTRACT = "native-personpicture-control-template-children-only"
PERSON_SOURCE = "actual exact PersonPicture runtime, Control.Template and current visual children"
PERSON_SDK_SOURCE = "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/PersonPicture/PersonPicture.cpp"
SELECTOR_ITEM_RUNTIME = "Microsoft.UI.Xaml.Controls.SelectorBarItem"
SELECTOR_ITEM_CONTRACT = "native-selectorbaritem-template-children-only"
SELECTOR_ITEM_SOURCE = "actual exact SelectorBarItem runtime, base chain, Control.Template and current visual children"
SELECTOR_ITEM_SDK_SOURCE = "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/SelectorBar/SelectorBarItem.cpp"
TOKEN_RUNTIMES = {"Relic.OverviewChipView", "Relic.OverviewBadgeView"}
TOKEN_CONTRACT = "relic-overview-token-template-content"
TOKEN_SOURCE = "actual sealed OverviewTokenView leaf runtime, template and ContentPresenter/Content object identities"
SIDEBAR_RUNTIME = "Relic.NativeSidebarRow"
SIDEBAR_CONTRACT = "relic-sidebar-row-template-content"
SIDEBAR_SOURCE = "actual sealed NativeSidebarRow runtime, current template and ContentPresenter/Content object identities"
DOT_RUNTIME = "Relic.NativeStateDotView"
DOT_CONTRACT = "relic-state-dot-grid-owned-ellipses"
DOT_SOURCE = "actual sealed NativeStateDotView runtime and Surround/VacancyRing object identities"
DOT_LAYERS_SOURCE = "actual NativeStateDotView owned paint objects and current Children order"
DOT_LAYER_SOURCE = "actual NativeStateDotView owned Ellipse object identity"
SCROLL_PRESENTER_RUNTIME = "Microsoft.UI.Xaml.Controls.ScrollContentPresenter"
SCROLL_PRESENTER_CONTRACT = "native-scroll-content-presenter-fill-border-and-content"
SCROLL_PRESENTER_SOURCE = "actual exact ScrollContentPresenter runtime BaseType/IsSealed and current visual-child count"
SCROLL_PRESENTER_SDK_SOURCE = "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/controls/generated/CScrollContentPresenter.g.h"
LOCAL_LAYOUT_SOURCE = "actual local layout Type.BaseType/IsSealed and exact audited source contract"
# Audited exact production classes add layout, a real region peer or retained
# child composition. Their native Panel background/border and all independent
# child/focus/Composition obligations remain unchanged.
LOCAL_LAYOUT_CONTRACTS = {
    "Relic.CenteredFractionLayout": ("relic-centered-fraction-panel-layout-only", "Microsoft.UI.Xaml.Controls.Panel", "native/windows/Relic/Conversation.cs#CenteredFractionLayout"),
    "Relic.MessageBubbleLayout": ("relic-message-bubble-panel-layout-only", "Microsoft.UI.Xaml.Controls.Panel", "native/windows/Relic/Conversation.cs#MessageBubbleLayout"),
    "Relic.MessageHeaderRow": ("relic-message-header-panel-layout-only", "Microsoft.UI.Xaml.Controls.Panel", "native/windows/Relic/MessageHeaderRow.cs#MessageHeaderRow"),
    "Relic.ActionRow": ("relic-action-row-panel-layout-only", "Microsoft.UI.Xaml.Controls.Panel", "native/windows/Relic/Design.cs#ActionRow"),
    "Relic.DetailsFilterRow": ("relic-details-filter-panel-layout-only", "Microsoft.UI.Xaml.Controls.Panel", "native/windows/Relic/DetailsStyles.cs#DetailsFilterRow"),
    "Relic.NativeRegionGrid": ("relic-region-grid-peer-only", "Microsoft.UI.Xaml.Controls.Grid", "native/windows/Relic/NativeRegion.cs#NativeRegionGrid"),
    "Relic.NativeOrganizationAvatarPaint": ("relic-organization-avatar-grid-owned-children", "Microsoft.UI.Xaml.Controls.Grid", "native/windows/Relic/NativeAvatarParts.cs#NativeOrganizationAvatarPaint"),
    "Relic.NativeSettingsNavigationLabel": ("relic-settings-label-grid-owned-child", "Microsoft.UI.Xaml.Controls.Grid", "native/windows/Relic/NativeSettingsNavigationLabel.cs#NativeSettingsNavigationLabel"),
}
TEMPLATE_CONTROL_CONTRACT = "native-core-control-template-children-only"
TOGGLE_RUNTIME = "Relic.NativeOverviewToggle"
TOGGLE_CONTRACT = "relic-overview-toggle-template-parts-only"
TOGGLE_SOURCE = "actual sealed NativeOverviewToggle base type, retained parts and applied template"
# Exact SDK 1.6.9 core types. HWWalk.cpp's pre/post-child switches do not
# render these controls themselves. They do render ContentControl, item
# presenters and TextBoxView; none of those is covered by this list. Applied
# children, current focus and attached Composition retain their own checks.
TEMPLATE_CONTROL_TYPES = {
    **{"Microsoft.UI.Xaml.Controls." + name: TEMPLATE_CONTROL_CONTRACT
       for name in ("Button", "ScrollViewer", "ListViewItem", "ListView", "ComboBox", "TextBox")},
    **{"Microsoft.UI.Xaml.Controls.Primitives." + name: TEMPLATE_CONTROL_CONTRACT
       for name in ("RepeatButton", "ToggleButton", "ScrollBar", "Thumb")},
}
CONTRACTS = {
    **TEMPLATE_CONTROL_TYPES,
    "Microsoft.UI.Xaml.Controls.Border": "native-border-fill-and-border",
    "Microsoft.UI.Xaml.Controls.ContentPresenter": "native-presenter-fill-border-and-content",
    **{"Microsoft.UI.Xaml.Controls." + name: "native-panel-background" for name in ("Grid", "StackPanel", "Canvas")},
    **{"Microsoft.UI.Xaml.Shapes." + name: "native-shape-fill-and-stroke" for name in ("Rectangle", "Ellipse", "Line", "Path", "Polygon", "Polyline")},
    **{"Microsoft.UI.Xaml.Controls." + name: "native-text-glyphs" for name in ("TextBlock", "RichTextBlock")},
    "Microsoft.UI.Xaml.Controls.Image": "native-image-content",
    # Exact SDK 1.6.9 CViewbox has only its scale/arrange operation. Its internal
    # CBorder and public Child are independently captured visual descendants.
    "Microsoft.UI.Xaml.Controls.Viewbox": "native-viewbox-child-transform",
}


def ancestry(node_id, by_id):
    result = []
    while node_id is not None:
        if node_id in result or node_id not in by_id:
            return None
        result.append(node_id)
        node_id = by_id[node_id].get("parent")
    return result


def overview_token_content(node, by_id):
    """Return the actual bound content of an exact audited token, or None.

    This only validates the production type/template/object tree. Paint,
    interaction and the content's own obligations remain separate decisions.
    """
    raw = node.get("outline_owner_evidence")
    if not isinstance(raw, dict) or not isinstance(by_id, dict):
        return None
    runtime = raw.get("runtime_type")
    if (not isinstance(runtime, str) or runtime not in TOKEN_RUNTIMES
            or raw.get("source") != SOURCE or raw.get("status") != "measured"
            or raw.get("owner_id") != node.get("id")
            or raw.get("own_paint_contract") != TOKEN_CONTRACT
            or node.get("type") != runtime.rsplit(".", 1)[-1]):
        return None
    token = raw.get("overview_token_content")
    render_type = node.get("render_type_evidence")
    valid = (isinstance(token, dict) and token.get("source") == TOKEN_SOURCE
             and token.get("status") == "measured" and token.get("owner_id") == node["id"]
             and token.get("base_type") == "Relic.OverviewTokenView"
             and token.get("base_base_type") == "Microsoft.UI.Xaml.Controls.ContentControl"
             and token.get("is_sealed") is True
             and token.get("audited_source") == "native/windows/Relic/OverviewStyles.cs#OverviewTokenView"
             and token.get("template_present") is True
             and token.get("template_type") == "Microsoft.UI.Xaml.Controls.ControlTemplate"
             and type(token.get("visual_child_count")) is int and token["visual_child_count"] == 1
             and token.get("presenter_runtime_type") == "Microsoft.UI.Xaml.Controls.ContentPresenter"
             and token.get("presenter_is_current_only_child") is True
             and token.get("presenter_content_same_object") is True
             and token.get("content_is_current_presenter_child") is True
             and isinstance(render_type, dict) and render_type.get("source") == "Actual runtime XAML base types"
             and render_type.get("is_control") is True and render_type.get("is_content_control") is True
             and render_type.get("control_template_present") is True)
    presenter_id = token.get("presenter_id") if isinstance(token, dict) else None
    content_id = token.get("content_id") if isinstance(token, dict) else None
    presenter = by_id.get(presenter_id) if isinstance(presenter_id, str) else None
    content = by_id.get(content_id) if isinstance(content_id, str) else None
    valid = (valid and isinstance(presenter, dict) and isinstance(content, dict)
             and len({node["id"], presenter_id, content_id}) == 3
             and presenter.get("type") == "ContentPresenter" and presenter.get("parent") == node["id"]
             and content.get("type") == token.get("content_type") and isinstance(token.get("content_type"), str)
             and bool(token["content_type"]) and content.get("parent") == presenter_id
             and [child["id"] for child in by_id.values()
                  if child.get("parent") == node["id"] and not child.get("text_run_source")] == [presenter_id]
             and [child["id"] for child in by_id.values()
                  if child.get("parent") == presenter_id and not child.get("text_run_source")] == [content_id])
    return content if valid else None


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
    local_contract = LOCAL_LAYOUT_CONTRACTS.get(runtime) if isinstance(runtime, str) else None
    token_runtime = isinstance(runtime, str) and runtime in TOKEN_RUNTIMES
    contract = (VECTOR_CONTRACT if runtime == VECTOR_RUNTIME else LABEL_CONTRACT if runtime == LABEL_RUNTIME
                else PERSON_CONTRACT if runtime == PERSON_RUNTIME else TOKEN_CONTRACT if token_runtime
                else SELECTOR_ITEM_CONTRACT if runtime == SELECTOR_ITEM_RUNTIME
                else DOT_CONTRACT if runtime == DOT_RUNTIME else SCROLL_PRESENTER_CONTRACT if runtime == SCROLL_PRESENTER_RUNTIME
                else TOGGLE_CONTRACT if runtime == TOGGLE_RUNTIME
                else SIDEBAR_CONTRACT if runtime == SIDEBAR_RUNTIME
                else local_contract[0] if local_contract
                else CONTRACTS.get(runtime) if isinstance(runtime, str) else None)
    expected_type = "ReferenceVectorIcon" if runtime == VECTOR_RUNTIME else runtime.rsplit(".", 1)[-1] if isinstance(runtime, str) else None
    if (contract is None or raw.get("own_paint_contract") != contract
            or expected_type != node.get("type") or raw.get("owner_id") != node.get("id")):
        gap("No exact known native primitive own-paint contract; derived and compound renderers remain unmeasured")
    if local_contract:
        local = raw.get("local_layout")
        if (not isinstance(local, dict) or local.get("source") != LOCAL_LAYOUT_SOURCE
                or local.get("owner_id") != node.get("id") or local.get("is_sealed") is not True
                or local.get("base_type") != local_contract[1] or local.get("audited_source") != local_contract[2]):
            gap("Exact local layout source contract lacks its actual sealed runtime/base-type binding")
    if runtime == TOGGLE_RUNTIME:
        toggle = raw.get("local_toggle")
        render_type = node.get("render_type_evidence")
        if (not isinstance(toggle, dict) or toggle.get("source") != TOGGLE_SOURCE
                or toggle.get("owner_id") != node.get("id") or toggle.get("is_sealed") is not True
                or toggle.get("base_type") != "Microsoft.UI.Xaml.Controls.Primitives.ToggleButton"
                or toggle.get("audited_source") != "native/windows/Relic/NativeOverviewToggle.cs#NativeOverviewToggle"
                or toggle.get("current_parts_same_objects") is not True
                or toggle.get("template_present") is not True
                or toggle.get("template_type") != "Microsoft.UI.Xaml.Controls.ControlTemplate"
                or not isinstance(render_type, dict) or render_type.get("is_control") is not True
                or render_type.get("control_template_present") is not True):
            gap("Exact retained-part ToggleButton subclass lacks its sealed runtime/base-type/current-template receipt")
        evidence["scope"] = ("Exact NativeOverviewToggle own container only; applied template parts, "
                             "their paint, live focus and hand-in Composition retain independent obligations")
    if runtime == SCROLL_PRESENTER_RUNTIME:
        # The exact SDK class is sealed, and its native CContentPresenter base
        # draws its own fill/border. This proof is not template-only, does not
        # infer a viewport/clip, and accepts any completely captured child set.
        presenter = raw.get("scroll_presenter")
        current_children = [child for child in by_id.values()
                            if child.get("parent") == node["id"] and not child.get("text_run_source")]
        valid_presenter = (isinstance(presenter, dict) and presenter.get("source") == SCROLL_PRESENTER_SOURCE
                           and presenter.get("status") == "measured" and presenter.get("owner_id") == node["id"]
                           and presenter.get("base_type") == "Microsoft.UI.Xaml.Controls.ContentPresenter"
                           and presenter.get("is_sealed") is True
                           and presenter.get("audited_sdk_source") == SCROLL_PRESENTER_SDK_SOURCE
                           and type(presenter.get("visual_child_count")) is int
                           and presenter["visual_child_count"] == len(current_children))
        if not valid_presenter:
            gap("Exact ScrollContentPresenter lacks its sealed SDK base-type and actual current-child-count receipt")
        else:
            evidence["scope"] = ("Exact SDK ScrollContentPresenter own fill/border only; actual scroll/clip geometry "
                                 "and independently captured children retain their own obligations")
    if runtime == SIDEBAR_RUNTIME:
        row = raw.get("sidebar_row_content")
        render_type = node.get("render_type_evidence")
        valid_row = (isinstance(row, dict) and row.get("source") == SIDEBAR_SOURCE
                     and row.get("status") == "measured" and row.get("owner_id") == node["id"]
                     and row.get("base_type") == "Microsoft.UI.Xaml.Controls.ListViewItem"
                     and row.get("is_sealed") is True
                     and row.get("audited_source") == "native/windows/Relic/NativeSidebarRow.cs#NativeSidebarRow"
                     and row.get("template_present") is True
                     and row.get("template_type") == "Microsoft.UI.Xaml.Controls.ControlTemplate"
                     and row.get("same_template_after") is True and row.get("same_content_after") is True
                     and type(row.get("visual_child_count")) is int and row["visual_child_count"] == 1
                     and row.get("presenter_runtime_type") == "Microsoft.UI.Xaml.Controls.ContentPresenter"
                     and row.get("presenter_is_current_only_child") is True
                     and row.get("presenter_content_same_object") is True
                     and row.get("content_is_current_presenter_child") is True
                     and isinstance(render_type, dict) and render_type.get("source") == "Actual runtime XAML base types"
                     and render_type.get("is_control") is True and render_type.get("is_content_control") is True
                     and render_type.get("control_template_present") is True)
        presenter_id = row.get("presenter_id") if isinstance(row, dict) else None
        content_id = row.get("content_id") if isinstance(row, dict) else None
        presenter = by_id.get(presenter_id) if isinstance(presenter_id, str) else None
        content = by_id.get(content_id) if isinstance(content_id, str) else None
        valid_row = (valid_row and isinstance(presenter, dict) and isinstance(content, dict)
                     and len({node["id"], presenter_id, content_id}) == 3
                     and presenter.get("type") == "ContentPresenter" and presenter.get("parent") == node["id"]
                     and content.get("type") == row.get("content_type") and isinstance(row.get("content_type"), str)
                     and bool(row["content_type"]) and content.get("parent") == presenter_id
                     and [child["id"] for child in by_id.values()
                          if child.get("parent") == node["id"] and not child.get("text_run_source")] == [presenter_id]
                     and [child["id"] for child in by_id.values()
                          if child.get("parent") == presenter_id and not child.get("text_run_source")] == [content_id])
        if not valid_row:
            gap("Exact sidebar row lacks its sealed ListViewItem class, current template and ContentPresenter/Content object binding")
        else:
            evidence["scope"] = ("Exact sealed NativeSidebarRow ListViewItem parent only; current template children, "
                                 "their background/content, focus and Composition retain independent obligations")
    if token_runtime:
        # Only the two audited sealed leaves over OverviewTokenView. The fixed
        # SDK ContentControl render branch handles ListViewBaseItem chrome;
        # these exact local classes instead use their actual ContentPresenter.
        # Background/border properties and independently measured child paint
        # are retained; this is not a generic ContentControl exemption.
        if overview_token_content(node, by_id) is None:
            gap("Exact overview token lacks its sealed class chain, applied template and current ContentPresenter/Content identity proof")
        else:
            evidence["scope"] = ("Exact sealed overview token ContentControl parent only; its actual ContentPresenter "
                                 "and content retain their own paint/focus/Composition obligations")
    if runtime == DOT_RUNTIME:
        dot = raw.get("state_dot_grid")
        layers = node.get("state_dot_evidence")
        render_type = node.get("render_type_evidence")
        valid_dot = (isinstance(dot, dict) and dot.get("source") == DOT_SOURCE
                     and dot.get("status") == "measured" and dot.get("owner_id") == node["id"]
                     and dot.get("base_type") == "Microsoft.UI.Xaml.Controls.Grid" and dot.get("is_sealed") is True
                     and dot.get("audited_source") == "native/windows/Relic/NativeStateDotView.cs#NativeStateDotView"
                     and type(dot.get("visual_child_count")) is int and dot["visual_child_count"] == 2
                     and type(dot.get("panel_child_count")) is int and dot["panel_child_count"] == 2
                     and dot.get("production_layers_are_current_children") is True
                     and isinstance(render_type, dict) and render_type.get("source") == "Actual runtime XAML base types"
                     and render_type.get("is_panel") is True and render_type.get("is_control") is False
                     and isinstance(layers, dict) and layers.get("source") == DOT_LAYERS_SOURCE
                     and layers.get("complete") is True and layers.get("current_children_same_objects") is True)
        layer_ids = [dot.get(key) for key in ("surround_id", "vacancy_ring_id")] if isinstance(dot, dict) else []
        if valid_dot:
            valid_dot = (all(isinstance(eid, str) and eid in by_id for eid in layer_ids)
                         and len(set(layer_ids + [node["id"]])) == 3
                         and layers.get("current_children") == layer_ids
                         and [child["id"] for child in sorted(
                             (item for item in by_id.values() if item.get("parent") == node["id"] and not item.get("text_run_source")),
                             key=lambda item: item.get("render_sibling_order", -1))] == layer_ids)
        if valid_dot:
            expected_layers = [{"id": eid, "property": role, "child_index": index}
                               for index, (eid, role) in enumerate(zip(layer_ids, ("Surround", "VacancyRing")))]
            current_layers = layers.get("layers")
            valid_dot = (isinstance(current_layers, list) and len(current_layers) == 2
                         and all(isinstance(layer, dict) and type(layer.get("child_index")) is int
                                 and all(layer.get(key) == value for key, value in expected.items())
                                 for layer, expected in zip(current_layers, expected_layers)))
            for expected in expected_layers:
                child = by_id[expected["id"]]
                binding = child.get("state_dot_layer_evidence")
                valid_dot = (valid_dot and child.get("type") == "Ellipse" and child.get("parent") == node["id"]
                             and isinstance(binding, dict) and binding.get("source") == DOT_LAYER_SOURCE
                             and binding.get("owner_id") == node["id"] and binding.get("property") == expected["property"]
                             and type(binding.get("child_index")) is int and binding["child_index"] == expected["child_index"])
        if not valid_dot:
            gap("Exact state-dot Grid lacks its sealed runtime and complete current Surround/VacancyRing object bindings")
        else:
            evidence["scope"] = ("Exact state-dot Grid own panel paint only; the two actual Ellipse layers remain independent. "
                                 "No CSS inset-shadow or final-raster equivalence is supplied")
    if runtime == PERSON_RUNTIME:
        # Fixed SDK's unsealed PersonPicture updates its real template's
        # TextBlock/Ellipse/brushes/VisualState, not a second parent renderer.
        # https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/PersonPicture/PersonPicture.idl
        # https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/hw/hwwalk.cpp#L1498
        picture = raw.get("person_picture_template")
        render_type = node.get("render_type_evidence")
        actual_children = [child for child in by_id.values()
                           if child.get("parent") == node["id"] and not child.get("text_run_source")]
        valid_picture = (isinstance(picture, dict) and picture.get("source") == PERSON_SOURCE
                         and picture.get("status") == "measured" and picture.get("owner_id") == node["id"]
                         and picture.get("base_type") == "Microsoft.UI.Xaml.Controls.Control"
                         and picture.get("is_sealed") is False and picture.get("audited_sdk_source") == PERSON_SDK_SOURCE
                         and picture.get("template_present") is True
                         and picture.get("template_type") == "Microsoft.UI.Xaml.Controls.ControlTemplate"
                         and type(picture.get("visual_child_count")) is int
                         and picture["visual_child_count"] == len(actual_children) > 0
                         and isinstance(render_type, dict) and render_type.get("source") == "Actual runtime XAML base types"
                         and render_type.get("is_control") is True and render_type.get("control_template_present") is True)
        if not valid_picture:
            gap("Exact PersonPicture has no complete actual runtime, present ControlTemplate and nonempty current-child receipt")
        else:
            evidence["scope"] = ("Exact SDK PersonPicture Control container only; current template descendants "
                                 "and their paint/focus/Composition retain independent obligations")
    if runtime == SELECTOR_ITEM_RUNTIME:
        # Pinned SelectorBarItem.cpp only changes template icon/text visibility;
        # ItemContainer.cpp owns template child/VisualState/input updates. Its
        # Control base has no pre/post-child renderer in the pinned HWWalk.
        # This exact unsealed class does not grant that proof to its subclasses.
        item = raw.get("selector_item_template")
        render_type = node.get("render_type_evidence")
        actual_children = [child for child in by_id.values()
                           if child.get("parent") == node["id"] and not child.get("text_run_source")]
        valid_item = (isinstance(item, dict) and item.get("source") == SELECTOR_ITEM_SOURCE
                      and item.get("status") == "measured" and item.get("owner_id") == node["id"]
                      and item.get("base_type") == "Microsoft.UI.Xaml.Controls.ItemContainer"
                      and item.get("base_base_type") == "Microsoft.UI.Xaml.Controls.Control"
                      and item.get("is_sealed") is False and item.get("audited_sdk_source") == SELECTOR_ITEM_SDK_SOURCE
                      and item.get("template_present") is True
                      and item.get("template_type") == "Microsoft.UI.Xaml.Controls.ControlTemplate"
                      and type(item.get("visual_child_count")) is int
                      and item["visual_child_count"] == len(actual_children) > 0
                      and isinstance(render_type, dict) and render_type.get("source") == "Actual runtime XAML base types"
                      and render_type.get("is_control") is True and render_type.get("control_template_present") is True)
        if not valid_item:
            gap("Exact SelectorBarItem lacks its actual base chain, present ControlTemplate and nonempty current-child receipt")
        else:
            evidence["scope"] = ("Exact SDK SelectorBarItem parent only; template descendants and their paint, "
                                 "current focus and hand-in Composition retain independent obligations")
    if runtime == LABEL_RUNTIME:
        label = raw.get("native_label_content")
        valid_label = (isinstance(label, dict) and label.get("source") == LABEL_SOURCE
                       and label.get("status") == "measured" and label.get("owner_id") == node.get("id")
                       and label.get("base_type") == "Microsoft.UI.Xaml.Controls.Panel"
                       and label.get("is_sealed") is True
                       and label.get("audited_source") == "native/windows/Relic/NativeLabel.cs#NativeLabel"
                       and type(label.get("visual_child_count")) is int and label["visual_child_count"] == 1
                       and type(label.get("panel_child_count")) is int and label["panel_child_count"] == 1
                       and label.get("production_image_is_current_only_child") is True)
        image_id = label.get("image_id") if isinstance(label, dict) else None
        image = by_id.get(image_id) if isinstance(image_id, str) else None
        image_type = image.get("outline_owner_evidence") if isinstance(image, dict) else None
        binding = label.get("production_image_binding") if isinstance(label, dict) else None
        captured_binding = image.get("native_label_surface_evidence") if isinstance(image, dict) else None
        valid_label = (valid_label and isinstance(image, dict) and image.get("type") == "Image"
                       and isinstance(image_type, dict) and image_type.get("runtime_type") == "Microsoft.UI.Xaml.Controls.Image"
                       and image.get("parent") == node["id"]
                       and [child["id"] for child in by_id.values()
                            if child.get("parent") == node["id"] and not child.get("text_run_source")] == [image_id]
                       and isinstance(binding, dict) and isinstance(captured_binding, dict))
        if valid_label:
            # Two actual observations of the same production child must agree.
            # Do not infer a surface from the label's name, text or geometry.
            for actual_binding in (binding, captured_binding):
                valid_label = (valid_label and actual_binding.get("source") == LABEL_SURFACE_SOURCE
                               and actual_binding.get("owner_id") == node["id"]
                               and actual_binding.get("same_image_object") is True
                               and actual_binding.get("surface_binding_same_com_identity") is True
                               and actual_binding.get("source_type") == "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource"
                               and all(type(actual_binding.get(key)) is int and actual_binding[key] > 0
                                       for key in ("layout_revision", "surface_revision", "draw_ordinal")))
            valid_label = (valid_label and all(binding.get(key) == captured_binding.get(key)
                           for key in ("layout_revision", "surface_revision", "draw_ordinal")))
        if not valid_label:
            gap("Exact NativeLabel parent paint has no complete sealed runtime, sole production Image and current bound-surface identity proof")
        else:
            evidence["scope"] = ("This exact NativeLabel's native Panel paint only; its actual production Image "
                                 "and glyph/surface/frame evidence retain independent obligations")
    if runtime == VECTOR_RUNTIME:
        vector = raw.get("vector_content")
        valid_vector = (isinstance(vector, dict) and vector.get("source") == VECTOR_SOURCE
                        and vector.get("status") == "measured" and vector.get("owner_id") == node.get("id")
                        and vector.get("template_is_null") is True
                        and vector.get("content_is_current_visual_child") is True
                        and vector.get("viewbox_child_is_vector_canvas") is True
                        and vector.get("canvas_children_are_vector_path") is True)
        if valid_vector:
            ids = [vector.get(key) for key in ("content_id", "canvas_id", "path_id")]
            valid_vector = (all(isinstance(value, str) and value in by_id for value in ids)
                            and len(set(ids + [node["id"]])) == 4)
        if valid_vector:
            content, canvas, path = (by_id[value] for value in ids)
            canvas_ancestors = ancestry(canvas["id"], by_id)
            measured_path = vector.get("canvas_visual_path")
            valid_vector = (content.get("type") == "Viewbox" and content.get("parent") == node["id"]
                            and canvas.get("type") == "Canvas" and path.get("type") == "Path"
                            and path.get("parent") == canvas["id"]
                            and vector.get("canvas_visual_path_complete") is True
                            and isinstance(measured_path, list) and canvas_ancestors is not None
                            and node["id"] in canvas_ancestors
                            and measured_path == canvas_ancestors[:canvas_ancestors.index(node["id"]) + 1]
                            and content["id"] in measured_path
                            and [item["id"] for item in by_id.values()
                                 if item.get("parent") == node["id"] and not item.get("text_run_source")] == [content["id"]]
                            and [item["id"] for item in by_id.values()
                                 if item.get("parent") == canvas["id"] and not item.get("text_run_source")] == [path["id"]])
        if not valid_vector:
            gap("Exact ReferenceVectorIcon production Content, Canvas and Path identities are not completely bound to the current visual tree")
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
