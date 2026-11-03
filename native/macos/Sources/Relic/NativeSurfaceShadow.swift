import AppKit
import SwiftUI

/// Draw broad surface shadows with Quartz. Opening a menu must not cold-start
/// SwiftUI's offscreen drawingGroup renderer on the event-handling thread.
///
/// On screen the view no longer draws its own backing store. For a dialog
/// that store was a blurred bitmap the size of the panel plus its shadow
/// (about 1040 x 760 points), and the commit that showed the dialog waited
/// for it (CABackingStoreGetFrontTexture: about 60 ms of a 130 ms first open
/// in a CI sample). Instead the same Quartz drawing is rendered once into a
/// small nine-slice image: the four corners, each edge's shadow and a middle
/// that are all the larger surface shows, since a blurred rounded rectangle
/// is the same along a straight edge once past its corners. The layer
/// stretches that image's middle row and column to the view's size, so the
/// pixels are the Quartz ones and nothing is drawn per dialog. Captures that
/// draw the view into a bitmap (cacheDisplay) still use `draw(_:)`.
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
        /// The view that renders an image draws itself, as a capture does.
        fileprivate var drawsItself = false
        override init(frame frameRect: NSRect) { super.init(frame: frameRect); wantsLayer = true }
        required init?(coder: NSCoder) { super.init(coder: coder); wantsLayer = true }
        override var isFlipped: Bool { true }
        override var isOpaque: Bool { false }
        // Out of a window (a test's hosting view) the view draws itself too.
        override var wantsUpdateLayer: Bool { !drawsItself && window != nil }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidChangeEffectiveAppearance() { super.viewDidChangeEffectiveAppearance(); needsDisplay = true }
        override func viewDidChangeBackingProperties() { super.viewDidChangeBackingProperties(); needsDisplay = true }
        override func setFrameSize(_ newSize: NSSize) { super.setFrameSize(newSize); needsDisplay = true }
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
                // This flipped NSView's drawing context already expresses
                // positive y toward the bottom of the surface.
                context.setShadow(offset: CGSize(width: shadow.x, height: shadow.y), blur: shadow.radius * 2, color: color.cgColor)
                context.setFillColor(fill.cgColor); context.addPath(path); context.fillPath()
                context.restoreGState()
            }
        }
        override func updateLayer() {
            guard let layer else { return }
            let trace = UIWorkTrace.begin("surface.shadow-image"); defer { UIWorkTrace.end(trace) }
            let scale = max(1, window?.backingScaleFactor ?? layer.contentsScale)
            // Beyond this inset from each side, every row and column of the
            // drawing is the same: the surface's corners are behind it and the
            // widest blur (a Gaussian of half the Quartz blur, three of them)
            // has faded.
            let reach = (shadows.map { $0.radius * 3 + max(abs($0.x), abs($0.y)) }.max() ?? 0)
            let inset = (outset + (corners.max() ?? 0) + reach).rounded(.up)
            let slice = NSSize(width: 2 * inset + 1, height: 2 * inset + 1)
            let sliced = bounds.width >= slice.width && bounds.height >= slice.height
            let size = sliced ? slice : bounds.size
            guard size.width >= 1, size.height >= 1,
                  let image = Self.image(for: self, size: size, scale: scale, cached: sliced) else { layer.contents = nil; return }
            layer.contents = image
            layer.contentsScale = scale
            layer.contentsGravity = .resize
            layer.contentsCenter = sliced
                ? CGRect(x: inset / slice.width, y: inset / slice.height, width: 1 / slice.width, height: 1 / slice.height)
                : CGRect(x: 0, y: 0, width: 1, height: 1)
        }

        private static var images: [String: CGImage] = [:]
        private static func describe(_ color: NSColor?) -> String {
            guard let color else { return "none" }
            return "\(color.redComponent),\(color.greenComponent),\(color.blueComponent),\(color.alphaComponent)"
        }
        /// The Quartz drawing of `view`'s surface at `size`, drawn the way a
        /// capture draws it. The nine-slice image is kept per appearance,
        /// colors, shape and scale; a full-size image for a small surface is not.
        private static func image(for view: ShadowView, size: NSSize, scale: CGFloat, cached: Bool) -> CGImage? {
            var key = ""
            if cached {
                var parts: [String] = []
                view.effectiveAppearance.performAsCurrentDrawingAppearance {
                    parts.append(Self.describe(view.fill.usingColorSpace(.sRGB)))
                    for shadow in view.shadows {
                        parts.append(Self.describe(NSColor(shadow.color).usingColorSpace(.sRGB)))
                        parts.append("\(shadow.radius),\(shadow.x),\(shadow.y)")
                    }
                }
                parts.append(view.corners.map { "\($0)" }.joined(separator: ","))
                parts.append("\(view.outset)|\(size.width)x\(size.height)@\(scale)")
                key = parts.joined(separator: "|")
                if let known = images[key] { return known }
            }
            let template = ShadowView(frame: NSRect(origin: .zero, size: size))
            template.drawsItself = true
            template.appearance = view.effectiveAppearance
            template.fill = view.fill; template.corners = view.corners
            template.shadows = view.shadows; template.outset = view.outset
            guard let allocation = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int((size.width * scale).rounded()),
                    pixelsHigh: Int((size.height * scale).rounded()), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                    isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
                  let bitmap = allocation.retagging(with: .sRGB), let bytes = bitmap.bitmapData else { return nil }
            bytes.update(repeating: 0, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
            bitmap.size = size
            template.cacheDisplay(in: template.bounds, to: bitmap)
            guard let image = bitmap.cgImage else { return nil }
            if cached {
                if images.count >= 32 { images.removeAll() }
                images[key] = image
            }
            return image
        }
    }
}
