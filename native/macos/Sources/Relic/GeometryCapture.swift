import AppKit
import RelicCore

/// Read the mounted native tree without asking AX or TextKit to lay it out.
/// The phase receipt distinguishes a changed view/scroll origin from a bad
/// coordinate projection. It never supplies replacement element rectangles.
@MainActor final class GeometryCaptureSession {
    private let path: URL
    private var baseline: [String: [String: Any]]?
    private var receipt: [String: Any] = ["provider": "passive NSView/NSClipView geometry", "phases": [] as [[String: Any]]]
    init(path: URL) { self.path = path }

    static func snapshot(_ root: NSView) -> [String: [String: Any]] {
        var result: [String: [String: Any]] = [:]
        func visit(_ view: NSView) {
            let id = String(describing: ObjectIdentifier(view))
            var item: [String: Any] = ["class": String(describing: type(of: view)),
                "frame": ElementCapture.box(view.frame), "bounds": ElementCapture.box(view.bounds),
                "flipped": view.isFlipped, "hidden": view.isHiddenOrHasHiddenAncestor,
                "visible_rect": ElementCapture.box(view.visibleRect),
                "parent": view.superview.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()]
            if let window = view.window { item["screen_bounds"] = ElementCapture.box(window.convertToScreen(view.convert(view.bounds, to: nil))) }
            if let text = view as? NSTextView { item["text"] = text.string }
            if let layer = view.layer {
                item["layer_bounds"] = ElementCapture.box(layer.bounds)
                item["layer_position"] = ["x": layer.position.x, "y": layer.position.y]
                item["layer_anchor"] = ["x": layer.anchorPoint.x, "y": layer.anchorPoint.y]
                if let displayed = layer.presentation() {
                    item["presentation_bounds"] = ElementCapture.box(displayed.bounds)
                    item["presentation_position"] = ["x": displayed.position.x, "y": displayed.position.y]
                }
            }
            result[id] = item
            for child in view.subviews { visit(child) }
        }
        visit(root); return result
    }

    func observe(_ phase: String, window: NSWindow) throws {
        guard let content = window.contentView else { throw RelicError.message("Native geometry capture lost its window") }
        let current = Self.snapshot(content)
        var observation: [String: Any] = ["phase": phase, "host_uptime_seconds": ProcessInfo.processInfo.systemUptime]
        if let baseline {
            let changed = current.keys.filter { key in
                guard let old = baseline[key], let value = current[key] else { return true }
                return !NSDictionary(dictionary: old).isEqual(to: value)
            }.sorted()
            let removed = baseline.keys.filter { current[$0] == nil }.sorted()
            observation["changed"] = changed.map { ["identity": $0, "before": baseline[$0] as Any? ?? NSNull(), "after": current[$0]!] }
            observation["removed"] = removed
            append(observation)
            guard changed.isEmpty && removed.isEmpty else {
                throw RelicError.message("Mounted native geometry changed at " + phase + ": " + String(changed.count) + " changed, " + String(removed.count) + " removed views")
            }
        } else {
            baseline = current; observation["views"] = current; append(observation)
        }
    }
    private func append(_ observation: [String: Any]) {
        var phases = receipt["phases"] as? [[String: Any]] ?? []
        phases.append(observation); receipt["phases"] = phases
        if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]) { try? data.write(to: path) }
    }
}
