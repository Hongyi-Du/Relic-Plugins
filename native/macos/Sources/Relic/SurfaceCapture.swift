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
    var shadows: [SurfaceShadow] = []
    var cornerRadii: [CGFloat]? = nil
    var insetLeadingWidth: CGFloat = 0
    var insetLeadingColor: Color = .clear
    var borderDash: [CGFloat] = []
    var selected: Bool? = nil
    var expanded: Bool? = nil
    var current: Bool? = nil
    var insetRingWidth: CGFloat = 0
    var insetRingColor: Color = .clear
    var outerRingWidth: CGFloat = 0
    var outerRingColor: Color = .clear
    @Environment(\.captureOpacity) private var opacity
    private var shape: UnevenRoundedRectangle {
        let corners = cornerRadii ?? Array(repeating: radius, count: 4)
        return UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3], bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular)
    }
    func body(content: Content) -> some View {
        content.background(background, in: shape)
            .overlay {
                if let edges {
                    ZStack {
                        border.frame(height: edges.top).frame(maxHeight: .infinity, alignment: .top)
                        border.frame(width: edges.trailing).frame(maxWidth: .infinity, alignment: .trailing)
                        border.frame(height: edges.bottom).frame(maxHeight: .infinity, alignment: .bottom)
                        border.frame(width: edges.leading).frame(maxWidth: .infinity, alignment: .leading)
                    }.allowsHitTesting(false)
                } else { shape.strokeBorder(border, style: StrokeStyle(lineWidth: borderWidth, dash: borderDash)).allowsHitTesting(false) }
            }
            .overlay { if insetLeadingWidth > 0 { insetLeadingColor.frame(width: insetLeadingWidth).frame(maxWidth: .infinity, alignment: .leading).clipShape(shape).allowsHitTesting(false) } }
            .overlay { if insetRingWidth > 0 { shape.inset(by: borderWidth).strokeBorder(insetRingColor, lineWidth: insetRingWidth).allowsHitTesting(false) } }
            .background {
                if outerRingWidth > 0 {
                    RoundedRectangle(cornerRadius: radius + outerRingWidth).strokeBorder(outerRingColor, lineWidth: outerRingWidth).padding(-outerRingWidth).allowsHitTesting(false)
                }
            }
            .modifier(SurfaceShadows(values: shadows))
            .background(SurfacePaintProbe(background: background, border: border, borderWidth: borderWidth, radius: radius, edges: edges, opacity: opacity, kind: kind, owner: owner, hovered: hovered, shadows: shadows, cornerRadii: cornerRadii, insetLeadingWidth: insetLeadingWidth, insetLeadingColor: insetLeadingColor, borderDash: borderDash, selected: selected, expanded: expanded, current: current, insetRingWidth: insetRingWidth, insetRingColor: insetRingColor, outerRingWidth: outerRingWidth, outerRingColor: outerRingColor))
    }
}

