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
    var unread: Bool? = nil
    var insetRingWidth: CGFloat = 0
    var insetRingColor: Color = .clear
    var outerRingWidth: CGFloat = 0
    var outerRingColor: Color = .clear
    var rings: [SurfaceRing] = []
    var outline: SurfaceOutline? = nil
    var nativeFill = false
    var nativeFillComponentBits = 8
    @State private var cardIdentity = "relic-card/" + UUID().uuidString
    @State private var hoverObservation = NativeSurfaceHover()
    @Environment(\.captureOpacity) private var opacity
    private var surfaceOwner: String? { owner ?? (kind == "card" ? cardIdentity : nil) }
    @ViewBuilder private func ownedContent(_ content: Content) -> some View {
        if kind == "card" && owner == nil {
            // The painted production card owns a real native accessibility
            // container at this exact position in the view hierarchy. Keep
            // its controls/text as children, so order is measured from AX
            // rather than appending an anonymous paint surface after the tree.
            content.accessibilityElement(children: .contain)
                .accessibilityIdentifier(cardIdentity).accessibilityLabel("")
        } else { content }
    }
    private var shape: UnevenRoundedRectangle {
        let corners = cornerRadii ?? Array(repeating: radius, count: 4)
        return UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3], bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular)
    }
    private var shadowOutset: CGFloat {
        shadows.map { $0.radius * 3 + max(abs($0.x), abs($0.y)) }.max() ?? 0
    }
    func body(content: Content) -> some View {
        ownedContent(content).background {
            // CSS box shadows belong to the surface outline. Applying SwiftUI
            // shadow to the content hierarchy also shadows fields/text inside
            // dialogs. Paint each shadow from the same background shape instead.
            if nativeFill {
                ZStack {
                    if !shadows.isEmpty {
                        ZStack {
                            ForEach(Array(shadows.enumerated().reversed()), id: \.offset) { _, value in
                                shape.fill(background).shadow(color: value.color, radius: value.radius, x: value.x, y: value.y)
                            }
                        }.padding(shadowOutset).drawingGroup(opaque: false, colorMode: .nonLinear).padding(-shadowOutset)
                    }
                // Keep AppKit's original fill path when SwiftUI composites
                // shadows. Quantizing that fill into another 8-bit image first
                // changed its antialiased border pixels in the mounted test.
                NativeSurfaceFill(color: background, corners: cornerRadii ?? Array(repeating: radius, count: 4), owner: surfaceOwner,
                    ownedLayer: shadows.isEmpty || nativeFillComponentBits > 8, componentBits: nativeFillComponentBits)
                }
            } else if shadows.isEmpty { shape.fill(background) }
            else {
                ZStack {
                    ForEach(Array(shadows.enumerated().reversed()), id: \.offset) { _, value in
                        shape.fill(background).shadow(color: value.color, radius: value.radius, x: value.x, y: value.y)
                    }
                    shape.fill(background)
                }
                // Keep translucent shadow layers in the reference's non-linear
                // sRGB blending space. AppKit controls remain outside this
                // shape-only raster group and retain their actual native draws.
                // A drawingGroup raster is limited to its layout bounds. Give
                // the actual blur kernel/offset room, then restore the original
                // surface layout size; otherwise every outside shadow is clipped.
                .padding(shadowOutset)
                .drawingGroup(opaque: false, colorMode: .nonLinear)
                .padding(-shadowOutset)
            }
        }
            .overlay {
                if let edges {
                    if borderDash.isEmpty {
                        ZStack {
                            border.frame(height: edges.top).frame(maxHeight: .infinity, alignment: .top)
                            border.frame(width: edges.trailing).frame(maxWidth: .infinity, alignment: .trailing)
                            border.frame(height: edges.bottom).frame(maxHeight: .infinity, alignment: .bottom)
                            border.frame(width: edges.leading).frame(maxWidth: .infinity, alignment: .leading)
                        }.allowsHitTesting(false)
                    } else {
                        GeometryReader { proxy in
                            ZStack {
                                if edges.top > 0 { Path { p in p.move(to: CGPoint(x: 0, y: edges.top / 2)); p.addLine(to: CGPoint(x: proxy.size.width, y: edges.top / 2)) }.stroke(border, style: StrokeStyle(lineWidth: edges.top, dash: borderDash)) }
                                if edges.trailing > 0 { Path { p in p.move(to: CGPoint(x: proxy.size.width - edges.trailing / 2, y: 0)); p.addLine(to: CGPoint(x: proxy.size.width - edges.trailing / 2, y: proxy.size.height)) }.stroke(border, style: StrokeStyle(lineWidth: edges.trailing, dash: borderDash)) }
                                if edges.bottom > 0 { Path { p in p.move(to: CGPoint(x: 0, y: proxy.size.height - edges.bottom / 2)); p.addLine(to: CGPoint(x: proxy.size.width, y: proxy.size.height - edges.bottom / 2)) }.stroke(border, style: StrokeStyle(lineWidth: edges.bottom, dash: borderDash)) }
                                if edges.leading > 0 { Path { p in p.move(to: CGPoint(x: edges.leading / 2, y: 0)); p.addLine(to: CGPoint(x: edges.leading / 2, y: proxy.size.height)) }.stroke(border, style: StrokeStyle(lineWidth: edges.leading, dash: borderDash)) }
                            }
                        }.allowsHitTesting(false)
                    }
                } else { shape.strokeBorder(border, style: StrokeStyle(lineWidth: borderWidth, dash: borderDash)).allowsHitTesting(false) }
            }
            .overlay { if insetLeadingWidth > 0 { insetLeadingColor.frame(width: insetLeadingWidth).frame(maxWidth: .infinity, alignment: .leading).clipShape(shape).allowsHitTesting(false) } }
            .overlay { if insetRingWidth > 0 { shape.inset(by: borderWidth).strokeBorder(insetRingColor, lineWidth: insetRingWidth).allowsHitTesting(false) } }
            .background {
                if outerRingWidth > 0 {
                    RoundedRectangle(cornerRadius: radius + outerRingWidth).strokeBorder(outerRingColor, lineWidth: outerRingWidth).padding(-outerRingWidth).allowsHitTesting(false)
                }
                ZStack {
                    ForEach(Array(rings.enumerated().reversed()), id: \.offset) { _, ring in
                        RoundedRectangle(cornerRadius: radius + ring.width, style: .circular)
                            .strokeBorder(ring.color, lineWidth: ring.width).padding(-ring.width)
                    }
                }.allowsHitTesting(false)
            }
            .overlay(SurfacePaintProbe(background: background, border: border, borderWidth: borderWidth, radius: radius, edges: edges, opacity: opacity, kind: kind, owner: surfaceOwner, hovered: hovered, shadows: shadows, cornerRadii: cornerRadii, insetLeadingWidth: insetLeadingWidth, insetLeadingColor: insetLeadingColor, borderDash: borderDash, selected: selected, expanded: expanded, current: current, unread: unread, insetRingWidth: insetRingWidth, insetRingColor: insetRingColor, outerRingWidth: outerRingWidth, outerRingColor: outerRingColor, rings: rings, outline: outline, hoverObservation: hoverObservation).padding(-(outline?.outset ?? 0)).allowsHitTesting(false))
            .onHover { hoverObservation.received($0) }
    }
}

