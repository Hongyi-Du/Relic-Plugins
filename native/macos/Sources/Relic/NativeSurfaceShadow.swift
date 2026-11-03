import AppKit
import SwiftUI

/// Broad surface shadows as Core Animation layer shadows with explicit
/// paths. Opening a menu must not cold-start SwiftUI's offscreen
/// drawingGroup renderer on the event-handling thread.
///
/// These shadows used to be drawn with Quartz into the view's own backing
/// store: for a dialog, a blurred bitmap the size of the panel plus its
/// shadow (about 1040 x 760 points). The commit that showed the dialog then
/// waited for that bitmap (CABackingStoreGetFrontTexture), about 60 ms of a
/// 130 ms first open in a CI sample. With a shadow path on each layer, Core
/// Animation renders the same shape's shadow itself and no bitmap is drawn
/// for the surface at all. The parameters are the Quartz ones: a Quartz blur
/// of twice the shadow radius is a layer shadow of that radius, and in this
/// flipped view positive y still points toward the bottom of the surface.
struct NativeSurfaceShadow: NSViewRepresentable {
    let fill: Color
    let corners: [CGFloat]
    let shadows: [SurfaceShadow]
    let outset: CGFloat
    func makeNSView(context: Context) -> ShadowView { ShadowView() }
    func updateNSView(_ view: ShadowView, context: Context) {
        view.fill = NSColor(fill); view.corners = corners
        view.shadows = shadows; view.outset = outset; view.needsLayout = true
    }
    final class ShadowView: NSView {
        var fill = NSColor.clear
        var corners: [CGFloat] = [0, 0, 0, 0]
        var shadows: [SurfaceShadow] = []
        var outset: CGFloat = 0
        private var shadowLayers: [CALayer] = []
        private let fillLayer = CAShapeLayer()
        override init(frame frameRect: NSRect) { super.init(frame: frameRect); wantsLayer = true }
        required init?(coder: NSCoder) { super.init(coder: coder); wantsLayer = true }
        override var isFlipped: Bool { true }
        override var isOpaque: Bool { false }
        override var wantsUpdateLayer: Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsLayout = true }
        override func updateLayer() { apply() }
        override func layout() { super.layout(); apply() }
        override func setFrameSize(_ newSize: NSSize) { super.setFrameSize(newSize); needsLayout = true }
        private func apply() {
            guard let layer else { return }
            let trace = UIWorkTrace.begin("surface.layer-shadow"); defer { UIWorkTrace.end(trace) }
            var fillColor: CGColor?, alpha: CGFloat = 0, colors: [CGColor?] = []
            effectiveAppearance.performAsCurrentDrawingAppearance {
                let resolved = fill.usingColorSpace(.sRGB)
                fillColor = resolved?.cgColor; alpha = resolved?.alphaComponent ?? 0
                colors = shadows.map { NSColor($0.color).usingColorSpace(.sRGB)?.cgColor }
            }
            CATransaction.begin(); CATransaction.setDisableActions(true)
            defer { CATransaction.commit() }
            guard let fillColor, bounds.width > 2 * outset, bounds.height > 2 * outset else {
                for shadowLayer in shadowLayers { shadowLayer.isHidden = true }
                fillLayer.isHidden = true
                return
            }
            let surface = bounds.insetBy(dx: outset, dy: outset)
            let path = UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3],
                bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular).path(in: surface).cgPath
            // Bottom to top: the last shadow first, as Quartz drew them, then the fill.
            while shadowLayers.count < shadows.count {
                let shadowLayer = CALayer()
                layer.insertSublayer(shadowLayer, at: UInt32(shadowLayers.count)); shadowLayers.append(shadowLayer)
            }
            if fillLayer.superlayer !== layer { layer.addSublayer(fillLayer) }
            for (index, shadowLayer) in shadowLayers.enumerated() {
                let order = shadows.count - 1 - index
                guard order >= 0, let color = colors[order] else { shadowLayer.isHidden = true; continue }
                let shadow = shadows[order]
                shadowLayer.isHidden = false; shadowLayer.frame = bounds
                shadowLayer.shadowPath = path; shadowLayer.shadowColor = color
                // Quartz cast each shadow from the fill, so a translucent fill
                // cast a lighter shadow; the layer shadow takes the fill's alpha.
                shadowLayer.shadowOpacity = Float(alpha)
                shadowLayer.shadowRadius = shadow.radius
                shadowLayer.shadowOffset = CGSize(width: shadow.x, height: shadow.y)
            }
            fillLayer.isHidden = false; fillLayer.frame = bounds
            fillLayer.path = path; fillLayer.fillColor = fillColor
        }
    }
}
