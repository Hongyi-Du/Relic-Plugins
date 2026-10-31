import AppKit
import SwiftUI

/// A CSS disc is a geometric symbol, not the font's bullet character. Keep its
/// spoken alternative while drawing the actual circle with CoreGraphics.
struct NativeListMarker: NSViewRepresentable {
    let size: CGFloat
    var ownedLayer = true
    @Environment(\.captureRegion) private var region
    func makeNSView(context: Context) -> NativeListMarkerView {
        let view = NativeListMarkerView()
        if ownedLayer { view.enableOwnedBackingImage() }
        updateNSView(view, context: context)
        return view
    }
    func updateNSView(_ view: NativeListMarkerView, context: Context) {
        view.configure(font: RelicStyle.nativeFont(size, weight: 400), color: NSColor(RelicStyle.ink), region: region)
    }
}

struct NativeListMarkerMetrics {
    let ascent: Int, descent: Int
    init(font: NSFont) {
        ascent = Int(font.ascender.rounded())
        descent = Int((-font.descender).rounded())
    }
    // The symbol box and its outside margin follow Chromium's native disc
    // layout, using our actual primary font metrics. See REQUESTS.md for the
    // separately measured reference symbol; no reference box enters this code.
    var diameter: CGFloat { CGFloat((ascent * 2 / 3 + 1) / 2) }
    var width: CGFloat { diameter + 2 }
    var height: CGFloat { CGFloat(ascent + descent) }
    var distanceBeforeText: CGFloat { CGFloat(ascent * 2 / 3 + 8) }
    var ellipse: NSRect { NSRect(x: 1, y: CGFloat(3 * (ascent - ascent * 2 / 3) / 2), width: diameter, height: diameter) }
}

