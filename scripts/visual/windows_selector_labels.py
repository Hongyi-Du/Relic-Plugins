"""Read actual SelectorBarItem Tag/Content identity; never infer from tab text.

This contract only owns one text source. Authored backgrounds, shadows, icons,
independent controls and all raw measurement failures retain their own records.
"""
import copy
import math


CONTRACT = "selectorbar-current-content-label-v1"
SOURCE = "Actual SelectorBarItem.Tag and current ContentPresenter.Content object identity"
TEXT_TYPES = {"TextBlock", "RichTextBlock", "NativeLabel"}


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
                                or entry["runtime_type"].rsplit(".", 1)[-1] != node.get("type")):
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
                            or source["runtime_type"].rsplit(".", 1)[-1] != node.get("type")):
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
