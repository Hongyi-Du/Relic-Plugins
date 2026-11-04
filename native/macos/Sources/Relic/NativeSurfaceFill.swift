import AppKit
import SwiftUI

/// The actual background painter. Its path and fill are independent native
/// evidence for later occlusion validation; a receipt alone does not establish
/// that another element was behind it or absent from the final screenshot.
struct NativeSurfaceFill: NSViewRepresentable {
    let color: Color
    let corners: [CGFloat]
    let owner: String?
    var ownedLayer = true
    @Environment(\.captureRegion) private var region
    private static let live = NSHashTable<NativeSurfaceFillView>.weakObjects()
    func makeNSView(context: Context) -> NativeSurfaceFillView {
        let view = NativeSurfaceFillView(); Self.live.add(view)
        if ownedLayer { view.enableOwnedBackingImage() }
        return view
    }
    func updateNSView(_ view: NativeSurfaceFillView, context: Context) {
        view.configure(color: NSColor(color), corners: corners, owner: owner, region: region)
    }
    static func observations(in window: NSWindow) -> [[String: Any]] {
        live.allObjects.filter { $0.window === window && !$0.isHiddenOrHasHiddenAncestor }.map { $0.observation() }
    }
    static func mountedViews(in window: NSWindow) -> [NativeSurfaceFillView] {
        live.allObjects.filter { $0.window === window && !$0.isHiddenOrHasHiddenAncestor }
    }
}