@MainActor final class NativeListMarkerView: NSView {
    private var font = RelicStyle.nativeFont(13.5, weight: 400)
    private var color = NSColor(RelicStyle.ink)
    private(set) var region = "window"
    private var revision = 0
    private var sequence = 0
    private(set) var lastDraw: [String: Any]?
    var recordDraws = VisualCapture.enabled
    private(set) var usesOwnedBackingImage = false
    private var backingImage: CGImage?, backingDraw: [String: Any]?
    private var backingBounds = NSRect.zero, backingFrame = NSRect.zero
    private var backingWindow: ObjectIdentifier?
    private var backingScale: CGFloat = 1
    override var wantsUpdateLayer: Bool { usesOwnedBackingImage }
    override func makeBackingLayer() -> CALayer {
        usesOwnedBackingImage ? NativeMarkerBackingLayer(owner: self) : super.makeBackingLayer()
    }
    func enableOwnedBackingImage() {
        usesOwnedBackingImage = true; canDrawSubviewsIntoLayer = false; wantsLayer = true
        invalidatePaint()
    }
    private func invalidatePaint() {
        needsDisplay = true
        if usesOwnedBackingImage { layer?.setNeedsDisplay() }
    }
    override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); invalidatePaint() }
    override func viewDidChangeBackingProperties() { super.viewDidChangeBackingProperties(); invalidatePaint() }
    override func setFrameSize(_ value: NSSize) {
        let changed = frame.size != value; super.setFrameSize(value)
        if changed { invalidatePaint() }
    }
    override var isFlipped: Bool { true }
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setAccessibilityElement(true)
        setAccessibilityRole(.image)
        setAccessibilityLabel("• ")
        setAccessibilityIdentifier("relic-list-marker/" + UUID().uuidString)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        revision += 1; invalidatePaint()
    }
    func configure(font: NSFont, color: NSColor, region: String) {
        self.region = region
        guard self.font != font || self.color != color else { return }
        self.font = font; self.color = color; revision += 1; invalidatePaint()
    }
    override func updateLayer() {
        guard let layer else { return }
        let scale = window?.backingScaleFactor ?? 1
        guard bounds.width > 0, bounds.height > 0, bounds.width.isFinite, bounds.height.isFinite,
              let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: Int(ceil(bounds.width * scale)), height: Int(ceil(bounds.height * scale)),
                bitsPerComponent: 8, bytesPerRow: 0, space: space,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            layer.contents = nil; backingImage = nil; backingDraw = nil; return
        }
        context.translateBy(x: 0, y: CGFloat(context.height)); context.scaleBy(x: scale, y: -scale)
        context.translateBy(x: -bounds.minX, y: -bounds.minY)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
        effectiveAppearance.performAsCurrentDrawingAppearance { draw(bounds) }
        NSGraphicsContext.restoreGraphicsState()
        guard let image = context.makeImage() else { return }
        layer.contentsScale = scale; layer.contentsGravity = .topLeft; layer.contents = image
        backingImage = image; backingDraw = lastDraw; backingBounds = bounds; backingFrame = frame
        backingWindow = window.map(ObjectIdentifier.init); backingScale = scale
    }
    func backingPaintObservation() -> [String: Any] {
        let contents = layer?.contents as AnyObject?, presentation = layer?.presentation()
        let matches = backingImage.map { contents === $0 } ?? false
        let presented = backingImage.map { (presentation?.contents as AnyObject?) === $0 } ?? false
        let current = matches && backingDraw?["revision"] as? Int == revision
            && backingBounds == bounds && backingFrame == frame && backingWindow == window.map(ObjectIdentifier.init)
            && layer?.contentsScale == backingScale && layer?.contentsGravity == .topLeft
        return ["source": "production NativeListMarkerView.updateLayer native sRGB image",
            "current": current, "view_identity": String(describing: ObjectIdentifier(self)),
            "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "image_identity": backingImage.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "layer_contents_is_same_image": matches, "presentation_contents_is_same_image": presented,
            "scale": backingScale, "image_width": backingImage?.width as Any? ?? NSNull(),
            "image_height": backingImage?.height as Any? ?? NSNull(),
            "bounds": ElementCapture.box(backingBounds), "native_frame": ElementCapture.box(backingFrame),
            "disc_draw": backingDraw as Any? ?? NSNull(), "final_png_attribution_proven": false,
            "model_layer": layer.map { NativeLayerOrder.observation($0) } as Any? ?? NSNull(),
            "presentation_layer": presentation.map { NativeLayerOrder.observation($0) } as Any? ?? NSNull()]
    }
    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext,
              let foreground = color.usingColorSpace(.sRGB) else { return }
        let metrics = NativeListMarkerMetrics(font: font)
        // Snap the actual symbol rectangle in the current native device space.
        let ideal = metrics.ellipse.offsetBy(dx: bounds.minX, dy: bounds.minY)
        let device = context.convertToDeviceSpace(ideal)
        let snappedDevice = CGRect(x: device.minX.rounded(), y: device.minY.rounded(),
            width: device.maxX.rounded() - device.minX.rounded(), height: device.maxY.rounded() - device.minY.rounded())
        let ellipse = context.convertToUserSpace(snappedDevice)
        context.saveGState(); context.setShouldAntialias(true)
        context.setFillColor(foreground.cgColor); context.fillEllipse(in: ellipse)
        context.restoreGState()
        if recordDraws {
            sequence += 1
            lastDraw = ["provider": "production NativeListMarkerView.draw / CGContext.fillEllipse",
                "draw_returned": true, "sequence": sequence, "revision": revision,
                "view_identity": String(describing: ObjectIdentifier(self)),
                "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                "local_bounds": ElementCapture.box(bounds), "local_ellipse": ElementCapture.box(ellipse),
                "device_ellipse": ElementCapture.box(snappedDevice), "foreground": ElementCapture.rgba(foreground),
                "symbol": "disc", "alternative_text": "• ", "font_size": font.pointSize,
                "font_postscript_name": font.fontName, "native_ascent": font.ascender, "native_descent": font.descender,
                "layout_ascent": metrics.ascent, "layout_descent": metrics.descent,
                "context_ctm": [context.ctm.a, context.ctm.b, context.ctm.c, context.ctm.d, context.ctm.tx, context.ctm.ty],
                "context_clip": ElementCapture.box(context.boundingBoxOfClipPath), "presentation_identity_proven": false]
        }
    }
    func observation() -> [String: Any] {
        var currentColor: [Double]?
        effectiveAppearance.performAsCurrentDrawingAppearance { currentColor = ElementCapture.rgba(color) as? [Double] }
        guard let window, let draw = lastDraw,
              window.isVisible, !isHiddenOrHasHiddenAncestor,
              draw["revision"] as? Int == revision,
              draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
              draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
              ElementCapture.rect(draw["local_bounds"]) == bounds,
              let currentColor, draw["foreground"] as? [Double] == currentColor else {
            return ["source": "production native disc observation", "current_draw": NSNull(), "errors": ["No current mounted native symbol draw"]]
        }
        guard let content = window.contentView else {
            return ["source": "production native disc observation", "current_draw": NSNull(), "errors": ["No current native window content view"]]
        }
        let contentFrame = window.convertToScreen(content.convert(content.bounds, to: nil))
        let screen = window.convertToScreen(convert(bounds, to: nil))
        let ink = window.convertToScreen(convert(ElementCapture.rect(draw["local_ellipse"]), to: nil))
        return ["source": "production native disc observation", "current_draw": draw,
            "native_backing_image": usesOwnedBackingImage ? backingPaintObservation() as Any : NSNull(),
            "screen_bounds": ElementCapture.box(screen), "screen_ellipse": ElementCapture.box(ink),
            "content_screen_frame": ["source": "actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen",
                "coordinate_space": "AppKit screen coordinates (bottom-left)",
                "window_identity": String(describing: ObjectIdentifier(window)), "bounds": ElementCapture.box(contentFrame)],
            "native_structure": NativeElementStructure.evidence(self, parent: nil), "errors": []]
    }
}

private final class NativeMarkerBackingLayer: CALayer {
    private weak var owner: NativeListMarkerView?
    init(owner: NativeListMarkerView) { self.owner = owner; super.init(); needsDisplayOnBoundsChange = true }
    override init(layer: Any) { super.init(layer: layer) }
    required init?(coder: NSCoder) { super.init(coder: coder) }
    override func display() { MainActor.assumeIsolated { owner?.updateLayer() } }
}
