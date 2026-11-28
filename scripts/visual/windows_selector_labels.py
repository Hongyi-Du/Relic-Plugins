"""Read actual SelectorBarItem Tag/Content identity; never infer from tab text.

The label contract owns one text source. A separate object-identity contract
can bind its actual simple tab surface. Shadows, icons, independent controls
and all raw measurement failures retain their own records.
"""
import copy
import math


CONTRACT = "selectorbar-current-content-label-v1"
SOURCE = "Actual SelectorBarItem.Tag and current ContentPresenter.Content object identity"
TEXT_TYPES = {"TextBlock", "RichTextBlock", "NativeLabel"}
PAINT_CONTRACT = "selectorbar-current-paint-surface-v1"
PAINT_SOURCE = "Actual Tag Border or exact NativeShadowPanel.Surface and Border.Child object identities"
PAINT_FIELDS = ("background", "border_color", "border_width", "border_widths", "border_colors",
                "border_styles", "corner_radius", "corner_radii", "background_image", "shadow")


def _positive(box):
    return (isinstance(box, dict)
            and all(type(box.get(key)) in (int, float) and math.isfinite(box[key])
                    for key in ("x", "y", "width", "height"))
            and box["width"] > 0 and box["height"] > 0)


def _chain(node_id, by_id):
    result = []
    while node_id in by_id and node_id not in result:
        result.append(node_id)
        node_id = by_id[node_id].get("parent")
    return result


def _runtime_type_name(full_name):
    # Type.FullName separates a nested CLR type with '+', while the independent
    # raw node records Type.Name. Keep the original FullName in the receipt;
    # this comparison changes neither the observed class nor its ownership.
    return full_name.rsplit(".", 1)[-1].rsplit("+", 1)[-1]


def selector_content_labels(raw):
    """Validate current object bindings against the unprojected XAML tree."""
    by_id = {node.get("id"): node for node in raw}
    owners, audits, issues = {}, {}, []
    for owner in raw:
        evidence = owner.get("selector_content_evidence")
        if evidence is None or owner.get("hidden_reason"):
            continue  # Historical captures do not acquire a synthetic receipt.
        owner_id = owner["id"]
        audit = {"evidence": copy.deepcopy(evidence), "status": "incomplete"}
        audits[owner_id] = audit
        reason = None
        if (not isinstance(evidence, dict) or evidence.get("contract") != CONTRACT
                or evidence.get("source") != SOURCE or evidence.get("status") != "measured"
                or evidence.get("owner_id") != owner_id or owner.get("type") != "SelectorBarItem"
                or evidence.get("owner_runtime_type") != "Microsoft.UI.Xaml.Controls.SelectorBarItem"
                or evidence.get("errors") != []):
            reason = "Current SelectorBarItem content identity receipt is absent, failed or inconsistent"
        required = ("ui_thread_access", "template_present", "same_subtree_after", "same_tag_after",
                    "same_template_after", "same_presenter_content_after", "tag_in_actual_subtree",
                    "captured_subtree_complete")
        if reason is None and any(evidence.get(key) is not True for key in required):
            reason = "Current template, Tag/Content object or captured subtree was not stable and complete"
        runtime = owner.get("render_type_evidence") or {}
        if reason is None and (runtime.get("is_control") is not True or runtime.get("control_template_present") is not True):
            reason = "Actual Control and current template observations are missing"
        entries = evidence.get("actual_subtree") if isinstance(evidence, dict) else None
        actual_ids = {node_id for node_id in by_id if owner_id in _chain(node_id, by_id)}
        if reason is None:
            if (len(by_id) != len(raw) or not isinstance(entries, list) or not entries
                    or any(not isinstance(entry, dict) for entry in entries)):
                reason = "Current subtree records are missing or ambiguous"
            else:
                entry_ids = [entry.get("id") for entry in entries]
                if (any(not isinstance(eid, str) for eid in entry_ids)
                        or len(set(entry_ids)) != len(entry_ids) or set(entry_ids) != actual_ids):
                    reason = "Captured current subtree does not account for every actual owner descendant"
                else:
                    for entry in entries:
                        node = by_id[entry["id"]]
                        expected_parent = None if node["id"] == owner_id else node.get("parent")
                        if (entry.get("parent_id") != expected_parent
                                or entry.get("captured_parent_matches") is not True
                                or type(entry.get("child_index")) is not int or entry["child_index"] < 0
                                or not isinstance(entry.get("runtime_type"), str)
                                or _runtime_type_name(entry["runtime_type"]) != node.get("type")):
                            reason = "Current visual parent/type observations conflict with the raw XAML tree"
                            break
        tag_id = evidence.get("tag_content_id") if isinstance(evidence, dict) else None
        presenters = evidence.get("presenter_ids") if isinstance(evidence, dict) else None
        if reason is None:
            tag = by_id.get(tag_id) if isinstance(tag_id, str) else None
            if (not isinstance(presenters, list) or len(presenters) != 1
                    or not isinstance(presenters[0], str)
                    or presenters[0] not in actual_ids or by_id[presenters[0]].get("type") != "ContentPresenter"
                    or tag is None or tag_id not in actual_ids
                    or presenters[0] not in _chain(tag_id, by_id)
                    or tag.get("declared_content_owner") != owner_id
                    or tag.get("declared_content_source") != "FrameworkElement.Tag UIElement in the actual visual tree"):
                reason = "Tag is not bound to one current ContentPresenter under this actual owner"
        sources = evidence.get("text_sources") if isinstance(evidence, dict) else None
        if reason is None:
            expected_sources = {eid for eid in actual_ids if by_id[eid].get("type") in TEXT_TYPES}
            if (not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources)
                    or any(not isinstance(source.get("id"), str) for source in sources)
                    or len({source["id"] for source in sources}) != len(sources)
                    or {source["id"] for source in sources} != expected_sources):
                reason = "Current text-object observations are missing, duplicated or incomplete"
            else:
                for source in sources:
                    node = by_id[source["id"]]
                    if (source.get("captured_text_matches") is not True or source.get("text") != node.get("text")
                            or not isinstance(source.get("runtime_type"), str)
                            or _runtime_type_name(source["runtime_type"]) != node.get("type")):
                        reason = "Current text getter does not match its independent raw text source"
                        break
        if reason is None:
            labels = [source for source in sources if source.get("text")]
            if len(labels) != 1:
                reason = "Content does not contain exactly one independently recorded text source"
            else:
                label = by_id[labels[0]["id"]]
                if (tag_id not in _chain(label["id"], by_id) or label.get("hidden_reason")
                        or not _positive(label.get("visible_bounds"))):
                    reason = "The actual text source is hidden, unmeasured or outside the bound content"
                else:
                    audit.update(status="measured", source_id=label["id"], text=label["text"])
                    owners[owner_id] = audit
        if reason:
            audit["reason"] = reason
            issues.append({"id": owner_id, "property": "selector.content_label", "reason": reason})
    return {"owners": owners, "audits": audits, "unmeasured": issues}


