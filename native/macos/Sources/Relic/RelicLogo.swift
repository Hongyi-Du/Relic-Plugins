import AppKit
import SwiftUI

struct RelicLogo: View {
    var body: some View { LogoRenderer().frame(width: 18, height: 18) }
}

private struct LogoRenderer: NSViewRepresentable {
    func makeNSView(context: Context) -> NativeLogoView { NativeLogoView() }
    func updateNSView(_ view: NativeLogoView, context: Context) {}
}

/// The actual vector image has its own native view and draw receipt. Hiding a
/// SwiftUI shape from AX previously removed this visible reference element from
/// extraction altogether. No second image is generated to supply the receipt.
final class NativeLogoView: NSView {
    static let letterPath = "M21 47V17h12.8c6.4 0 10.2 3.5 10.2 8.9 0 4.2-2.3 7.2-6.2 8.3L45 47h-7.6l-6.4-12.1H27.9V47H21zm6.9-17.8h5.9c2.8 0 4.3-1.3 4.3-3.6s-1.5-3.6-4.3-3.6h-5.9v7.2z"
    private(set) var lastDraw: [String: Any]?
    var recordDraws = VisualCapture.enabled
    private var drawSequence = 0
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .image }
    override func accessibilityLabel() -> String? { "" }
    override func accessibilityIdentifier() -> String { "relic-brand-image" }
    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext,
              let letter = try? VectorPath.parse(Self.letterPath) else { return }
        let space = CGColorSpace(name: CGColorSpace.sRGB)!
        let viewBox = CGRect(x: 0, y: 0, width: 64, height: 64)
        let imageRadius: CGFloat = 15, outerRadius: CGFloat = 5
        let gradientStart = CGPoint(x: 0, y: 0), gradientEnd = CGPoint(x: 0, y: 64)
        let stopOffsets: [CGFloat] = [0, 1]
        let stopColors: [[CGFloat]] = [[46,44,41,255], [27,26,24,255]]
        let letterColor: [CGFloat] = [255,255,255,255]
        let circleColor: [CGFloat] = [217,119,87,255]
        let circleCenter = CGPoint(x: 47.5, y: 46.5), circleRadius: CGFloat = 4.2
        let gradientOptions: CGGradientDrawingOptions = [.drawsBeforeStartLocation, .drawsAfterEndLocation]
        guard let gradient = CGGradient(colorSpace: space,
            colorComponents: stopColors.flatMap { $0.map { $0 / 255 } }, locations: stopOffsets, count: stopOffsets.count) else { return }
        context.saveGState()
        context.addPath(CGPath(roundedRect: bounds, cornerWidth: outerRadius, cornerHeight: outerRadius, transform: nil)); context.clip()
        context.translateBy(x: bounds.minX, y: bounds.minY)
        context.scaleBy(x: bounds.width / viewBox.width, y: bounds.height / viewBox.height)
        let imageTransform = context.ctm
        context.saveGState()
        context.addPath(CGPath(roundedRect: viewBox, cornerWidth: imageRadius, cornerHeight: imageRadius, transform: nil)); context.clip()
        context.drawLinearGradient(gradient, start: gradientStart, end: gradientEnd, options: gradientOptions)
        context.restoreGState()
        context.setFillColor(CGColor(colorSpace: space, components: letterColor.map { $0 / 255 })!)
        context.addPath(letter); context.fillPath()
        context.setFillColor(CGColor(colorSpace: space, components: circleColor.map { $0 / 255 })!)
        context.fillEllipse(in: CGRect(x: circleCenter.x - circleRadius, y: circleCenter.y - circleRadius, width: circleRadius * 2, height: circleRadius * 2))
        context.restoreGState()
        if recordDraws {
            drawSequence += 1
            var pathElements: [[String: Any]] = []
            letter.applyWithBlock { element in
                let value = element.pointee
                let count: Int
                switch value.type { case .moveToPoint, .addLineToPoint: count = 1; case .addQuadCurveToPoint: count = 2; case .addCurveToPoint: count = 3; default: count = 0 }
                pathElements.append(["type": value.type.rawValue, "points": (0..<count).map { [value.points[$0].x, value.points[$0].y] }])
            }
            // These are the same parameters supplied to the actual CG calls
            // above, retained in their executed painting order. No reference
            // SVG, URI or expected image dictionary is read by this renderer.
            let paint: [String: Any] = ["source": "vector-image-v1", "glyph": [
                "view_box": [viewBox.minX, viewBox.minY, viewBox.width, viewBox.height],
                "layers": [
                    ["kind": "rounded-rect", "bounds": [viewBox.minX, viewBox.minY, viewBox.width, viewBox.height],
                     "radii": [imageRadius, imageRadius], "fill": ["kind": "linear-gradient", "start": [gradientStart.x, gradientStart.y],
                         "end": [gradientEnd.x, gradientEnd.y], "spread": "pad", "color_space": "srgb",
                         "stops": zip(stopOffsets, stopColors).map { ["offset": $0.0, "color": $0.1] as [String: Any] }]],
                    ["kind": "path", "d": Self.letterPath, "fill_rule": "nonzero", "fill": ["kind": "solid", "color": letterColor]],
                    ["kind": "circle", "center": [circleCenter.x, circleCenter.y], "radius": circleRadius,
                     "fill": ["kind": "solid", "color": circleColor]]
                ] as [[String: Any]]]]
            lastDraw = ["provider": "production NativeLogoView.draw", "local_bounds": ElementCapture.box(bounds),
                "sequence": drawSequence, "view_identity": String(describing: ObjectIdentifier(self)),
                "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                "outer_clip_radius": outerRadius, "parsed_path_elements": pathElements,
                "cg_color_space": space.name as Any? ?? NSNull(), "gradient_options": gradientOptions.rawValue,
                "image_context_transform": ["a": imageTransform.a, "b": imageTransform.b, "c": imageTransform.c, "d": imageTransform.d, "tx": imageTransform.tx, "ty": imageTransform.ty],
                "paint": paint, "renderer": "CoreGraphics actual draw into the mounted image view", "draw_returned": true,
                "presentation_identity_proven": false]
        }
    }
    func currentPaint() -> [String: Any]? {
        guard let window, window.isVisible, let draw = lastDraw,
              draw["draw_returned"] as? Bool == true,
              draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
              draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
              ElementCapture.rect(draw["local_bounds"]) == bounds else { return nil }
        return draw["paint"] as? [String: Any]
    }
}
