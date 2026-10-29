import SwiftUI
import AppKit

// Keep native NSScrollView scrolling/AX/keyboard behavior while matching the
// reference's overlay track. A legacy scroller reserves 15px and shifts every
// message and inspector row, even when the visible thumb is only a few pixels.
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
                    scroll.scrollerStyle = .overlay; scroll.autohidesScrollers = true
                    if scroll.hasVerticalScroller && !(scroll.verticalScroller is ReferenceScroller) { scroll.verticalScroller = ReferenceScroller() }
                    if scroll.hasHorizontalScroller && !(scroll.horizontalScroller is ReferenceScroller) { scroll.horizontalScroller = ReferenceScroller() }
                }
                for child in view.subviews { apply(child) }
            }
            apply(root)
        }
    }
}

final class ReferenceScroller: NSScroller {
    private var over = false
    override class var isCompatibleWithOverlayScrollers: Bool { true }
    var paintedKnob: NSRect {
        let knob = rect(for: .knob)
        if bounds.height > bounds.width { return NSRect(x: bounds.maxX - 7, y: knob.minY + 3, width: 4, height: max(0, knob.height - 6)) }
        return NSRect(x: knob.minX + 3, y: bounds.maxY - 7, width: max(0, knob.width - 6), height: 4)
    }
    override func drawKnob() {
        guard knobProportion < 1 else { return }
        NSColor(RelicStyle.muted).withAlphaComponent(over ? 0.55 : 0.35).setFill()
        NSBezierPath(roundedRect: paintedKnob, xRadius: 2, yRadius: 2).fill()
    }
    override func drawKnobSlot(in slotRect: NSRect, highlight flag: Bool) {}
    override func updateTrackingAreas() {
        for area in trackingAreas { removeTrackingArea(area) }
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.inVisibleRect, .activeAlways, .mouseEnteredAndExited], owner: self))
        super.updateTrackingAreas()
    }
    override func mouseEntered(with event: NSEvent) { over = true; needsDisplay = true }
    override func mouseExited(with event: NSEvent) { over = false; needsDisplay = true }
}
