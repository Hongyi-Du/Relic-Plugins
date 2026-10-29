import SwiftUI
import AppKit

// These values draw the production surface and describe that same drawing to
// the capture probe. No reference measurements are consulted.
struct RecordedSurface: ViewModifier {
    let background: Color
    var border: Color = .clear
    var borderWidth: CGFloat = 0
    var radius: CGFloat = 0
    var edges: EdgeInsets? = nil
    var kind: String? = nil
    var owner: String? = nil
    var hovered: Bool? = nil
    @Environment(\.captureOpacity) private var opacity
    func body(content: Content) -> some View {
        content.background(background, in: RoundedRectangle(cornerRadius: radius))
            .overlay {
                if let edges {
                    ZStack {
                        border.frame(height: edges.top).frame(maxHeight: .infinity, alignment: .top)
                        border.frame(width: edges.trailing).frame(maxWidth: .infinity, alignment: .trailing)
                        border.frame(height: edges.bottom).frame(maxHeight: .infinity, alignment: .bottom)
                        border.frame(width: edges.leading).frame(maxWidth: .infinity, alignment: .leading)
                    }.allowsHitTesting(false)
                } else { RoundedRectangle(cornerRadius: radius).strokeBorder(border, lineWidth: borderWidth).allowsHitTesting(false) }
            }
            .background(SurfacePaintProbe(background: background, border: border, borderWidth: borderWidth, radius: radius, edges: edges, opacity: opacity, kind: kind, owner: owner, hovered: hovered))
    }
}

private struct CaptureOpacityKey: EnvironmentKey { static var defaultValue: Double = 1 }
extension EnvironmentValues {
    var captureOpacity: Double { get { self[CaptureOpacityKey.self] } set { self[CaptureOpacityKey.self] = newValue } }
}
private struct RecordedOpacity: ViewModifier {
    @Environment(\.captureOpacity) private var inherited
    let value: Double
    func body(content: Content) -> some View { content.opacity(value).environment(\.captureOpacity, inherited * value) }
}
extension View {
    func recordedOpacity(_ opacity: Double) -> some View { modifier(RecordedOpacity(value: opacity)) }
}

struct SurfacePaintProbe: NSViewRepresentable {
    let background: Color
    let border: Color
    let borderWidth: CGFloat
    let radius: CGFloat
    let edges: EdgeInsets?
    let opacity: Double
    let kind: String?
    let owner: String?
    let hovered: Bool?
    private static let live = NSHashTable<SurfaceView>.weakObjects()
    func makeNSView(context: Context) -> SurfaceView { let view = SurfaceView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: SurfaceView, context: Context) {
        view.fill = NSColor(background); view.border = NSColor(border); view.width = borderWidth
        view.widths = edges.map { [$0.top, $0.trailing, $0.bottom, $0.leading] } ?? Array(repeating: borderWidth, count: 4)
        view.separateEdges = edges != nil; view.radius = radius; view.opacity = opacity; view.kind = kind; view.owner = owner; view.hovered = hovered
    }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor else { return nil }
            let rect = ElementCapture.topLeft(window.convertToScreen(view.convert(view.bounds, to: nil)), in: content)
            var fill: Any = NSNull(), border: Any = NSNull()
            window.effectiveAppearance.performAsCurrentDrawingAppearance {
                fill = ElementCapture.rgba(view.fill); border = ElementCapture.rgba(view.border)
            }
            var opacity = view.opacity
            var ancestor: NSView? = view
            while let current = ancestor { opacity *= Double(current.alphaValue); ancestor = current.superview }
            return ["rectValue": NSValue(rect: rect), "bounds": ElementCapture.box(rect),
                    "owner": view.owner as Any? ?? NSNull(), "kind": view.kind as Any? ?? NSNull(), "hovered": view.hovered as Any? ?? NSNull(),
                    "style": ["backgroundColor": fill, "borderColor": border, "borderWidth": Double(view.widths.max() ?? view.width), "borderRadius": Double(view.radius),
                              "border_widths": view.widths.map { Double($0) },
                              "border_colors": Array(repeating: border, count: 4), "corner_radii": Array(repeating: Double(view.radius), count: 4),
                              "opacity": opacity, "background_image": "none", "shadow": []],
                    "evidence": ["source": "live-native-surface-probe", "renderer": view.separateEdges ? "RoundedRectangle.fill and four edge Rectangles" : "RoundedRectangle.fill/strokeBorder", "attachment": "production ViewModifier", "identity": view.identity]]
        }
    }
    final class SurfaceView: NSView {
        let identity = UUID().uuidString
        var fill = NSColor.clear, border = NSColor.clear
        var width: CGFloat = 0, radius: CGFloat = 0, opacity: Double = 1
        var widths: [CGFloat] = [0,0,0,0]
        var kind: String?, owner: String?, hovered: Bool?
        var separateEdges = false
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
