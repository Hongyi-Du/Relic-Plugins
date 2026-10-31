import AppKit
import CoreImage

/// Actual model/presentation layer ancestry for the captured NSWindow. This
/// records compositing inputs; it does not declare a layer's contents known or
/// erase AX elements merely because their rectangles overlap a popup.
@MainActor enum NativeLayerOrder {
    static func identifier(_ layer: CALayer) -> String { String(describing: ObjectIdentifier(layer)) }

    static func observation(_ layer: CALayer) -> [String: Any] {
        func filter(_ value: Any?) -> Any {
            guard let value else { return NSNull() }
            var result: [String: Any] = ["class": String(describing: type(of: value)),
                "semantics_proven": false]
            if let name = value as? String { result["native_name"] = name }
            if let actual = value as? CIFilter {
                result["native_name"] = actual.name
                result["input_keys"] = actual.inputKeys
            }
            return result
        }
        func matrix(_ value: CATransform3D) -> [CGFloat] {
            [value.m11, value.m12, value.m13, value.m14, value.m21, value.m22, value.m23, value.m24,
             value.m31, value.m32, value.m33, value.m34, value.m41, value.m42, value.m43, value.m44]
        }
        func properties(_ value: CALayer) -> [String: Any] {
            ["bounds": ElementCapture.box(value.bounds), "position": [value.position.x, value.position.y],
             "anchor": [value.anchorPoint.x, value.anchorPoint.y], "z_position": value.zPosition,
             "anchor_z": value.anchorPointZ, "transform": matrix(value.transform),
             "sublayer_transform": matrix(value.sublayerTransform), "opacity": value.opacity,
             "hidden": value.isHidden, "masks_to_bounds": value.masksToBounds,
             "geometry_flipped": value.isGeometryFlipped, "double_sided": value.isDoubleSided,
             "mask_present": value.mask != nil, "compositing_filter_present": value.compositingFilter != nil,
             "compositing_filter": filter(value.compositingFilter),
             "filters": (value.filters ?? []).map { filter($0) },
             "background_filters": (value.backgroundFilters ?? []).map { filter($0) },
             "filter_count": value.filters?.count ?? 0, "background_filter_count": value.backgroundFilters?.count ?? 0,
             "should_rasterize": value.shouldRasterize, "contents_present": value.contents != nil,
             "contents_scale": value.contentsScale, "contents_gravity": value.contentsGravity.rawValue]
        }
        let parent = layer.superlayer
        let siblings = parent?.sublayers ?? []
        return ["identity": identifier(layer), "class": String(describing: type(of: layer)),
            "parent": parent.map(identifier) as Any? ?? NSNull(),
            "sibling_index": siblings.firstIndex(where: { $0 === layer }) as Any? ?? NSNull(),
            "ordered_children": (layer.sublayers ?? []).map(identifier),
            "model": properties(layer), "presentation": layer.presentation().map(properties) as Any? ?? NSNull(),
            "animation_keys": layer.animationKeys() ?? [], "drawing_duty_proven": false]
    }

    static func capture(in window: NSWindow) -> [String: Any] {
        var layers: [String: [String: Any]] = [:], views: [String: Any] = [:]
        // Keep the actual roots of the measured views. Do not substitute a
        // synthetic shared ancestor when AppKit has multiple layer trees.
        var roots = Set<String>()
        func visitLayer(_ layer: CALayer) {
            let id = identifier(layer)
            guard layers[id] == nil else { return }
            layers[id] = observation(layer)
            for child in layer.sublayers ?? [] { visitLayer(child) }
        }
        func visitView(_ view: NSView) {
            let id = String(describing: ObjectIdentifier(view))
            if let layer = view.layer {
                views[id] = identifier(layer)
                var root = layer
                while let parent = root.superlayer { root = parent }
                roots.insert(identifier(root)); visitLayer(root)
            } else { views[id] = NSNull() }
            for child in view.subviews { visitView(child) }
        }
        if let content = window.contentView { visitView(content) }
        return ["source": "actual NSView.layer and CALayer model/presentation ancestry",
            "window_identity": String(describing: ObjectIdentifier(window)),
            "views": views, "roots": roots.sorted(), "layers": layers,
            "occlusion_proven": false,
            "measurement_limit": "Layer order and transforms do not identify private contents, establish draw ownership, or bind pixels to the final screenshot"]
    }
}
