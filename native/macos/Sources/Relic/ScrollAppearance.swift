import SwiftUI
import AppKit
import RelicAX

// The reference's styled scrollbars reserve a 10px gutter on overflow. Preserve
// native scrolling/AX/keyboard behavior and let NSScrollView tile that actual
// custom-width scroller, rather than covering content with an overlay scrollbar.
struct ScrollAppearance: NSViewRepresentable {
    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ view: Probe, context: Context) { view.needsLayout = true }
    final class Probe: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); needsLayout = true }
        override func layout() {
            super.layout()
            guard let root = window?.contentView else { return }
            func apply(_ view: NSView) {
                if let scroll = view as? NSScrollView {
                    if VisualCapture.enabled { ScrollGeometryTrace.observe(scroll, phase: "before-scroller-configuration") }
                    if scroll.hasVerticalScroller && !(scroll.verticalScroller is ReferenceScroller) { scroll.verticalScroller = ReferenceScroller() }
                    if scroll.hasHorizontalScroller && !(scroll.horizontalScroller is ReferenceScroller) { scroll.horizontalScroller = ReferenceScroller() }
                    if scroll.scrollerStyle != .legacy { scroll.scrollerStyle = .legacy }
                    if !scroll.autohidesScrollers { scroll.autohidesScrollers = true }
                    if VisualCapture.enabled { ScrollGeometryTrace.observe(scroll, phase: "after-scroller-configuration") }
                }
                for child in view.subviews { apply(child) }
            }
            apply(root)
        }
    }
}

final class ReferenceScroller: NSScroller {
    private var over = false
    private(set) var lastPaint: [String: Any]?
    override class var isCompatibleWithOverlayScrollers: Bool { true }
    override func accessibilityChildren() -> [Any]? {
        // This scroller draws one thumb. NSScroller's legacy arrow/page-button
        // providers are disabled and have no corresponding painted buttons.
        // Expose the actual native thumb; parent scrolling actions stay native.
        super.accessibilityChildren()?.filter { RelicAXRead($0)["role"] as? String == "AXValueIndicator" }
    }
    override class func scrollerWidth(for controlSize: NSControl.ControlSize, scrollerStyle: NSScroller.Style) -> CGFloat { 10 }
    var paintedKnob: NSRect {
        let knob = rect(for: .knob)
        if bounds.height > bounds.width { return NSRect(x: bounds.maxX - 7, y: knob.minY + 3, width: 4, height: max(0, knob.height - 6)) }
        return NSRect(x: knob.minX + 3, y: bounds.maxY - 7, width: max(0, knob.width - 6), height: 4)
    }
    override func drawKnob() {
        guard knobProportion < 1 else {
            if VisualCapture.enabled { lastPaint = ["provider": "production ReferenceScroller.drawKnob", "painted": false, "knob_proportion": knobProportion] }
            return
        }
        let fill = NSColor(RelicStyle.muted).withAlphaComponent(over ? 0.55 : 0.35)
        fill.setFill()
        NSBezierPath(roundedRect: paintedKnob, xRadius: 2, yRadius: 2).fill()
        if VisualCapture.enabled {
            lastPaint = ["provider": "production ReferenceScroller.drawKnob", "painted": true,
                "track_local_bounds": ElementCapture.box(bounds), "knob_local_bounds": ElementCapture.box(paintedKnob),
                "knob_hit_bounds": ElementCapture.box(rect(for: .knob)), "fill": ElementCapture.rgba(fill),
                "corner_radius": 2, "orientation": bounds.height > bounds.width ? "vertical" : "horizontal",
                "value": doubleValue, "knob_proportion": knobProportion, "hovered": over,
                "clip_local_bounds": ElementCapture.box(visibleRect), "draw_returned": true]
        }
    }
    override func draw(_ dirtyRect: NSRect) { drawKnob() }
    override func drawKnobSlot(in slotRect: NSRect, highlight flag: Bool) {}
    override func updateTrackingAreas() {
        for area in trackingAreas { removeTrackingArea(area) }
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.inVisibleRect, .activeAlways, .mouseEnteredAndExited, .mouseMoved], owner: self))
        super.updateTrackingAreas()
    }
    private func updateHover(_ event: NSEvent) {
        let hovered = rect(for: .knob).intersection(bounds).contains(convert(event.locationInWindow, from: nil))
        if hovered != over { over = hovered; needsDisplay = true }
    }
    override func mouseEntered(with event: NSEvent) { updateHover(event) }
    override func mouseMoved(with event: NSEvent) { updateHover(event) }
    override func mouseExited(with event: NSEvent) { over = false; needsDisplay = true }
}
