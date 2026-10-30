import AppKit
import SwiftUI

/// A CSS disc is a geometric symbol, not the font's bullet character. Keep its
/// spoken alternative while drawing the actual circle with CoreGraphics.
struct NativeListMarker: NSViewRepresentable {
    let size: CGFloat
    @Environment(\.captureRegion) private var region
    func makeNSView(context: Context) -> NativeListMarkerView {
        let view = NativeListMarkerView()
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
    func configure(font: NSFont, color: NSColor, region: String) {
        self.region = region
        guard self.font != font || self.color != color else { return }
        self.font = font; self.color = color; revision += 1; needsDisplay = true
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
        guard let window, let draw = lastDraw,
              window.isVisible, !isHiddenOrHasHiddenAncestor,
              draw["revision"] as? Int == revision,
              draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
              draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
              ElementCapture.rect(draw["local_bounds"]) == bounds else {
            return ["source": "production native disc observation", "current_draw": NSNull(), "errors": ["No current mounted native symbol draw"]]
        }
        let screen = window.convertToScreen(convert(bounds, to: nil))
        let ink = window.convertToScreen(convert(ElementCapture.rect(draw["local_ellipse"]), to: nil))
        return ["source": "production native disc observation", "current_draw": draw,
            "screen_bounds": ElementCapture.box(screen), "screen_ellipse": ElementCapture.box(ink),
            "native_structure": NativeElementStructure.evidence(self, parent: nil), "errors": []]
    }
}
