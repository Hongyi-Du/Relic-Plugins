"""Originating-toggle state for an explicitly retained decorative thumb.

The reference's checkbox ::after is emitted using its originating checkbox's
live state. This module supplies the same quantity only for the production
NativeOverviewToggle thumb. It does not infer a state owner for Button text,
change raw states, or establish geometry/paint/frame coverage.
"""
from collections import Counter
from copy import deepcopy

from windows_automation_identity import OWNER_SOURCE, bind_automation_identities, held_observer_binding


SOURCE = "Actual NativeOverviewToggle retained production parts and live getters"
CONTRACT = "NativeOverviewToggle decorative thumb; sealed production owner; no independent thumb input handler"
FIELDS = ("enabled", "checked", "focused", "indeterminate")


def windows_toggle_parts(raw_nodes, uia):
    """Return measured thumb state overlays and explicit unresolved contracts.

    `parts[id].state` has only the four originating-control fields. The caller
    must retain the leaf's raw state and all existing errors and must not use
    this receipt to own/remove the thumb, its paint, or other descendants.
    """
    result = {"source": SOURCE, "parts": {}, "unresolved": [],
              "quantity": "Originating toggle state of its actual decorative thumb",
              "does_not_resolve": "Final-frame paint, geometry, hover, other parts and Button text remain independent"}
    counts = Counter(n.get("id") for n in raw_nodes if isinstance(n, dict))
    by_id = {n["id"]: n for n in raw_nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    binding = bind_automation_identities(raw_nodes, uia)
    pairs = {p["xaml_id"]: p for p in binding["pairs"]}
    uia_by_id = {n["id"]: n for n in uia.get("raw_nodes", []) if isinstance(n, dict) and isinstance(n.get("id"), str)}
    candidates = [n for n in raw_nodes if isinstance(n, dict)
                  and (n.get("type") == "NativeOverviewToggle" or n.get("native_toggle_parts") is not None)]
    claims = Counter(n.get("native_toggle_parts", {}).get("thumb_id") for n in candidates
                     if isinstance(n.get("native_toggle_parts"), dict))
    for owner in candidates:
        owner_id = owner.get("id")
        receipt = owner.get("native_toggle_parts")
        audit = {"owner_id": owner_id, "raw_contract": deepcopy(receipt),
                 "owner_raw_state": deepcopy(owner.get("state")), "owner_identity": deepcopy(pairs.get(owner_id))}

        def reject(reason):
            result["unresolved"].append({"owner_id": owner_id, "reason": reason, "evidence": audit})

        if (not isinstance(receipt, dict) or receipt.get("source") != SOURCE
                or type(receipt.get("version")) is not int or receipt["version"] != 1
                or receipt.get("status") != "measured" or receipt.get("errors") != []
                or receipt.get("part_contract") != CONTRACT
                or owner.get("type") != "NativeOverviewToggle"
                or receipt.get("owner_runtime_type") != "Relic.NativeOverviewToggle"
                or receipt.get("owner_id") != owner_id):
            reject("No measured exact production toggle-part contract")
            continue
        roles = {"owner": owner_id, **{key: receipt.get(key + "_id") for key in ("track", "shadow", "thumb")}}
        if (any(not isinstance(value, str) or not value or counts[value] != 1 for value in roles.values())
                or len(set(roles.values())) != 4 or claims[roles["thumb"]] != 1):
            reject("Part ids are absent, duplicated, shared, or point outside the actual visual walk")
            continue
        track, shadow, thumb = (by_id[roles[key]] for key in ("track", "shadow", "thumb"))
        audit.update(part_ids=roles, thumb_raw_state=deepcopy(thumb.get("state")))
        if (track.get("type") != "Border" or shadow.get("type") != "NativeShadowPanel" or thumb.get("type") != "Border"
                or track.get("declared_content_owner") != owner_id
                or track.get("declared_content_source") != "ContentControl.Content"
                or any(receipt.get(key) is not True for key in (
                    "owner_content_is_track", "track_child_is_shadow", "shadow_surface_is_thumb",
                    "current_parts_same_objects", "reaches_same_owner_object", "all_captured_edges_match", "getters_unchanged"))):
            reject("Retained Content/Child/Surface objects or actual production part types are unproven")
            continue
        edges = receipt.get("actual_ancestor_edges")
        # This production template has one ContentPresenter. It is measured in
        # the actual chain; no name, coordinate, or reference scene is consulted.
        chain = [roles["thumb"], roles["shadow"], roles["track"]]
        presenter_id = track.get("parent")
        chain += [presenter_id, owner_id]
        if (not isinstance(presenter_id, str) or counts[presenter_id] != 1
                or by_id[presenter_id].get("type") != "ContentPresenter"
                or len(set(chain)) != len(chain) or not isinstance(edges, list) or len(edges) != len(chain) - 1):
            reject("Actual thumb-to-owner template chain is missing, ambiguous, or has an independent intermediate object")
            continue
        chain_valid = True
        for index, (child_id, parent_id) in enumerate(zip(chain, chain[1:])):
            edge = edges[index]
            if (not isinstance(edge, dict) or edge.get("child_id") != child_id or edge.get("parent_id") != parent_id
                    or edge.get("actual_parent_in_visual_walk") is not True or edge.get("captured_parent_matches") is not True
                    or by_id[child_id].get("parent") != parent_id):
                chain_valid = False
        if not chain_valid:
            reject("Live parent edges do not agree with the retained raw visual tree")
            continue
        independent = []
        for part_id in chain[:-1]:
            part = by_id[part_id]
            interaction = part.get("interaction_evidence")
            if (not isinstance(interaction, dict) or interaction.get("is_control") is not False
                    or interaction.get("is_tab_stop") is not None):
                independent.append(part_id)
            part_pair = pairs.get(part_id)
            if part_pair:
                provider = uia_by_id.get(part_pair["uia_id"], {})
                # A separately exposed provider must affirmatively report no
                # focus or action; missing pattern evidence is not absence.
                if (provider.get("state", {}).get("focusable") is not False
                        or provider.get("supported_patterns") != []):
                    independent.append(part_id)
            else:
                peer = part.get("automation_identity_evidence")
                if (not isinstance(peer, dict) or peer.get("source") != OWNER_SOURCE
                        or peer.get("owner_id") != part_id or peer.get("status") != "no-peer"
                        or peer.get("peer_is_null") is not True or peer.get("metadata_modified") is not False
                        or type(peer.get("process_id")) is not int or peer["process_id"] != uia.get("pid")
                        or held_observer_binding(peer, uia) is not None):
                    independent.append(part_id)
        if (independent or thumb.get("interaction_evidence", {}).get("is_hit_test_visible") is not False
                or any(n.get("parent") == roles["thumb"] for n in raw_nodes if isinstance(n, dict))):
            reject("The thumb or its path has independent input, unknown interaction, or a child subtree")
            continue
        before, after = receipt.get("before"), receipt.get("after")
        audit.update(getters_before=deepcopy(before), getters_after=deepcopy(after))
        if (not isinstance(before, dict) or not isinstance(after, dict) or before != after
                or any(type(snapshot.get(key)) is not bool for snapshot in (before, after) for key in (
                    "is_checked", "is_three_state", "is_enabled", "is_loaded", "thumb_is_hit_test_visible", "thumb_child_is_null"))
                or before["is_three_state"] is not False or before["is_loaded"] is not True
                or before["thumb_is_hit_test_visible"] is not False or before["thumb_child_is_null"] is not True
                or before.get("focus_state") not in {"Unfocused", "Pointer", "Keyboard", "Programmatic"}):
            reject("Current getters are incomplete, changed, tri-state, detached, or allow independent thumb input")
            continue
        pair = pairs.get(owner_id)
        provider = uia_by_id.get(pair["uia_id"], {}) if pair else {}
        provider_state = provider.get("state")
        audit["owner_uia_state"] = deepcopy(provider_state)
        if (not pair or not isinstance(provider_state, dict)
                or provider.get("control_type") != "ControlType.Button"
                or not isinstance(provider.get("supported_patterns"), list)
                or "TogglePatternIdentifiers.Pattern" not in (provider.get("supported_patterns") or [])):
            reject("No unique held full-RuntimeId binding to an actual UIA TogglePattern owner")
            continue
        state = {"enabled": before["is_enabled"], "checked": before["is_checked"],
                 "focused": before["focus_state"] != "Unfocused", "indeterminate": False}
        owner_state = owner.get("state", {})
        if (not isinstance(owner_state, dict)
                or any(type(owner_state.get(key)) is not bool or type(provider_state.get(key)) is not bool
                       or owner_state[key] != value or provider_state[key] != value for key, value in state.items())):
            reject("Actual owner getters, raw XAML state and independently bound UIA state disagree or are unknown")
            continue
        if provider_state.get("toggle") != ("On" if state["checked"] else "Off"):
            reject("UIA ToggleState is unavailable or contradicts the actual two-state owner")
            continue
        part_state = thumb.get("state", {})
        if not isinstance(part_state, dict) or any(key not in part_state or part_state[key] is not None for key in FIELDS):
            reject("Thumb already reports independent or conflicting interaction state; it is not overwritten")
            continue
        audit.update(status="measured-originating-toggle-state", fields=list(FIELDS), actual_ancestor_edges=deepcopy(edges),
                     state_source="Live NativeOverviewToggle getters corroborated by its uniquely bound UIA TogglePattern",
                     raw_part_state_preserved=True, final_frame_contribution=None)
        result["parts"][roles["thumb"]] = {"state": state, "evidence": audit}
    return result
