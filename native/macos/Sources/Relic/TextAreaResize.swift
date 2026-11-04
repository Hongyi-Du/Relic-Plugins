import AppKit
import SwiftUI

struct TextAreaResize: NSViewRepresentable {
    @Binding var size: CGSize?
    let identity: String
    let minimumHeight: CGFloat
    func makeNSView(context: Context) -> TextAreaResizeView { let view = TextAreaResizeView(); updateNSView(view, context: context); return view }
    func updateNSView(_ view: TextAreaResizeView, context: Context) {
        view.owner = "relic-composer/" + identity
        view.minimum = CGSize(width: 24, height: minimumHeight)
        view.resize = { size = $0 }
        view.setAccessibilityIdentifier("relic-resize-handle/" + identity)
    }
}

/// AppKit owns hit testing and delivers the real drag sequence. The parent
/// textarea uses the resulting size in its normal layout, including re-centering
/// the dialog. A screen-space delta avoids feedback from that moving parent.
final class TextAreaResizeView: NSView {
    var owner = ""
    var minimum = CGSize(width: 24, height: 36)
    var resize: (CGSize) -> Void = { _ in }
    private var initialPoint: NSPoint?
    private var initialSize = CGSize.zero
    private(set) var events: [[String: Any]] = []
    override var isFlipped: Bool { true }
    var handleRect: NSRect { NSRect(x: max(0, bounds.maxX - 13), y: max(0, bounds.maxY - 13), width: min(13, bounds.width), height: min(13, bounds.height)) }
    override func hitTest(_ point: NSPoint) -> NSView? {
        let local = convert(point, from: superview)
        return !isHiddenOrHasHiddenAncestor && handleRect.contains(local) ? self : nil
    }
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { NSAccessibility.Role(rawValue: "AXGrowArea") }
    override func accessibilityFrame() -> NSRect { window?.convertToScreen(convert(handleRect, to: nil)) ?? .zero }
    override func resetCursorRects() { addCursorRect(handleRect, cursor: .crosshair) }
    override func draw(_ dirtyRect: NSRect) {
        let stroke = NSColor(srgbRed: 0.5, green: 0.5, blue: 0.5, alpha: 1)
        stroke.setStroke()
        let path = NSBezierPath(); path.lineWidth = 1
        for length in [3.0, 6.0, 9.0] {
            path.move(to: NSPoint(x: bounds.maxX - 3 - length, y: bounds.maxY - 3))
            path.line(to: NSPoint(x: bounds.maxX - 3, y: bounds.maxY - 3 - length))
        }
        path.stroke()
    }
    static func resized(_ size: CGSize, from origin: NSPoint, to point: NSPoint, minimum: CGSize) -> CGSize {
        CGSize(width: max(minimum.width, size.width + point.x - origin.x), height: max(minimum.height, size.height + origin.y - point.y))
    }
    private func screenPoint(_ event: NSEvent) -> NSPoint { window?.convertPoint(toScreen: event.locationInWindow) ?? event.locationInWindow }
    private func record(_ event: NSEvent) {
        let point = screenPoint(event)
        events.append(["type": event.type.rawValue, "timestamp": event.timestamp, "screen_point": ["x": point.x, "y": point.y], "window_number": event.windowNumber, "event_number": event.eventNumber, "button": event.buttonNumber])
        if events.count > 32 { events.removeFirst(events.count - 32) }
    }
    override func mouseDown(with event: NSEvent) {
        initialPoint = screenPoint(event); initialSize = bounds.size; events = []; record(event)
    }
    override func mouseDragged(with event: NSEvent) {
        record(event)
        guard let initialPoint else { return }
        resize(Self.resized(initialSize, from: initialPoint, to: screenPoint(event), minimum: minimum))
    }
    override func mouseUp(with event: NSEvent) { record(event); initialPoint = nil }
    func observation() -> [String: Any] {
        ["identity": String(describing: ObjectIdentifier(self)), "owner": owner,
         "control_screen_bounds": window.map { ElementCapture.box($0.convertToScreen(convert(bounds, to: nil))) } as Any? ?? NSNull(),
         "handle_screen_bounds": ElementCapture.box(accessibilityFrame()), "events": events,
         "dragging": initialPoint != nil,
         "paint": ["provider": "TextAreaResizeView.draw", "stroke_color": [127.5, 127.5, 127.5, 255], "stroke_width": 1, "line_lengths": [3,6,9], "inset": 3]]
    }
}
