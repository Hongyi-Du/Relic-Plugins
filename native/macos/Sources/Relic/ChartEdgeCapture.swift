import AppKit
import SwiftUI
import RelicCore

struct ChartEdge {
    let path: String
    let color: Color
    let width: CGFloat
    let dash: [CGFloat]
    let opacity: Double
    var tip = ""
}
struct ChartEdgeView: View {
    let edge: ChartEdge
    let plane: CGSize
    let index: Int
    var body: some View {
        if let path = try? VectorPath.parse(edge.path) {
            Path(path).stroke(edge.color, style: StrokeStyle(lineWidth: edge.width, dash: edge.dash)).opacity(edge.opacity)
                .frame(width: plane.width, height: plane.height)
                .contentShape(Path(path).strokedPath(StrokeStyle(lineWidth: edge.width)))
                .background(ChartEdgeProbe(edge: edge, path: path, index: index)).help(edge.tip).allowsHitTesting(!edge.tip.isEmpty)
        }
    }
}
struct ChartEdgeProbe: NSViewRepresentable {
    @Environment(\.captureRegion) private var region
    let edge: ChartEdge
    let path: CGPath
    let index: Int
    private static let live = NSHashTable<EdgeView>.weakObjects()
    func makeNSView(context: Context) -> EdgeView { let view = EdgeView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: EdgeView, context: Context) { view.edge = edge; view.path = path; view.index = index; view.region = region }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.sorted { $0.index < $1.index }.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor, let edge = view.edge, let path = view.path else { return nil }
            let rect = ElementCapture.topLeft(window.convertToScreen(view.convert(path.boundingBoxOfPath, to: nil)), in: content)
            let frame = window.convertToScreen(view.convert(view.bounds, to: nil))
            let sx = frame.width / max(0.01, view.bounds.width), sy = frame.height / max(0.01, view.bounds.height)
            var color: Any = NSNull()
            view.effectiveAppearance.performAsCurrentDrawingAppearance { color = ElementCapture.rgba(NSColor(edge.color)) }
            let glyph: [String: Any] = ["tag": "path", "attributes": ["d": edge.path], "children": []]
            let encoded = String(data: try! JSONSerialization.data(withJSONObject: glyph, options: [.sortedKeys, .withoutEscapingSlashes]), encoding: .utf8)!
            return ["id": "chart-edge/" + view.identity, "rectValue": NSValue(rect: rect), "color": color, "opacity": edge.opacity, "width": Double(edge.width * sx), "region": view.region, "icon": ["source": "svg", "glyph": encoded],
                    "evidence": ["source": "live-native-chart-path", "renderer": "SwiftUI.Path/CoreGraphics", "path": edge.path, "source_width": Double(edge.width), "scale_x": Double(sx), "scale_y": Double(sy), "stroke_dash": edge.dash.map { Double($0) }, "stroke_dash_offset": 0, "stroke_linecap": "butt", "stroke_linejoin": "miter", "native_layer_order": view.index]]
        }
    }
    final class EdgeView: NSView {
        let identity = UUID().uuidString
        var edge: ChartEdge?, path: CGPath?
        var index = 0
        var region = "window"
        override var isFlipped: Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
