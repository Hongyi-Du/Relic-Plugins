import AppKit
import SwiftUI

// The production icon renderer. Receipts are recorded by the same CoreGraphics
// draw that strokes the visible path, rather than by a neighboring measuring
// view. The icon stays AX-hidden; its real owning control supplies interaction.
struct ElementPaintProbe: NSViewRepresentable {
    @Environment(\.captureRegion) private var region
    let name: String
    let size: CGFloat
    let color: Color
    let owner: String?
    let opacity: Double
    private static let live = NSHashTable<PaintView>.weakObjects()
    func makeNSView(context: Context) -> PaintView { let view = PaintView(frame: .zero); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: PaintView, context: Context) {
        view.configure(name: name, size: size, color: NSColor(color))
        view.owner = owner; view.opacity = opacity; view.region = region
    }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor, let source = ReferenceIcons.paths[view.name] else { return nil }
            let screen = window.convertToScreen(view.convert(view.bounds, to: nil))
            let rect = ElementCapture.topLeft(screen, in: content)
            let clip = NativeVisibility.screenClip(view).map { $0.isNull ? NSRect.null : ElementCapture.topLeft($0, in: content) } ?? .null
            let draw = view.currentDraw()
            let outline = IconOutlineCapture.inspect(view)
            let foreground: Any = draw?["foreground"] ?? NSNull()
            let dimension = String(format: "%g", Double(view.size))
            func json(_ value: Any) -> String { String(data: try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]), encoding: .utf8)! }
            let glyph = #"{"tag":"svg","attributes":"# + json(["height": dimension, "viewBox": "0 0 24 24", "width": dimension]) + #","children":[{"tag":"path","attributes":"# + json(["d": source]) + #","children":[]}]}"#
            return ["id": "paint/" + view.identity, "owner": view.owner as Any? ?? NSNull(), "rect": ElementCapture.box(rect), "region": view.region,
                    "screenRect": NSValue(rect: screen), "nativeVisibleBounds": clip.isNull ? NSNull() : ElementCapture.box(clip), "foreground": foreground, "opacity": NativeVisibility.opacity(view),
                    "native_structure": NativeElementStructure.evidence(view, parent: view.owner),
                    "icon": draw == nil ? NSNull() : ["source": "svg", "glyph": glyph] as Any,
                    "stroke_width": draw?["stroke_width"] ?? NSNull(),
                    "outline": outline.paint,
                    "evidence": ["source": "production CoreGraphics icon draw", "renderer": "final native PaintView.draw",
                        "resource": view.name, "path": source, "viewBox": "0 0 24 24",
                        "current_draw": draw as Any? ?? NSNull(), "last_draw": view.lastDraw as Any? ?? NSNull(),
                        "native_icon_outline": outline.evidence,
                        "draw_binding_valid": draw != nil, "presentation_identity_proven": false,
                        "declared_swiftui_opacity": view.opacity, "native_opacity_ancestry": NativeVisibility.opacityAncestry(view)]]
        }
    }
    final class PaintView: NSView {
        let identity = UUID().uuidString
        private(set) var name = "", size: CGFloat = 0, color = NSColor.clear
        var owner: String?
        var opacity: Double = 1
        var region = "window"
        var recordDraws = VisualCapture.enabled
        private var revision = 0, drawSequence = 0
        private(set) var lastDraw: [String: Any]?
        override var isFlipped: Bool { true }
        override init(frame: NSRect) { super.init(frame: frame); focusRingType = .none }
        required init?(coder: NSCoder) { super.init(coder: coder); focusRingType = .none }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        func configure(name: String, size: CGFloat, color: NSColor) {
            guard self.name != name || self.size != size || self.color != color else { return }
            self.name = name; self.size = size; self.color = color
            revision += 1; needsDisplay = true
        }
        override func draw(_ dirtyRect: NSRect) {
            guard let source = ReferenceIcons.paths[name], let path = try? VectorPath.parse(source),
                  let context = NSGraphicsContext.current?.cgContext else { return }
            var transform = CGAffineTransform(scaleX: bounds.width / 24, y: bounds.height / 24)
                .concatenating(CGAffineTransform(translationX: bounds.minX, y: bounds.minY))
            guard let rendered = path.copy(using: &transform) else { return }
            let width = 1.7 * size / 24
            context.saveGState()
            context.setShouldAntialias(true)
            context.setLineWidth(width); context.setLineCap(.round); context.setLineJoin(.round)
            context.setLineDash(phase: 0, lengths: [])
            let foreground = color.usingColorSpace(.sRGB) ?? color
            context.setStrokeColor(foreground.cgColor)
            context.addPath(rendered); context.strokePath()
            context.restoreGState()
            if recordDraws {
                var commands: [[String: Any]] = []
                rendered.applyWithBlock { pointer in
                    let element = pointer.pointee
                    let count: Int
                    switch element.type {
                    case .moveToPoint, .addLineToPoint: count = 1
                    case .addQuadCurveToPoint: count = 2
                    case .addCurveToPoint: count = 3
                    case .closeSubpath: count = 0
                    @unknown default: count = 0
                    }
                    commands.append(["type": element.type.rawValue, "points": (0..<count).map { [element.points[$0].x, element.points[$0].y] }])
                }
                drawSequence += 1
                lastDraw = ["provider": "production PaintView.draw / CGContext.strokePath", "draw_returned": true,
                    "view_identity": String(describing: ObjectIdentifier(self)),
                    "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                    "revision": revision, "sequence": drawSequence, "resource": name, "source_path": source,
                    "local_bounds": ElementCapture.box(bounds), "rendered_path_bounds": ElementCapture.box(rendered.boundingBoxOfPath),
                    "rendered_path_commands": commands, "foreground": ElementCapture.rgba(foreground),
                    "stroke_width": width, "stroke_dash": [], "stroke_dash_offset": 0,
                    "line_cap": "round", "line_join": "round", "should_antialias": true,
                    "presentation_identity_proven": false]
            }
        }
        func currentDraw() -> [String: Any]? {
            guard let window, window.isVisible, !isHiddenOrHasHiddenAncestor, let draw = lastDraw,
                  draw["revision"] as? Int == revision, draw["draw_returned"] as? Bool == true,
                  draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
                  draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
                  ElementCapture.rect(draw["local_bounds"]) == bounds else { return nil }
            var currentColor: [Double]?
            effectiveAppearance.performAsCurrentDrawingAppearance { currentColor = ElementCapture.rgba(color) as? [Double] }
            guard let currentColor, let drawnColor = draw["foreground"] as? [Double], currentColor == drawnColor else { return nil }
            return draw
        }
    }
}