@MainActor final class NativeSurfaceFillView: NSView {
    private var color = NSColor.clear
    private var corners: [CGFloat] = [0,0,0,0]
    private var owner: String?, region = "window"
    private var revision = 0, sequence = 0
    private(set) var lastDraw: [String: Any]?
    var recordDraws = VisualCapture.enabled
    private(set) var usesOwnedBackingImage = false
    private var backingImage: CGImage?, backingDraw: [String: Any]?
    private var backingBounds = NSRect.zero, backingFrame = NSRect.zero
    private var backingWindow: ObjectIdentifier?
    private var backingScale: CGFloat = 1
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func isAccessibilityElement() -> Bool { false }
    override var wantsUpdateLayer: Bool { usesOwnedBackingImage }
    override func makeBackingLayer() -> CALayer {
        usesOwnedBackingImage ? NativeFillBackingLayer(owner: self) : super.makeBackingLayer()
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
    override func setFrameSize(_ newSize: NSSize) {
        let changed = frame.size != newSize; super.setFrameSize(newSize)
        if changed { invalidatePaint() }
    }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance(); revision += 1; invalidatePaint()
    }
    func configure(color: NSColor, corners: [CGFloat], owner: String?, region: String) {
        precondition(corners.count == 4)
        guard self.color != color || self.corners != corners || self.owner != owner || self.region != region else { return }
        self.color = color; self.corners = corners; self.owner = owner; self.region = region
        revision += 1; invalidatePaint()
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
        let contents = layer?.contents as AnyObject?
        let identical = backingImage.map { contents === $0 } ?? false
        var currentFill: [Double]?
        effectiveAppearance.performAsCurrentDrawingAppearance { currentFill = ElementCapture.rgba(color) as? [Double] }
        let current = identical && backingDraw?["revision"] as? Int == revision
            && currentFill != nil && backingDraw?["fill"] as? [Double] == currentFill
            && backingBounds == bounds && backingFrame == frame && backingWindow == window.map(ObjectIdentifier.init)
            && layer?.contentsScale == backingScale && layer?.contentsGravity == .topLeft
        return ["source": "actual native surface updateLayer sRGB image", "current": current,
            "view_identity": String(describing: ObjectIdentifier(self)),
            "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "image_identity": backingImage.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "layer_contents_is_same_image": identical, "scale": backingScale,
            "bounds": ElementCapture.box(backingBounds), "native_frame": ElementCapture.box(backingFrame),
            "fill_draw": backingDraw as Any? ?? NSNull(), "final_png_attribution_proven": false]
    }
    func currentOwnedImage() -> CGImage? {
        guard usesOwnedBackingImage, backingPaintObservation()["current"] as? Bool == true else { return nil }
        return backingImage
    }
    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext,
              let fill = color.usingColorSpace(.sRGB) else { return }
        let path = UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3],
            bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular).path(in: bounds).cgPath
        context.saveGState()
        context.setAlpha(1); context.setBlendMode(.normal); context.setShouldAntialias(true)
        context.setFillColor(fill.cgColor); context.addPath(path); context.fillPath()
        if recordDraws {
            sequence += 1
            lastDraw = ["provider": "production NativeSurfaceFillView.draw / CGContext.fillPath",
                "draw_returned": true, "sequence": sequence, "revision": revision,
                "view_identity": String(describing: ObjectIdentifier(self)),
                "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                "local_bounds": ElementCapture.box(bounds),
                "local_path": OutlineDrawReceipt.pathString(path, map: { $0 }),
                "fill": ElementCapture.rgba(fill), "fill_rule": "nonzero", "global_alpha": 1,
                "blend_mode": "normal", "antialias": true,
                "context_bitmap": ["bits_per_component": context.bitsPerComponent,
                    "bits_per_pixel": context.bitsPerPixel, "bytes_per_row": context.bytesPerRow,
                    "bitmap_info": context.bitmapInfo.rawValue, "alpha_info": context.alphaInfo.rawValue,
                    "color_space": context.colorSpace?.name.map { $0 as String } as Any? ?? NSNull(),
                    "data_address": context.data.map { "0x" + String(UInt(bitPattern: $0), radix: 16) } as Any? ?? NSNull(),
                    "bitmap_data_available": context.data != nil],
                "context_ctm": [context.ctm.a, context.ctm.b, context.ctm.c, context.ctm.d, context.ctm.tx, context.ctm.ty],
                "context_clip": ElementCapture.box(context.boundingBoxOfClipPath)]
        }
        context.restoreGState()
    }
    func observation() -> [String: Any] {
        var actualFill: [Double]?
        effectiveAppearance.performAsCurrentDrawingAppearance { actualFill = ElementCapture.rgba(color) as? [Double] }
        var result: [String: Any] = ["source": "production native surface fill observation",
            "owner_identifier": owner as Any? ?? NSNull(), "region": region,
            "native_structure": NativeElementStructure.evidence(self, parent: owner),
            "opacity_ancestry": NativeVisibility.opacityAncestry(self),
            "occlusion_proven": false,
            "measurement_limit": "A current actual fill is not proof of final screenshot compositing order or covered-element invisibility"]
        if usesOwnedBackingImage { result["native_backing_image"] = backingPaintObservation() }
        guard let window, window.isVisible, !isHiddenOrHasHiddenAncestor,
              let content = window.contentView, let draw = lastDraw,
              draw["revision"] as? Int == revision,
              draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
              draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
              ElementCapture.rect(draw["local_bounds"]) == bounds,
              let actualFill, draw["fill"] as? [Double] == actualFill else {
            result["current_draw"] = NSNull(); result["errors"] = ["No current mounted native fill draw"]
            return result
        }
        result["current_draw"] = draw
        result["screen_bounds"] = ElementCapture.box(window.convertToScreen(convert(bounds, to: nil)))
        result["screen_clip"] = NativeVisibility.screenClip(self).map(ElementCapture.box) as Any? ?? NSNull()
        result["content_screen_frame"] = ["source": "actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen",
            "coordinate_space": "AppKit screen coordinates (bottom-left)",
            "window_identity": String(describing: ObjectIdentifier(window)),
            "bounds": ElementCapture.box(window.convertToScreen(content.convert(content.bounds, to: nil)))]
        result["errors"] = []
        return result
    }
}

private final class NativeFillBackingLayer: CALayer {
    private weak var owner: NativeSurfaceFillView?
    init(owner: NativeSurfaceFillView) { self.owner = owner; super.init(); needsDisplayOnBoundsChange = true }
    override init(layer: Any) { super.init(layer: layer) }
    required init?(coder: NSCoder) { super.init(coder: coder) }
    override func display() { MainActor.assumeIsolated { owner?.updateLayer() } }
}
