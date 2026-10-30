import AppKit

/// Only the final native icon view's own outline. The path stroke is the glyph;
/// any containing button, focus owner or ancestor retains its separate duty.
@MainActor enum IconOutlineCapture {
    static func inspect(_ view: ElementPaintProbe.PaintView) -> (paint: Any, evidence: [String: Any]) {
        let draw = view.currentDraw()
        var errors: [String] = []
        var evidence: [String: Any] = ["source": "final native PaintView own-paint contract and current CGContext stroke",
            "contract": "relic-native-icon-own-outline-v1", "scope": "this icon only; excludes parent/control paint",
            "view_identity": String(describing: ObjectIdentifier(view)), "view_class": String(describing: type(of: view)),
            "draw_sequence": draw?["sequence"] ?? NSNull(), "draw_revision": draw?["revision"] ?? NSNull(),
            "window_identity": view.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "focus_ring_type": view.focusRingType.rawValue, "subview_count": view.subviews.count,
            "absence_proven": false, "presentation_identity_proven": false]
        if draw == nil { errors.append("No current mounted source-bound icon stroke") }
        if view.focusRingType != .none || !view.subviews.isEmpty { errors.append("Additional native focus or child paint") }
        func inspectLayer(_ layer: CALayer) -> [String: Any] {
            let children = layer.sublayers ?? []
            let animations = layer.animationKeys() ?? []
            if layer.borderWidth != 0 || layer.shadowOpacity != 0 || !children.isEmpty || !animations.isEmpty ||
                layer.mask != nil || layer.compositingFilter != nil || !(layer.filters ?? []).isEmpty || !(layer.backgroundFilters ?? []).isEmpty {
                errors.append("Additional icon layer paint/effects are outside the renderer contract")
            }
            return ["identity": String(describing: ObjectIdentifier(layer)), "class": String(describing: type(of: layer)),
                "border_width": layer.borderWidth, "shadow_opacity": layer.shadowOpacity,
                "sublayer_count": children.count, "sublayer_classes": children.map { String(describing: type(of: $0)) },
                "animation_keys": animations, "mask_present": layer.mask != nil,
                "compositing_filter_present": layer.compositingFilter != nil,
                "filter_count": layer.filters?.count ?? 0, "background_filter_count": layer.backgroundFilters?.count ?? 0]
        }
        if let layer = view.layer {
            evidence["layer"] = inspectLayer(layer)
            if let presentation = layer.presentation() { evidence["presentation_layer"] = inspectLayer(presentation) }
            else { errors.append("Icon backing layer has no current presentation observation") }
        } else { evidence["layer"] = NSNull() }
        evidence["errors"] = errors; evidence["absence_proven"] = errors.isEmpty
        return (errors.isEmpty ? "none" as Any : NSNull(), evidence)
    }
}
