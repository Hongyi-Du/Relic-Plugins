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
        guard let gradient = CGGradient(colorSpace: space,
            colorComponents: [CGFloat(46)/255,CGFloat(44)/255,CGFloat(41)/255,1, CGFloat(27)/255,CGFloat(26)/255,CGFloat(24)/255,1], locations: [0,1], count: 2) else { return }
        context.saveGState()
        context.addPath(CGPath(roundedRect: bounds, cornerWidth: 5, cornerHeight: 5, transform: nil)); context.clip()
        context.scaleBy(x: bounds.width / 64, y: bounds.height / 64)
        context.saveGState()
        context.addPath(CGPath(roundedRect: CGRect(x: 0, y: 0, width: 64, height: 64), cornerWidth: 15, cornerHeight: 15, transform: nil)); context.clip()
        context.drawLinearGradient(gradient, start: CGPoint(x: 0, y: 0), end: CGPoint(x: 0, y: 64), options: [])
        context.restoreGState()
        context.setFillColor(CGColor(colorSpace: space, components: [1,1,1,1])!)
        context.addPath(letter); context.fillPath()
        context.setFillColor(CGColor(colorSpace: space, components: [CGFloat(217)/255,CGFloat(119)/255,CGFloat(87)/255,1])!)
        context.fillEllipse(in: CGRect(x: 43.3, y: 42.3, width: 8.4, height: 8.4))
        context.restoreGState()
        if VisualCapture.enabled {
            lastDraw = ["provider": "production NativeLogoView.draw", "local_bounds": ElementCapture.box(bounds),
                "image_view_box": [0,0,64,64], "outer_clip_radius": 5, "image_corner_radius": 15,
                "gradient": ["start": [0,0], "end": [0,64], "colors": [[46,44,41,255],[27,26,24,255]]],
                "letter_path": Self.letterPath, "letter_fill": [255,255,255,255],
                "circle": ["center": [47.5,46.5], "radius": 4.2, "fill": [217,119,87,255]],
                "renderer": "CoreGraphics actual draw into the mounted image view", "draw_returned": true]
        }
    }
}
