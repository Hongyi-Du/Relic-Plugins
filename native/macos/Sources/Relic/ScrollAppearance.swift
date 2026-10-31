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
        private var applying = false
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            NotificationCenter.default.removeObserver(self, name: NSWindow.didUpdateNotification, object: nil)
            if let window {
                NotificationCenter.default.addObserver(self, selector: #selector(windowUpdated(_:)), name: NSWindow.didUpdateNotification, object: window)
            }
            needsLayout = true
        }
        deinit { NotificationCenter.default.removeObserver(self) }
        @objc private func windowUpdated(_ notification: Notification) { applyToWindow() }
        override func layout() {
            super.layout()
            applyToWindow()
        }
        private func applyToWindow() {
            guard !applying, let root = window?.contentView else { return }
            applying = true; defer { applying = false }
            func apply(_ view: NSView) {
                if let scroll = view as? NSScrollView {
                    HiddenScrollIndicators.apply(to: scroll)
                    if VisualCapture.enabled { ScrollGeometryTrace.observe(scroll, phase: "native-scroll-mounted", once: true) }
                    let vertical = scroll.hasVerticalScroller && !(scroll.verticalScroller is ReferenceScroller)
                    let horizontal = scroll.hasHorizontalScroller && !(scroll.horizontalScroller is ReferenceScroller)
                    if vertical || horizontal || scroll.scrollerStyle != .legacy || !scroll.autohidesScrollers {
                        if VisualCapture.enabled { ScrollGeometryTrace.observe(scroll, phase: "before-scroller-configuration") }
                        if vertical { scroll.verticalScroller = ReferenceScroller() }
                        if horizontal { scroll.horizontalScroller = ReferenceScroller() }
                        if scroll.scrollerStyle != .legacy { scroll.scrollerStyle = .legacy }
                        if !scroll.autohidesScrollers { scroll.autohidesScrollers = true }
                        if VisualCapture.enabled { ScrollGeometryTrace.observe(scroll, phase: "after-scroller-configuration") }
                    }
                }
                for child in view.subviews { apply(child) }
            }
            apply(root)
        }
    }
}

/// Explicit production policy for scroll areas whose reference hides its
/// indicators. A native scroller must not reserve a legacy gutter in these
/// areas; the NSScrollView and its document still perform normal scrolling.
struct HiddenScrollIndicators: NSViewRepresentable {
    var horizontal = true
    var vertical = false
    private static let live = NSHashTable<Mount>.weakObjects()
    func makeNSView(context: Context) -> Mount {
        let view = Mount(); Self.live.add(view); updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: Mount, context: Context) {
        view.horizontal = horizontal; view.vertical = vertical; view.apply()
    }
    static func apply(to scroll: NSScrollView) {
        for view in live.allObjects where view.enclosingScrollView === scroll {
            if view.horizontal && scroll.hasHorizontalScroller { scroll.hasHorizontalScroller = false }
            if view.vertical && scroll.hasVerticalScroller { scroll.hasVerticalScroller = false }
        }
    }
    final class Mount: NSView {
        var horizontal = true, vertical = false
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); apply() }
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); apply() }
        override func layout() { super.layout(); apply() }
        func apply() {
            guard let scroll = enclosingScrollView else { return }
            if horizontal && scroll.hasHorizontalScroller { scroll.hasHorizontalScroller = false }
            if vertical && scroll.hasVerticalScroller { scroll.hasVerticalScroller = false }
        }
    }
}

final class ReferenceScroller: NSScroller {
    private var over = false
    private var registeringNativeParts: [Any]?
    private(set) var lastPaint: [String: Any]?
    override class var isCompatibleWithOverlayScrollers: Bool { true }
    override func accessibilityChildren() -> [Any]? {
        // This scroller draws one thumb. NSScroller's legacy arrow/page-button
        // providers are disabled and have no corresponding painted buttons.
        // Expose the actual native thumb; parent scrolling actions stay native.
        // AppKit registers each native part's UIElementSpecifier when its role
        // is first read. Registration calls this parent's accessibilityIndexOfChild,
        // which enumerates children again. Supply the native list during that
        // registration; never recursively query the same child's role.
        // Confirmed by Relic-2026-10-30-100410.ips from CI 41035817459.
        if let registeringNativeParts { return registeringNativeParts }
        guard let parts = super.accessibilityChildren() else { return nil }
        registeringNativeParts = parts
        defer { registeringNativeParts = nil }
        return parts.filter {
            guard let role = RelicAXRole($0) else { return true }
            return role == "AXValueIndicator"
        }
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
