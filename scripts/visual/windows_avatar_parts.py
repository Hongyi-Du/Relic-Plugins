"""Own only retained production avatar decorations, without changing raw paint.

This module does not infer membership from matching coordinates, colors, text,
or a generic ancestor PersonPicture. An outline remains an outline: its actual
stroke evidence survives, and an unmeasured contour/offset remains unresolved.
"""
from collections import Counter
from copy import deepcopy
import math

from windows_automation_identity import OWNER_SOURCE, bind_automation_identities, held_observer_binding


SOURCE = "Actual retained NativeAvatarPicture production parts and visual parent identities"


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def windows_avatar_parts(raw_nodes, uia):
    """Return explicit decoration ownership and actual style/box source ids.

    Consumers must keep all raw nodes/evidence and their measurement failures.
    Only `owned_ids` may be grouped into the one avatar. Labels, images, status
    dots, cabinet rings and any other independent child are never owned here.
    No canonical name, text, interaction state, glyph, or default paint is made.
    """
    result = {"source": SOURCE, "owners": {}, "unresolved": [], "unmeasured": []}
    nodes = [node for node in raw_nodes if isinstance(node, dict)]
    counts = Counter(node.get("id") for node in nodes)
    by_id = {node["id"]: node for node in nodes if isinstance(node.get("id"), str)}
    binding = bind_automation_identities(raw_nodes, uia)
    pairs = {pair["xaml_id"]: pair for pair in binding["pairs"]}
    providers = {node["id"]: node for node in uia.get("raw_nodes", [])
                 if isinstance(node, dict) and isinstance(node.get("id"), str)}
    candidates = [node for node in nodes if node.get("native_avatar_parts") is not None]
    claims = Counter(part.get("id") for owner in candidates
                     if isinstance(owner.get("native_avatar_parts"), dict)
                     and isinstance(owner["native_avatar_parts"].get("parts"), list)
                     for part in owner["native_avatar_parts"].get("parts", [])
                     if isinstance(part, dict) and isinstance(part.get("id"), str)
                     and part.get("role") in ("outline", "frame"))

    def passive(part_id):
        part = by_id[part_id]
        interaction = part.get("interaction_evidence")
        if (not isinstance(interaction, dict) or interaction.get("is_control") is not False
                or interaction.get("is_tab_stop") is not None):
            return False
        pair = pairs.get(part_id)
        if pair:
            provider = providers.get(pair["uia_id"], {})
            return provider.get("state", {}).get("focusable") is False and provider.get("supported_patterns") == []
        peer = part.get("automation_identity_evidence")
        return (isinstance(peer, dict) and peer.get("source") == OWNER_SOURCE
                and peer.get("owner_id") == part_id and peer.get("status") == "no-peer"
                and peer.get("peer_is_null") is True and peer.get("metadata_modified") is False
                and type(peer.get("process_id")) is int and peer["process_id"] == uia.get("pid")
                and held_observer_binding(peer, uia) is None)

    for owner in candidates:
        owner_id = owner.get("id")
        receipt = owner["native_avatar_parts"]
        audit = {"raw_contract": deepcopy(receipt), "owner_identity": deepcopy(pairs.get(owner_id)),
                 "raw_owner_name": owner.get("accessible_name"), "final_pixel_equivalence": None}

        def reject(reason):
            result["unresolved"].append({"owner_id": owner_id, "reason": reason, "evidence": audit})

        if (not isinstance(receipt, dict) or receipt.get("source") != SOURCE
                or type(receipt.get("version")) is not int or receipt["version"] != 1
                or receipt.get("status") != "measured" or receipt.get("errors") != []
                or receipt.get("owner_id") != owner_id or counts[owner_id] != 1
                or owner.get("type") != "NativeAvatarPicture"
                or receipt.get("owner_runtime_type") != "Relic.NativeAvatarPicture"
                or receipt.get("getters_unchanged") is not True):
            reject("No complete current retained production avatar contract")
            continue
        kind = receipt.get("kind")
        expected = {"organization-outline": {"paint", "surface", "initial", "outline"},
                    "reply-border": {"paint", "frame", "layout"}}.get(kind) if isinstance(kind, str) else None
        rows = receipt.get("parts")
        if (expected is None or not isinstance(rows, list) or len(rows) != len(expected)
                or any(not isinstance(row, dict) or not isinstance(row.get("role"), str) for row in rows)
                or {row.get("role") for row in rows} != expected):
            reject("Unknown or incomplete avatar part roles")
            continue
        parts = {row["role"]: row.get("id") for row in rows}
        if (any(not isinstance(value, str) or counts[value] != 1 for value in parts.values())
                or len(set(parts.values()) | {owner_id}) != len(parts) + 1
                or any(row.get("same_retained_object_in_capture") is not True for row in rows)
                or any(claims[parts[role]] != 1 for role in ("outline", "frame") if role in parts)):
            reject("Avatar parts are missing, duplicated, shared, or are not retained captured objects")
            continue
        expected_types = ({"paint": ("NativeOrganizationAvatarPaint", "Relic.NativeOrganizationAvatarPaint"),
                           "surface": ("Border", "Microsoft.UI.Xaml.Controls.Border"),
                           "initial": ("TextBlock", "Microsoft.UI.Xaml.Controls.TextBlock"),
                           "outline": ("Rectangle", "Microsoft.UI.Xaml.Shapes.Rectangle")}
                          if kind == "organization-outline" else
                          {"frame": ("Border", "Microsoft.UI.Xaml.Controls.Border"),
                           "layout": ("Grid", "Microsoft.UI.Xaml.Controls.Grid")})
        typed = all(by_id[parts[role]].get("type") == types[0]
                    and next(row for row in rows if row["role"] == role).get("runtime_type") == types[1]
                    for role, types in expected_types.items())
        if kind == "reply-border":
            paint = by_id[parts["paint"]]
            typed &= (paint.get("type") in {"Border", "Image"}
                      and next(row for row in rows if row["role"] == "paint").get("runtime_type")
                      == "Microsoft.UI.Xaml.Controls." + paint.get("type", ""))
        before, after = receipt.get("before"), receipt.get("after")
        if (not typed or not isinstance(before, dict) or not isinstance(after, dict) or before != after
                or any(snapshot.get(key) is not True for snapshot in (before, after)
                       for key in ("owner_tag_is_paint", "owner_template_is_retained", "owner_is_loaded"))
                or any(snapshot.get("owner_is_tab_stop") is not False for snapshot in (before, after))):
            reject("Actual production part types, template objects or live getter snapshots disagree")
            continue
        paint_id = parts["paint"]
        presenter_id = by_id[paint_id].get("parent")
        if (not isinstance(presenter_id, str) or counts[presenter_id] != 1
                or by_id[presenter_id].get("type") != "ContentPresenter"):
            reject("Retained paint has no actual one-presenter path to its avatar")
            continue
        expected_edges = {paint_id: presenter_id, presenter_id: owner_id}
        if kind == "organization-outline":
            expected_edges.update({parts["surface"]: paint_id, parts["initial"]: parts["surface"],
                                   parts["outline"]: paint_id})
            valid_parts = (before.get("organization_current_parts") is True
                           and before.get("organization_has_cabinet_ring") is False
                           and before.get("reply_current_parts") is None
                           and before.get("reply_frame_contract_type") is None
                           and type(before.get("reply_frame_count")) is int and before["reply_frame_count"] == 0
                           and {n["id"] for n in nodes if n.get("parent") == paint_id}
                           == {parts["surface"], parts["outline"]}
                           and {n["id"] for n in nodes if n.get("parent") == parts["surface"]} == {parts["initial"]}
                           and not any(n.get("parent") == parts["outline"] for n in nodes))
            passive_ids = [paint_id, presenter_id, parts["surface"], parts["outline"]]
        else:
            expected_edges.update({owner_id: parts["layout"], parts["layout"]: parts["frame"]})
            valid_parts = (before.get("reply_current_parts") is True
                           and before.get("reply_frame_contract_type") == "Relic.NativeReplyAvatarFrame"
                           and type(before.get("reply_frame_count")) is int and before["reply_frame_count"] == 1
                           and before.get("organization_current_parts") is None
                           and before.get("organization_has_cabinet_ring") is None
                           and {n["id"] for n in nodes if n.get("parent") == parts["layout"]} == {owner_id}
                           and {n["id"] for n in nodes if n.get("parent") == parts["frame"]} == {parts["layout"]})
            passive_ids = [presenter_id, parts["layout"], parts["frame"]]
        edges = receipt.get("actual_ancestor_edges")
        if (not valid_parts or not isinstance(edges, list) or len(edges) != len(expected_edges)
                or any(not isinstance(edge, dict) or not isinstance(edge.get("child_id"), str) for edge in edges)
                or len({edge.get("child_id") for edge in edges}) != len(expected_edges)
                or any(edge.get("parent_id") != expected_edges.get(edge.get("child_id"))
                       or edge.get("actual_parent_in_visual_walk") is not True
                       or edge.get("captured_parent_matches") is not True for edge in edges)
                or any(by_id[child].get("parent") != parent for child, parent in expected_edges.items())
                or any(not passive(part_id) for part_id in passive_ids)):
            reject("Live avatar parent/child closure is changed, contains extra content, or has an independent/unknown interaction")
            continue
        pair = pairs.get(owner_id)
        provider = providers.get(pair["uia_id"], {}) if pair else {}
        if (not pair or provider.get("control_type") not in {"ControlType.Text", "ControlType.Image"}
                or provider.get("state", {}).get("focusable") is not False
                or provider.get("supported_patterns") != []):
            reject("Avatar has no unique held full-RuntimeId non-actionable UIA identity")
            continue
        owned_id = parts["outline" if kind == "organization-outline" else "frame"]
        decoration = by_id[owned_id]
        audit.update(kind=kind, raw_decoration=deepcopy(decoration), actual_ancestor_edges=deepcopy(edges),
                     source_part_ids=deepcopy(parts), raw_owner_state=deepcopy(owner.get("state")))
        projected = {"kind": kind, "owned_ids": [owned_id], "bounds_source": owner_id,
                     "border_source": None, "outline_source": None, "outline": None, "evidence": audit}
        style = decoration.get("style") if isinstance(decoration.get("style"), dict) else {}
        if kind == "reply-border":
            projected.update(bounds_source=owned_id, border_source=owned_id)
            # Consumers take these exact border fields from this real outer
            # frame; they do not treat its transparent background as the fill.
            projected["border_style"] = {key: deepcopy(style.get(key))
                for key in ("border_width", "border_widths", "border_color", "border_colors",
                            "border_styles", "corner_radius", "corner_radii")}
        else:
            dashes = style.get("stroke_dash")
            width, color = style.get("stroke_width"), style.get("foreground")
            valid_dashes = isinstance(dashes, list) and all(_finite(value) and value >= 0 for value in dashes)
            projected["outline_source"] = owned_id
            projected["outline"] = {
                "style": ("dashed" if dashes else "solid") if valid_dashes else None,
                "color": deepcopy(color) if isinstance(color, list) and len(color) == 4
                         and all(_finite(value) and 0 <= value <= 255 for value in color) else None,
                "width": width if _finite(width) and width > 0 else None,
                "offset": None, "contour": None,
                "dash": deepcopy(dashes) if valid_dashes else None,
                "dash_offset": style.get("stroke_dash_offset") if _finite(style.get("stroke_dash_offset")) else None,
            }
            for field in ("style", "color", "width", "offset", "contour", "dash", "dash_offset"):
                if projected["outline"][field] is None:
                    result["unmeasured"].append({"id": owner_id, "property": "style.outline." + field,
                        "reason": "Retained actual avatar outline does not measure this quantity; no CSS or reference contour substituted",
                        "source_id": owned_id})
        result["owners"][owner_id] = projected
    return result
