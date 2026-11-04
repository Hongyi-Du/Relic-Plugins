import AppKit
import RelicAX

/// Project only the actual custom scroller's draw receipt. AX hit rectangles
/// remain available independently; the thumb is never sized from scroll ratios.
@MainActor enum ScrollbarCapture {
    static func screenBounds(_ scroller: ReferenceScroller, thumb: Bool) -> NSRect? {
        guard let window = scroller.window, let draw = scroller.lastPaint, draw["painted"] as? Bool == true else { return nil }
        let local = ElementCapture.rect(draw[thumb ? "knob_local_bounds" : "track_local_bounds"])
        guard !local.isNull, !local.isEmpty else { return nil }
        return window.convertToScreen(scroller.convert(local, to: nil))
    }
    static func normalized(value: Any?, minimum: Any?, maximum: Any?) -> Double? {
        guard let value = (value as? NSNumber)?.doubleValue,
              let minimum = (minimum as? NSNumber)?.doubleValue, let maximum = (maximum as? NSNumber)?.doubleValue,
              value.isFinite, minimum.isFinite, maximum.isFinite, maximum >= minimum,
              value >= minimum, value <= maximum else { return nil }
        return maximum == minimum ? 0 : (value - minimum) / (maximum - minimum)
    }
    static func apply(to node: inout [String: Any], scroller: ReferenceScroller, thumb: Bool) {
        let provider = RelicAXRead(scroller)
        let position = normalized(value: provider["value"], minimum: provider["minimum"], maximum: provider["maximum"])
        node["native_scrollbar_owner"] = ["identity": String(describing: ObjectIdentifier(scroller)),
            "provider_value": provider["value"] ?? NSNull(), "provider_minimum": provider["minimum"] ?? NSNull(),
            "provider_maximum": provider["maximum"] ?? NSNull(), "control_double_value": scroller.doubleValue,
            "provider_enabled": provider["enabled"] ?? NSNull(), "control_enabled": scroller.isEnabled,
            "normalized_position": position as Any? ?? NSNull(), "part": thumb ? "thumb" : "track",
            "ownership": "AX child belongs to this actual ReferenceScroller; drawKnob paints its drag part"]
        var state = node["state"] as! [String: Any]
        state["enabled"] = scroller.isEnabled
        state["scroll_position"] = position as Any? ?? NSNull()
        state["orientation"] = scroller.lastPaint?["orientation"] ?? NSNull()
        node["state"] = state
        guard let draw = scroller.lastPaint, draw["painted"] as? Bool == true else { return }
        node["native_scrollbar_paint"] = draw
        var style = node["style"] as! [String: Any]
        style.merge(["backgroundColor": thumb ? draw["fill"]! : [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0,
            "borderRadius": thumb ? draw["corner_radius"]! : 0, "border_widths": [0,0,0,0],
            "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4),
            "corner_radii": Array(repeating: thumb ? draw["corner_radius"]! : 0, count: 4),
            "opacity": NativeVisibility.opacity(scroller), "background_image": "none", "shadow": []], uniquingKeysWith: { _, actual in actual })
        node["style"] = style
        node["hovered"] = NSNull()
        if let window = scroller.window {
            let local = scroller.convert(window.convertPoint(fromScreen: NSEvent.mouseLocation), from: nil)
            node["hovered"] = thumb ? draw["hovered"]! : scroller.bounds.contains(local)
        }
    }
}
