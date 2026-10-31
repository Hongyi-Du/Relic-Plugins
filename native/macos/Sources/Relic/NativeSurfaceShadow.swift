import AppKit
import SwiftUI

/// Draw broad surface shadows with Quartz. Opening a menu must not cold-start
/// SwiftUI's offscreen drawingGroup renderer on the event-handling thread.
struct NativeSurfaceShadow: NSViewRepresentable {
    let fill: Color
    let corners: [CGFloat]
    let shadows: [SurfaceShadow]
    let outset: CGFloat
    func makeNSView(context: Context) -> ShadowView { ShadowView() }
    func updateNSView(_ view: ShadowView, context: Context) {
        view.fill = NSColor(fill); view.corners = corners
        view.shadows = shadows; view.outset = outset; view.needsDisplay = true
    }
    final class ShadowView: NSView {
        var fill = NSColor.clear
        var corners: [CGFloat] = [0, 0, 0, 0]
        var shadows: [SurfaceShadow] = []
        var outset: CGFloat = 0
        override var isFlipped: Bool { true }
        override var isOpaque: Bool { false }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsDisplay = true }
        override func draw(_ dirtyRect: NSRect) {
            let trace = UIWorkTrace.begin("surface.quartz-shadow"); defer { UIWorkTrace.end(trace) }
            guard let context = NSGraphicsContext.current?.cgContext,
                  let fill = fill.usingColorSpace(.sRGB), bounds.width > 2 * outset, bounds.height > 2 * outset else { return }
            let surface = bounds.insetBy(dx: outset, dy: outset)
            let path = UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3],
                bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular).path(in: surface).cgPath
            for shadow in shadows.reversed() {
                guard let color = NSColor(shadow.color).usingColorSpace(.sRGB) else { continue }
                context.saveGState()
                context.setBlendMode(.normal); context.setAlpha(1); context.setShouldAntialias(true)
                context.setShadow(offset: CGSize(width: shadow.x, height: -shadow.y), blur: shadow.radius * 2, color: color.cgColor)
                context.setFillColor(fill.cgColor); context.addPath(path); context.fillPath()
                context.restoreGState()
            }
        }
    }
}