struct SurfaceShadow {
    let color: Color
    let radius: CGFloat, x: CGFloat, y: CGFloat
    static let small = [SurfaceShadow(color: Color(red: 20/255, green: 18/255, blue: 15/255).opacity(0.06), radius: 1, x: 0, y: 1)]
    private static func color(_ lightAlpha: CGFloat, _ darkAlpha: CGFloat) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(srgbRed: 0, green: 0, blue: 0, alpha: darkAlpha) : NSColor(srgbRed: 20/255, green: 18/255, blue: 15/255, alpha: lightAlpha)
        })
    }
    static let dialog = [SurfaceShadow(color: color(0.14, 0.5), radius: 16, x: 0, y: 10), SurfaceShadow(color: color(0.06, 0.3), radius: 3, x: 0, y: 2)]
}
private struct SurfaceShadows: ViewModifier {
    let values: [SurfaceShadow]
    func body(content: Content) -> some View {
        values.reversed().reduce(AnyView(content)) { view, value in
            AnyView(view.shadow(color: value.color, radius: value.radius, x: value.x, y: value.y))
        }
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
    @Environment(\.captureRegion) private var region
    let background: Color
    let border: Color
    let borderWidth: CGFloat
    let radius: CGFloat
    let edges: EdgeInsets?
    let opacity: Double
    let kind: String?
    let owner: String?
    let hovered: Bool?
    let shadows: [SurfaceShadow]
    let cornerRadii: [CGFloat]?
    let insetLeadingWidth: CGFloat
    let insetLeadingColor: Color
    let borderDash: [CGFloat]
    let selected: Bool?
    let expanded: Bool?
    let current: Bool?
    let insetRingWidth: CGFloat, insetRingColor: Color, outerRingWidth: CGFloat, outerRingColor: Color
    private static let live = NSHashTable<SurfaceView>.weakObjects()
    func makeNSView(context: Context) -> SurfaceView { let view = SurfaceView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: SurfaceView, context: Context) {
        view.fill = NSColor(background); view.border = NSColor(border); view.width = borderWidth
        view.widths = edges.map { [$0.top, $0.trailing, $0.bottom, $0.leading] } ?? Array(repeating: borderWidth, count: 4)
        view.separateEdges = edges != nil; view.radius = radius; view.opacity = opacity; view.kind = kind; view.owner = owner; view.hovered = hovered
        view.shadows = shadows
        view.cornerRadii = cornerRadii ?? Array(repeating: radius, count: 4)
        view.insetLeadingWidth = insetLeadingWidth; view.insetLeadingColor = NSColor(insetLeadingColor)
        view.borderDash = borderDash
        view.selected = selected; view.expanded = expanded; view.current = current
        view.region = region
        view.insetRingWidth = insetRingWidth; view.insetRingColor = NSColor(insetRingColor)
        view.outerRingWidth = outerRingWidth; view.outerRingColor = NSColor(outerRingColor)
    }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor else { return nil }
            let rect = ElementCapture.topLeft(window.convertToScreen(view.convert(view.bounds, to: nil)), in: content)
            var fill: Any = NSNull(), border: Any = NSNull(), shadows: [[String: Any]] = []
            view.effectiveAppearance.performAsCurrentDrawingAppearance {
                fill = ElementCapture.rgba(view.fill); border = ElementCapture.rgba(view.border)
                shadows = view.shadows.map { ["inset": false, "offset_x": Double($0.x), "offset_y": Double($0.y), "blur_radius": Double($0.radius * 2), "spread_radius": 0, "color": ElementCapture.rgba(NSColor($0.color))] }
                if view.insetLeadingWidth > 0 { shadows.insert(["inset": true, "offset_x": Double(view.insetLeadingWidth), "offset_y": 0, "blur_radius": 0, "spread_radius": 0, "color": ElementCapture.rgba(view.insetLeadingColor)], at: 0) }
                if view.insetRingWidth > 0 { shadows.append(["inset": true, "offset_x": 0, "offset_y": 0, "blur_radius": 0, "spread_radius": Double(view.insetRingWidth), "color": ElementCapture.rgba(view.insetRingColor)]) }
                if view.outerRingWidth > 0 { shadows.append(["inset": false, "offset_x": 0, "offset_y": 0, "blur_radius": 0, "spread_radius": Double(view.outerRingWidth), "color": ElementCapture.rgba(view.outerRingColor)]) }
            }
            var opacity = view.opacity
            var ancestor: NSView? = view
            while let current = ancestor { opacity *= Double(current.alphaValue); ancestor = current.superview }
            return ["rectValue": NSValue(rect: rect), "bounds": ElementCapture.box(rect), "region": view.region,
                    "owner": view.owner as Any? ?? NSNull(), "kind": view.kind as Any? ?? NSNull(), "hovered": view.hovered as Any? ?? NSNull(),
                    "selected": view.selected as Any? ?? NSNull(), "expanded": view.expanded as Any? ?? NSNull(), "current": view.current as Any? ?? NSNull(),
                    "style": ["backgroundColor": fill, "borderColor": border, "borderWidth": Double(view.widths.max() ?? view.width), "borderRadius": Double(view.cornerRadii.max() ?? view.radius),
                              "border_widths": view.widths.map { Double($0) },
                              "border_styles": view.widths.map { $0 == 0 ? "none" : view.borderDash.isEmpty ? "solid" : "dashed" },
                              "border_colors": Array(repeating: border, count: 4), "corner_radii": view.cornerRadii.map { Double($0) },
                              "opacity": opacity, "background_image": "none", "shadow": shadows],
                    "evidence": ["source": "live-native-surface-probe", "renderer": "UnevenRoundedRectangle.fill/strokeBorder, optional edge Rectangles and clipped leading inset", "attachment": "production ViewModifier", "identity": view.identity, "native_shadow_radii": view.shadows.map { Double($0.radius) }, "border_dash": view.borderDash.map { Double($0) }, "shadow_radius_unit": "SwiftUI Gaussian radius; CSS blur diameter is twice the radius"]]
        }
    }
    final class SurfaceView: NSView {
        let identity = UUID().uuidString
        var fill = NSColor.clear, border = NSColor.clear
        var width: CGFloat = 0, radius: CGFloat = 0, opacity: Double = 1
        var widths: [CGFloat] = [0,0,0,0]
        var kind: String?, owner: String?, hovered: Bool?
        var separateEdges = false
        var shadows: [SurfaceShadow] = []
        var cornerRadii: [CGFloat] = [0,0,0,0]
        var insetLeadingWidth: CGFloat = 0
        var insetLeadingColor = NSColor.clear
        var borderDash: [CGFloat] = []
        var selected: Bool?, expanded: Bool?, current: Bool?
        var region = "window"
        var insetRingWidth: CGFloat = 0, outerRingWidth: CGFloat = 0
        var insetRingColor = NSColor.clear, outerRingColor = NSColor.clear
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