struct SurfaceRing {
    let width: CGFloat
    let color: Color
}

struct SurfaceOutline: Equatable {
    let width: CGFloat
    let color: Color
    let dash: [CGFloat]
    var phase: CGFloat = 0
    // CSS outline-offset measures from the owner's outside edge to the
    // outline's inside edge. Existing avatar outlines remain wholly inset.
    var offset: CGFloat? = nil
    var effectiveOffset: CGFloat { offset ?? -width }
    var outset: CGFloat { max(0, effectiveOffset + width) }
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
    @Environment(\.nativeElementParent) private var nativeParent
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
    let unread: Bool?
    let insetRingWidth: CGFloat, insetRingColor: Color, outerRingWidth: CGFloat, outerRingColor: Color
    let rings: [SurfaceRing]
    let outline: SurfaceOutline?
    var hoverObservation: NativeSurfaceHover? = nil
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
        view.selected = selected; view.expanded = expanded; view.current = current; view.unread = unread
        view.region = region
        view.productionParent = nativeParent
        view.insetRingWidth = insetRingWidth; view.insetRingColor = NSColor(insetRingColor)
        view.outerRingWidth = outerRingWidth; view.outerRingColor = NSColor(outerRingColor)
        view.rings = rings
        view.configureOutline(outline, corners: view.cornerRadii)
        view.hoverObservation = hoverObservation
    }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor else { return nil }
            let rect = ElementCapture.topLeft(window.convertToScreen(view.convert(view.surfaceBounds, to: nil)), in: content)
            let clip = NativeVisibility.screenClip(view).map { $0.isNull ? NSRect.null : ElementCapture.topLeft($0, in: content).intersection(rect) } ?? .null
            var fill: Any = NSNull(), border: Any = NSNull(), shadows: [[String: Any]] = [], outline: Any = NSNull()
            view.effectiveAppearance.performAsCurrentDrawingAppearance {
                fill = ElementCapture.rgba(view.fill); border = ElementCapture.rgba(view.border)
                shadows = view.shadows.map { ["inset": false, "offset_x": Double($0.x), "offset_y": Double($0.y), "blur_radius": Double($0.radius * 2), "spread_radius": 0, "color": ElementCapture.rgba(NSColor($0.color))] }
                if view.insetLeadingWidth > 0 { shadows.insert(["inset": true, "offset_x": Double(view.insetLeadingWidth), "offset_y": 0, "blur_radius": 0, "spread_radius": 0, "color": ElementCapture.rgba(view.insetLeadingColor)], at: 0) }
                if view.insetRingWidth > 0 { shadows.append(["inset": true, "offset_x": 0, "offset_y": 0, "blur_radius": 0, "spread_radius": Double(view.insetRingWidth), "color": ElementCapture.rgba(view.insetRingColor)]) }
                if view.outerRingWidth > 0 { shadows.append(["inset": false, "offset_x": 0, "offset_y": 0, "blur_radius": 0, "spread_radius": Double(view.outerRingWidth), "color": ElementCapture.rgba(view.outerRingColor)]) }
                shadows.append(contentsOf: view.rings.map { ["inset": false, "offset_x": 0, "offset_y": 0, "blur_radius": 0, "spread_radius": Double($0.width), "color": ElementCapture.rgba(NSColor($0.color))] })
                if let value = view.outline {
                    outline = ["width": Double(value.width), "color": ElementCapture.rgba(NSColor(value.color)),
                        "dash": value.dash.map(Double.init), "offset": Double(value.effectiveOffset),
                        "renderer": "Separate native outline stroke; not a layout border"]
                }
            }
            let outlineDraw = view.outlineReceipt(in: content)
            // SwiftUI materializes its opacity on the representable's native
            // ancestry. The environment value describes that SAME operation;
            // multiplying it again reports .35 squared for a .35 surface.
            let opacity = NativeVisibility.opacity(view)
            return ["rectValue": NSValue(rect: rect), "bounds": ElementCapture.box(rect), "nativeVisibleBounds": clip.isNull ? NSNull() : ElementCapture.box(clip), "region": view.region,
                    "owner": view.owner as Any? ?? NSNull(), "kind": view.kind as Any? ?? NSNull(), "hovered": (view.hovered ?? view.hoverObservation?.value) as Any? ?? NSNull(),
                    "native_hover_callbacks": view.hoverObservation?.observation() as Any? ?? NSNull(),
                    "native_structure": NativeElementStructure.evidence(view, parent: view.productionParent),
                    "selected": view.selected as Any? ?? NSNull(), "expanded": view.expanded as Any? ?? NSNull(), "current": view.current as Any? ?? NSNull(),
                    "unread": view.unread as Any? ?? NSNull(),
                    "style": ["backgroundColor": fill, "borderColor": border, "borderWidth": Double(view.widths.max() ?? view.width), "borderRadius": Double(view.cornerRadii.max() ?? view.radius),
                              "border_widths": view.widths.map { Double($0) },
                              "border_styles": view.widths.map { $0 == 0 ? "none" : view.borderDash.isEmpty ? "solid" : "dashed" },
                              "border_colors": Array(repeating: border, count: 4), "corner_radii": view.cornerRadii.map { Double($0) },
                              "opacity": opacity, "background_image": "none", "shadow": shadows, "native_outline": outline, "outline": outlineDraw.paint],
                    "evidence": ["source": "live-native-surface-probe", "renderer": "UnevenRoundedRectangle.fill/strokeBorder, optional edge Rectangles and clipped leading inset", "attachment": "production ViewModifier", "identity": view.identity, "probe_local_bounds": ElementCapture.box(view.bounds), "surface_local_bounds": ElementCapture.box(view.surfaceBounds), "outline_draw_outset": Double(view.outline?.outset ?? 0), "declared_swiftui_opacity": view.opacity, "native_opacity_ancestry": NativeVisibility.opacityAncestry(view), "native_shadow_radii": view.shadows.map { Double($0.radius) }, "border_dash": view.borderDash.map { Double($0) }, "shadow_radius_unit": "SwiftUI Gaussian radius; CSS blur diameter is twice the radius", "outline": outlineDraw.evidence]]
        }
    }
    final class SurfaceView: NSView {
        let identity = UUID().uuidString
        var fill = NSColor.clear, border = NSColor.clear
        var width: CGFloat = 0, radius: CGFloat = 0, opacity: Double = 1
        var widths: [CGFloat] = [0,0,0,0]
        var kind: String?, owner: String?, hovered: Bool?
        var hoverObservation: NativeSurfaceHover?
        var productionParent: String?
        var separateEdges = false
        var shadows: [SurfaceShadow] = []
        var cornerRadii: [CGFloat] = [0,0,0,0]
        var insetLeadingWidth: CGFloat = 0
        var insetLeadingColor = NSColor.clear
        var borderDash: [CGFloat] = []
        var selected: Bool?, expanded: Bool?, current: Bool?, unread: Bool?
        var region = "window"
        var insetRingWidth: CGFloat = 0, outerRingWidth: CGFloat = 0
        var rings: [SurfaceRing] = []
        private(set) var outline: SurfaceOutline?
        var surfaceBounds: NSRect { bounds.insetBy(dx: outline?.outset ?? 0, dy: outline?.outset ?? 0) }
        private var outlineCorners: [CGFloat] = [0,0,0,0]
        private(set) var outlineRevision = 0
        private var drawSequence = 0
        private(set) var lastOutlineDraw: OutlineDrawReceipt?
        var recordDraws = VisualCapture.enabled
        var insetRingColor = NSColor.clear, outerRingColor = NSColor.clear
        override var isFlipped: Bool { true }
        override func viewDidChangeEffectiveAppearance() {
            super.viewDidChangeEffectiveAppearance()
            outlineRevision += 1; needsDisplay = true
        }
        func configureOutline(_ value: SurfaceOutline?, corners: [CGFloat]) {
            guard outline != value || outlineCorners != corners else { return }
            outline = value; outlineCorners = corners; outlineRevision += 1; needsDisplay = true
        }
        override func draw(_ dirtyRect: NSRect) {
            guard let outline, let context = NSGraphicsContext.current?.cgContext,
                  let color = NSColor(outline.color).usingColorSpace(.sRGB) else { return }
            let corners = outlineCorners
            let path = UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3],
                bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular)
                .inset(by: -(outline.effectiveOffset + outline.width / 2)).path(in: surfaceBounds).cgPath
            context.saveGState()
            context.setLineWidth(outline.width); context.setLineDash(phase: outline.phase, lengths: outline.dash)
            context.setLineCap(.butt); context.setLineJoin(.miter); context.setStrokeColor(color.cgColor)
            let transform = context.ctm, clip = context.boundingBoxOfClipPath
            context.addPath(path); context.strokePath(); context.restoreGState()
            if recordDraws {
                drawSequence += 1
                lastOutlineDraw = OutlineDrawReceipt(path: path, bounds: bounds, ownerBounds: surfaceBounds, width: outline.width, offset: outline.effectiveOffset,
                    dash: outline.dash, phase: outline.phase,
                    color: [color.redComponent, color.greenComponent, color.blueComponent, color.alphaComponent].map { Double($0 * 255) },
                    contextTransform: transform, contextClip: clip, revision: outlineRevision, sequence: drawSequence,
                    viewIdentity: String(describing: ObjectIdentifier(self)),
                    windowIdentity: window.map { String(describing: ObjectIdentifier($0)) })
            }
        }
        func outlineReceipt(in content: NSRect) -> (paint: Any, evidence: [String: Any]) {
            guard outline != nil else {
                return (NSNull(), ["source": "production surface outline renderer", "absence_proven": false,
                    "errors": ["This surface has no separate outline; other owner focus/template paint is not yet covered"]])
            }
            guard let lastOutlineDraw else {
                return (NSNull(), ["source": "production surface outline renderer", "errors": ["No completed outline draw"]])
            }
            return lastOutlineDraw.projected(view: self, content: content, currentRevision: outlineRevision)
        }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
