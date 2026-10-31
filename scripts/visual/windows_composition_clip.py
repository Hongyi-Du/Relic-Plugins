"""Actual backing-Visual clip geometry, independent of SVG/resource identity.

The local XAML clip and Composition clip both survive. Property getters measure
geometry, not the compositor's sampled frame or antialiasing coverage in a PNG.
"""
import copy
import math


SOURCE = "actual ElementCompositionPreview.GetElementVisual(owner).Clip"
RETAINED_SOURCE = "production-retained backing Visual from ClipToolbarLogo"
PREPARED_SOURCE = "diagnostic-prepared backing Visual retained before authoritative capture"
PREPARED_BINDING = "actual IUnknown identities in retained preparation and read-only checkpoints"
PREFIX = "Microsoft.UI.Composition."
IDENTITY3 = [1, 0, 0, 1, 0, 0]
IDENTITY4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def vector(value, count):
    return isinstance(value, list) and len(value) == count and all(number(x) for x in value)


def box(value):
    return isinstance(value, dict) and all(number(value.get(k)) for k in ("x", "y", "width", "height"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_preparation(node, raw):
    """Validate measured setup/readback order without claiming original state."""
    receipt = raw.get("diagnostic_preparation") or {}
    setup, call = receipt.get("setup") or {}, receipt.get("owner_call") or {}
    render = receipt.get("render_preparation") or {}
    require(receipt.get("capture_owner_same_object") is True
            and receipt.get("read_only_authoritative_window") is True
            and receipt.get("production_original_state_observed") is False
            and setup.get("production_original_state_observed") is False
            and raw.get("production_backing_visual_binding_available") is False
            and raw.get("backing_visual_read") is True and "error" not in receipt,
            "Diagnostic preparation is not bound to this owner or is mislabelled as original production state")
    require(isinstance(setup.get("case_id"), str) and bool(setup["case_id"])
            and setup["case_id"] == render.get("case_id")
            and type(setup.get("qpc_frequency")) is int and setup["qpc_frequency"] > 0
            and type(setup.get("owner_count")) is int and setup["owner_count"] > 0
            and type(call.get("index")) is int and 0 <= call["index"] < setup["owner_count"],
            "Prepared clip case, owner index or clock source differs")
    require(all(item.get("may_create") is True and item.get("created_unknown") is True for item in (setup, call))
            and call.get("api") == "ElementCompositionPreview.GetElementVisual(actual owner)"
            and call.get("returned") is True and "error" not in call,
            "Actual potentially mutating preparation call is missing, failed or mislabelled")
    cycle, commit, flush = (render.get(key) or {} for key in ("render_cycle", "request_commit", "dwm_flush"))
    require(render.get("failure") is None and commit.get("source") == "Window.Compositor.RequestCommitAsync"
            and commit.get("completed") is True and flush.get("source") == "DwmFlush"
            and type(flush.get("hresult")) is int and flush["hresult"] >= 0
            and (cycle.get("rendering") or {}).get("source") == "CompositionTarget.Rendering"
            and (cycle.get("rendered") or {}).get("source") == "CompositionTarget.Rendered",
            "Existing render/commit/flush preparation did not complete")
    clocks = [setup.get("started_qpc"), call.get("started_qpc"), call.get("completed_qpc"), setup.get("completed_qpc"),
              cycle.get("redraw_request_started_qpc"), cycle.get("redraw_request_completed_qpc"),
              (cycle.get("rendering") or {}).get("qpc"), (cycle.get("rendered") or {}).get("qpc"),
              commit.get("started_qpc"), commit.get("completed_qpc"), flush.get("started_qpc"), flush.get("completed_qpc")]
    states = []
    for label in ("baseline", "before_desktop_readback", "after_desktop_readback", "before_getters", "after_getters"):
        point = receipt.get(label) or {}
        require("error" not in point and isinstance(point.get("state"), dict), "Prepared clip checkpoint is missing or failed: " + label)
        clocks.extend((point.get("started_qpc"), point.get("completed_qpc")))
        states.append(point["state"])
    require(all(type(clock) is int and clock > 0 for clock in clocks) and clocks == sorted(clocks),
            "Potentially mutating setup or baseline overlaps authoritative readback/getter observations")
    require(all(state == states[0] for state in states), "Actual prepared owner/Visual/clip changed across the observed interval")
    state = states[0]
    for key in ("owner_identity", "root_identity", "visual_identity"):
        identity = call.get(key)
        require(isinstance(identity, str) and identity.startswith("0x") and int(identity[2:], 16) > 0
                and state.get(key) == identity, "Actual prepared COM identity changed or is absent: " + key)
    require(state.get("owner_is_loaded") is True and state.get("owner_unloaded_since_setup") is False
            and state.get("same_xaml_root") is True and state.get("same_retained_owner") is True
            and state.get("owner_local_bounds") == node.get("local_bounds")
            and state.get("owner_to_window") == node.get("transform")
            and state.get("xaml_clip_present") == raw.get("xaml_clip_present")
            and "retained_baseline_clip_identity" in state and "retained_baseline_geometry_identity" in state
            and state.get("clip_identity") == state["retained_baseline_clip_identity"]
            and state.get("geometry_identity") == state["retained_baseline_geometry_identity"]
            and state.get("properties") == raw.get("before") == raw.get("after"),
            "Prepared backing Visual is detached, replaced or differs from actual captured owner/getters")
    if state["properties"].get("clip_present") is False:
        require(state.get("clip_identity") is None and state.get("geometry_identity") is None,
                "Measured absent clip contradicts retained clip/geometry identities")
    elif state["properties"].get("clip_present") is True:
        for key in ("clip_identity", "geometry_identity"):
            if key == "geometry_identity" and not (state["properties"].get("clip") or {}).get("geometry", {}).get("type"):
                continue
            identity = state.get(key)
            require(isinstance(identity, str) and identity.startswith("0x") and int(identity[2:], 16) > 0,
                    "Actual present clip/geometry has no retained COM identity: " + key)
    return {"basis": "diagnostic-prepared", "production_original_state_observed": False,
            "may_create": True, "created_unknown": True,
            "limitations": ["Property reads are not compositor animation samples or final-PNG coverage",
                            "Preparation may have created handoff visuals and installed WinUI listeners"]}


def composition_clip(node):
    """Return a measured geometry audit and gaps; never repair the raw record."""
    raw = node.get("composition_clip_evidence")
    audit = {"owner_id": node.get("id"), "status": "unavailable", "raw": copy.deepcopy(raw),
             "xaml_clip": copy.deepcopy(node.get("clip")), "window_geometry": None,
             "image_corner_radius": None, "presentation_identity_proven": False}
    issues = []

    def fail(reason, property_name="clip.composition"):
        issues.append({"id": node.get("id"), "property": property_name, "reason": reason})

    try:
        require(isinstance(raw, dict) and raw.get("source") in (SOURCE, RETAINED_SOURCE, PREPARED_SOURCE), "Backing Visual clip has no actual-owner receipt")
        require(raw.get("status") == "measured" and raw.get("owner_id") == node.get("id"), "Composition clip collection or owner identity is incomplete")
        require(isinstance(raw.get("owner_runtime_type"), str) and bool(raw["owner_runtime_type"])
                and raw.get("owner_type") == node.get("type"), "Composition clip runtime owner differs from the rendered node")
        require(raw.get("owner_is_loaded") is True, "Composition clip owner is not actually loaded")
        if raw.get("source") == PREPARED_SOURCE:
            audit["observation_basis"] = validate_preparation(node, raw)
        if raw.get("source") == RETAINED_SOURCE:
            retained = raw.get("production_binding")
            require(isinstance(retained, dict)
                    and retained.get("source") == "Actual ClipToolbarLogo assignment and retained owner/root/Visual fields"
                    and raw.get("backing_visual_read") is True
                    and raw.get("production_backing_visual_binding_available") is True,
                    "Production backing Visual has no retained owner assignment receipt")
            require(all(retained.get(key) is True for key in (
                "owner_same_object", "owner_is_current_logo", "same_xaml_root", "owner_is_loaded_after",
                "visual_same_retained_object", "clip_is_installed_production_object",
                "geometry_is_installed_production_object", "read_only")),
                "Production backing Visual/owner/root or installed clip binding changed or is incomplete")
            require(type(retained.get("revision_before")) is int and retained["revision_before"] > 0
                    and type(retained.get("revision_after")) is int
                    and retained["revision_before"] == retained["revision_after"],
                    "Production clip was detached/reassigned or its revision is missing")
        binding = raw.get("binding") or {}
        binding_source = PREPARED_BINDING if raw.get("source") == PREPARED_SOURCE else "actual IUnknown identity comparison; acquired references released in finally"
        require(binding.get("source") == binding_source
                and all(binding.get(k) is True for k in ("visual_same_object_after", "clip_same_object_after", "geometry_same_object_after")),
                "Backing Visual, clip or geometry COM identity changed or is unverified")
        require(raw.get("properties_stable") is True and isinstance(raw.get("before"), dict) and raw["before"] == raw.get("after"),
                "Composition clip properties changed between actual reads")
        require("clip" in node and isinstance(raw.get("xaml_clip_present"), bool)
                and raw["xaml_clip_present"] == (node["clip"] is not None), "Independent UIElement.Clip receipt is absent or inconsistent")
        current = raw["before"]
        if current.get("clip_present") is False:
            require(current.get("clip") is None, "Measured absent backing clip has contradictory clip properties")
            audit["status"] = "measured-absent"
            return audit, issues
        require(current.get("clip_present") is True and isinstance(current.get("clip"), dict), "Backing Visual clip presence is unmeasured")
        visual, clip = current.get("visual") or {}, current["clip"]
        require(clip.get("type") == PREFIX + "CompositionGeometricClip", "Actual backing clip type has no supported geometric projection")
        geometry = clip.get("geometry") or {}
        require(geometry.get("type") == PREFIX + "CompositionRoundedRectangleGeometry", "Actual clip geometry is not a measured rounded rectangle")
        require(vector(geometry.get("size"), 2) and all(x > 0 for x in geometry["size"])
                and vector(geometry.get("offset"), 2) and vector(geometry.get("corner_radius"), 2)
                and all(x >= 0 for x in geometry["corner_radius"]), "Rounded clip size, offset or radius is invalid/unmeasured")
        require(all(number(geometry.get(k)) for k in ("trim_start", "trim_end", "trim_offset"))
                and [geometry[k] for k in ("trim_start", "trim_end", "trim_offset")] == [0, 1, 0], "Trimmed Composition geometry has no closed-contour proof")
        for owner, dimensions, matrix in ((clip, 2, IDENTITY3), (visual, 3, IDENTITY4)):
            require(vector(owner.get("anchor_point"), 2) and owner["anchor_point"] == [0, 0]
                    and vector(owner.get("center_point"), dimensions) and owner["center_point"] == [0] * dimensions
                    and vector(owner.get("scale"), dimensions) and owner["scale"] == [1] * dimensions
                    and number(owner.get("rotation_angle")) and owner["rotation_angle"] == 0
                    and vector(owner.get("transform_matrix"), len(matrix)) and owner["transform_matrix"] == matrix,
                    "Actual clip/backing Visual transform is outside the verified local-coordinate branch")
        require(vector(visual.get("rotation_axis"), 3) and vector(visual.get("offset"), 3) and visual["offset"][2] == 0
                and vector(clip.get("offset"), 2), "Backing Visual/clip spatial properties are incomplete")
        local = raw.get("owner_local_bounds")
        require(box(local) and local == node.get("local_bounds") and local["x"] == 0 and local["y"] == 0
                and local["width"] > 0 and local["height"] > 0 and vector(visual.get("size"), 2)
                and visual["size"] == [local["width"], local["height"]], "Backing Visual size is not bound to the actual XAML owner's local box")
        matrix = raw.get("owner_to_window")
        require(isinstance(matrix, dict) and matrix == node.get("transform")
                and all(number(matrix.get(k)) for k in ("m11", "m12", "m21", "m22", "offset_x", "offset_y")),
                "Actual owner-to-window coordinate mapping is absent or inconsistent")
        require(matrix["m12"] == matrix["m21"] == 0 and matrix["m11"] == matrix["m22"] and matrix["m11"] > 0,
                "Rounded clip needs a positive uniform actual owner-to-window transform")
        scale = matrix["m11"]
        local_clip = {"x": geometry["offset"][0] + clip["offset"][0], "y": geometry["offset"][1] + clip["offset"][1],
                      "width": geometry["size"][0], "height": geometry["size"][1]}
        window = {"x": local_clip["x"] * scale + matrix["offset_x"], "y": local_clip["y"] * scale + matrix["offset_y"],
                  "width": local_clip["width"] * scale, "height": local_clip["height"] * scale}
        radii = [r * scale for r in geometry["corner_radius"]]
        require(box(window) and vector(radii, 2), "Derived actual clip geometry is non-finite")
        audit["window_geometry"] = {"kind": "rounded-rectangle", "bounds": window, "radius_xy": radii,
            "quantity": "Actual stable Composition geometric-clip property contour in window coordinates; not a sampled alpha mask"}
        audit["status"] = "geometry-measured"
        # A cropped or elliptical image clip cannot become a scalar CSS-style radius.
        # Preserve its measured contour without changing the owner's layout box.
        if node.get("type") == "Image" and local_clip == local and window == node.get("bounds") and radii[0] == radii[1]:
            require(radii[0] <= min(window["width"], window["height"]) / 2, "Overlapping rounded clip arcs need independently measured clamp semantics")
            xaml_clip = node["clip"]
            if xaml_clip is not None:
                require(isinstance(xaml_clip, dict) and xaml_clip.get("kind") == "rectangle" and box(xaml_clip.get("bounds")),
                        "The independent XAML clip has unmeasured geometry")
                other = xaml_clip["bounds"]
                require(other["x"] <= window["x"] and other["y"] <= window["y"]
                        and other["x"] + other["width"] >= window["x"] + window["width"]
                        and other["y"] + other["height"] >= window["y"] + window["height"],
                        "The actual XAML clip intersects the rounded Image contour")
            audit["image_corner_radius"] = radii[0]
        fail("Composition property reads do not measure the compositor-sampled clip or its antialiased final-PNG coverage", "clip.presentation")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        fail(str(error))
    return audit, issues


def apply_composition_clip(element, audit):
    """Project only the same Image owner's coextensive measured contour."""
    element.setdefault("evidence", {})["composition_clip"] = copy.deepcopy(audit)
    radius = audit.get("image_corner_radius")
    if audit.get("owner_id") == element.get("id") and element.get("kind") == "image" and number(radius):
        element["style"]["corner_radius"] = radius
        element["style"]["corner_radii"] = [radius] * 4
