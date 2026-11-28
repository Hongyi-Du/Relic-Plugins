import AppKit

/// Observe the original cacheDisplay call. A matched buffer proves where that
/// draw occurred; it does not prove occlusion, layer order or final PNG coverage.
@MainActor extension CaptureRaster {
    static func cache(_ view: NSView, into bitmap: NSBitmapImageRep) -> [String: Any] {
        let fills = view.window.map { NativeSurfaceFill.mountedViews(in: $0) } ?? []
        let before = Dictionary(uniqueKeysWithValues: fills.map {
            (ObjectIdentifier($0), $0.lastDraw?["sequence"] as? Int ?? 0)
        })
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let address = bitmap.bitmapData.map { "0x" + String(UInt(bitPattern: $0), radix: 16) }
        var observations: [[String: Any]] = []
        for fill in fills {
            let actual = fill.observation(), draw = actual["current_draw"] as? [String: Any] ?? [:]
            let context = draw["context_bitmap"] as? [String: Any] ?? [:]
            let previous = before[ObjectIdentifier(fill)] ?? 0
            let sequence = draw["sequence"] as? Int
            let advanced = sequence.map { $0 > previous } ?? false
            let identical = address != nil && context["data_address"] as? String == address
            observations.append(["actual_fill": actual, "sequence_before_cache": previous,
                "sequence_after_cache": sequence as Any? ?? NSNull(), "new_draw_during_cache": advanced,
                "same_destination_buffer": identical,
                "draw_destination_bound": advanced && identical,
                "final_png_attribution_proven": false, "occlusion_proven": false])
        }
        var result = evidence(bitmap)
        result["source"] = "actual NSView.cacheDisplay invocation and destination buffer"
        result["data_address"] = address as Any? ?? NSNull()
        result["view_identity"] = String(describing: ObjectIdentifier(view))
        result["window_identity"] = view.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()
        result["view_bounds"] = ElementCapture.box(view.bounds)
        result["native_fill_destinations"] = observations
        return result
    }
}
