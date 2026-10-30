import AppKit

/// Own-paint coverage for the two final, production read-only text classes.
/// A containing SwiftUI control/surface has a separate paint obligation; this
/// receipt must never be promoted from its label to that control's outline.
@MainActor enum TextOutlineCapture {
    static func inspect(_ view: NSTextView, range: NSRange) -> (paint: Any, evidence: [String: Any]) {
        var errors: [String] = []
        let knownView = type(of: view) == ReferenceLabelView.self || type(of: view) == QuoteTextView.self
        let manager = view.textLayoutManager == nil ? view.layoutManager : nil
        let knownManager = manager.map { type(of: $0) == NativeGlyphLayoutManager.self || type(of: $0) == InlineCodeLayoutManager.self } ?? false
        let fontDraw = (manager as? NativeGlyphLayoutManager)?.fontEvidence(for: range, in: view) ?? [:]
        let layer = view.layer
        var evidence: [String: Any] = [
            "source": "mounted final read-only NSTextView own-paint contract and current glyph draw",
            "contract": "relic-read-only-text-own-outline-v1", "scope": "this text span only; excludes parent/control paint",
            "view_identity": String(describing: ObjectIdentifier(view)), "view_class": String(describing: type(of: view)),
            "window_identity": view.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "range": ["location": range.location, "length": range.length],
            "focus_ring_type": view.focusRingType.rawValue, "editable": view.isEditable, "field_editor": view.isFieldEditor,
            "draws_background": view.drawsBackground, "subview_classes": view.subviews.map { String(describing: type(of: $0)) },
            "layout_manager_class": manager.map { String(describing: type(of: $0)) } as Any? ?? NSNull(),
            "glyph_draw_status": fontDraw["status"] ?? NSNull(), "glyph_draw_binding": fontDraw["binding"] ?? NSNull(),
            "absence_proven": false, "presentation_identity_proven": false]
        if !knownView || !knownManager { errors.append("Unknown text view or layout renderer") }
        if view.window?.isVisible != true || view.isHiddenOrHasHiddenAncestor { errors.append("Text is not mounted in a visible window") }
        if view.isEditable || view.isFieldEditor || view.drawsBackground || view.focusRingType != .none {
            errors.append("Native text background/editor/focus drawing is outside the own-paint contract")
        }
        if !view.subviews.isEmpty { errors.append("Text view has additional native child paint") }
        if fontDraw["status"] as? String != "measured-current-draw" { errors.append("No current source-bound glyph draw") }
        if let layer {
            let childCount = layer.sublayers?.count ?? 0
            let animations = layer.animationKeys() ?? []
            evidence["layer"] = ["identity": String(describing: ObjectIdentifier(layer)),
                "class": String(describing: type(of: layer)), "border_width": layer.borderWidth,
                "shadow_opacity": layer.shadowOpacity, "sublayer_count": childCount, "animation_keys": animations,
                "mask_present": layer.mask != nil, "compositing_filter_present": layer.compositingFilter != nil,
                "filter_count": layer.filters?.count ?? 0, "background_filter_count": layer.backgroundFilters?.count ?? 0]
            if layer.borderWidth != 0 || layer.shadowOpacity != 0 || childCount != 0 || !animations.isEmpty ||
                layer.mask != nil || layer.compositingFilter != nil || !(layer.filters ?? []).isEmpty || !(layer.backgroundFilters ?? []).isEmpty {
                errors.append("Additional layer paint/effects are outside the text renderer contract")
            }
            if let presented = layer.presentation() {
                evidence["presentation_layer"] = ["border_width": presented.borderWidth, "shadow_opacity": presented.shadowOpacity,
                    "sublayer_count": presented.sublayers?.count ?? 0, "mask_present": presented.mask != nil,
                    "compositing_filter_present": presented.compositingFilter != nil,
                    "filter_count": presented.filters?.count ?? 0, "background_filter_count": presented.backgroundFilters?.count ?? 0]
                if presented.borderWidth != 0 || presented.shadowOpacity != 0 || !(presented.sublayers ?? []).isEmpty ||
                    presented.mask != nil || presented.compositingFilter != nil || !(presented.filters ?? []).isEmpty || !(presented.backgroundFilters ?? []).isEmpty {
                    errors.append("Presentation layer retains additional paint/effects")
                }
            } else { errors.append("Backing layer has no current presentation observation") }
        } else { evidence["layer"] = NSNull() }
        if let storage = view.textStorage, range.location >= 0, range.length > 0,
           range.location <= storage.length, range.length <= storage.length - range.location {
            var attributes: [[String: Any]] = []
            storage.enumerateAttributes(in: range) { value, subrange, _ in
                let stroke = (value[.strokeWidth] as? NSNumber)?.doubleValue
                attributes.append(["range": ["location": subrange.location, "length": subrange.length],
                    "stroke_width": stroke as Any? ?? NSNull(), "shadow_present": value[.shadow] != nil,
                    "attachment_present": value[.attachment] != nil])
                if value[.shadow] != nil || value[.attachment] != nil || stroke.map({ $0 != 0 }) == true || value[.strokeWidth] != nil && stroke == nil {
                    errors.append("Text span contains unmeasured attachment, shadow or stroke paint")
                }
            }
            evidence["attribute_paint"] = attributes
        } else { errors.append("Text source range is not current") }
        evidence["errors"] = errors
        evidence["absence_proven"] = errors.isEmpty
        return (errors.isEmpty ? "none" as Any : NSNull(), evidence)
    }
}