def selector_label_candidate(audit, labels, nested_semantics):
    """Only the already-visible actual text owner (or its sole full Run)."""
    if not audit or audit.get("status") != "measured" or nested_semantics or len(labels) != 1:
        return None
    label = labels[0]
    source_id = (label.get("text_run_source") or {}).get("owner", label.get("id"))
    if source_id != audit["source_id"] or label.get("text") != audit["text"]:
        return None
    return label


def selector_paint_surfaces(raw, labels):
    """Own one bound decoration, only at the same measured native box/transform.

    No distance threshold selects a surface. Unknown clips, focus, Composition
    and shadow remain independent obligations in the ordinary projector.
    """
    by_id = {node["id"]: node for node in raw}
    owners, audits, issues = {}, {}, []
    for owner in raw:
        parent = owner.get("selector_content_evidence")
        proof = parent.get("paint_surface") if isinstance(parent, dict) else None
        if proof is None or owner.get("hidden_reason"):
            continue
        owner_id = owner["id"]
        audit = {"status": "incomplete", "evidence": copy.deepcopy(proof)}
        audits[owner_id] = audit
        reason = None
        label = labels["owners"].get(owner_id)
        if (not isinstance(proof, dict) or proof.get("contract") != PAINT_CONTRACT
                or proof.get("source") != PAINT_SOURCE or proof.get("status") != "measured"
                or proof.get("errors") != [] or proof.get("owner_id") != owner_id or label is None):
            reason = "Actual tab surface receipt or its independently validated label binding is incomplete"
        if reason is None and any(proof.get(key) is not True for key in
                                  ("surface_child_is_unique_label", "current_child_parent_matches",
                                   "same_surface_after", "same_child_after")):
            reason = "Actual surface/Border.Child relationship changed or was not observed"
        surface_id = proof.get("surface_id") if isinstance(proof, dict) else None
        surface = by_id.get(surface_id) if isinstance(surface_id, str) else None
        shadow = None
        if reason is None:
            if (surface is None or surface.get("type") != "Border"
                    or proof.get("surface_runtime_type") != "Microsoft.UI.Xaml.Controls.Border"
                    or proof.get("tag_content_id") != parent.get("tag_content_id")
                    or proof.get("label_id") != label["source_id"]
                    or by_id[label["source_id"]].get("parent") != surface_id):
                reason = "Surface or its direct child is not the actual bound Border/unique label"
        if reason is None:
            if proof.get("content_form") == "direct-border":
                if (surface_id != parent.get("tag_content_id")
                        or proof.get("shadow_id") is not None or proof.get("shadow_runtime_type") is not None):
                    reason = "Direct surface is not the actual Tag Border"
            elif proof.get("content_form") == "shadow-surface":
                shadow_id = proof.get("shadow_id")
                shadow = by_id.get(shadow_id) if isinstance(shadow_id, str) else None
                if (shadow is None or shadow_id != parent.get("tag_content_id")
                        or shadow.get("type") != "NativeShadowPanel"
                        or proof.get("shadow_runtime_type") != "Relic.NativeShadowPanel"
                        or surface.get("parent") != shadow_id):
                    reason = "Surface is not the exact current NativeShadowPanel.Surface under Tag"
            else:
                reason = "Unsupported actual tab content form; no generic authored-content paint ownership"
        if reason is None:
            # Do not flatten an additional owner/template background behind a
            # translucent surface. Sibling content is not included or removed.
            path = _chain(surface_id, by_id)
            for ancestor_id in path[1:path.index(owner_id) + 1]:
                ancestor_style = by_id[ancestor_id].get("style") or {}
                background = ancestor_style.get("background")
                border = ancestor_style.get("border_color")
                border_width = ancestor_style.get("border_width")
                if (not isinstance(background, list) or len(background) != 4 or background[3] != 0
                        or ancestor_style.get("background_image") != "none"
                        or not (type(border_width) in (int, float) and math.isfinite(border_width) and border_width == 0
                                or isinstance(border, list) and len(border) == 4 and border[3] == 0)):
                    reason = "Additional or unknown owner/template paint cannot be flattened into the bound surface"
                    break
        if reason is None:
            transform_keys = ("m11", "m12", "m21", "m22", "offset_x", "offset_y")
            transforms = (owner.get("transform"), surface.get("transform"))
            if (surface.get("hidden_reason")
                    or any(not _positive(node.get(key)) for node in (owner, surface) for key in ("bounds", "visible_bounds"))
                    or any(surface[key] != owner[key] for key in ("bounds", "visible_bounds"))
                    or any(node.get("axis_aligned_transform") is not True for node in (owner, surface))
                    or any(not isinstance(transform, dict)
                           or any(type(transform.get(key)) not in (int, float) or not math.isfinite(transform[key])
                                  for key in transform_keys) for transform in transforms)
                    or any(transforms[0][key] != transforms[1][key] for key in transform_keys)
                    or type(owner.get("opacity")) not in (int, float) or not math.isfinite(owner["opacity"])
                    or type(surface.get("opacity")) not in (int, float) or not math.isfinite(surface["opacity"])
                    or surface["opacity"] != owner["opacity"]):
                reason = "Actual surface/owner bounds, transform or effective opacity differ or are unmeasured; no approximate paint merge"
        if reason:
            audit["reason"] = reason
            issues.append({"id": owner_id, "property": "selector.paint_surface", "reason": reason})
            continue
        style = surface.get("style") if isinstance(surface.get("style"), dict) else {}
        audit.update(status="measured", surface_id=surface_id, label_id=label["source_id"],
                     shadow_id=shadow["id"] if shadow else None,
                     style={key: copy.deepcopy(style.get(key)) for key in PAINT_FIELDS},
                     raw_surface=copy.deepcopy(surface), raw_shadow=copy.deepcopy(shadow))
        if shadow is not None:
            # The capture reports real DropShadow parameters, not a certified
            # CSS/raster shadow. The transparent owner default [] is not absence.
            audit["style"]["shadow"] = None
            issues.append({"id": owner_id, "property": "style.shadow",
                           "reason": "Actual bound NativeShadowPanel is retained; live Composition parameters do not establish CSS shadow equivalence",
                           "source_id": shadow["id"]})
        owners[owner_id] = audit
    return {"owners": owners, "audits": audits, "unmeasured": issues}
