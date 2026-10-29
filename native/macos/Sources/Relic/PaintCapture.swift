import AppKit
import SwiftUI

// A transparent measuring view attached to the production shape, using the same
// resource and color that draw it. It adds neither paint nor an AX element.
struct ElementPaintProbe: NSViewRepresentable {
    let name: String
    let size: CGFloat
    let color: Color
    let owner: String?
    private static let live = NSHashTable<PaintView>.weakObjects()
    func makeNSView(context: Context) -> PaintView { let view = PaintView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: PaintView, context: Context) { view.name = name; view.size = size; view.color = NSColor(color); view.owner = owner }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor, let source = ReferenceIcons.paths[view.name] else { return nil }
            let screen = window.convertToScreen(view.convert(view.bounds, to: nil))
            let rect = ElementCapture.topLeft(screen, in: content)
            var foreground: Any = NSNull()
            window.effectiveAppearance.performAsCurrentDrawingAppearance { foreground = ElementCapture.rgba(view.color) }
            let dimension = String(format: "%g", Double(view.size))
            func json(_ value: Any) -> String { String(data: try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]), encoding: .utf8)! }
            let glyph = #"{"tag":"svg","attributes":"# + json(["height": dimension, "viewBox": "0 0 24 24", "width": dimension]) + #","children":[{"tag":"path","attributes":"# + json(["d": source]) + #","children":[]}]}"#
            return ["id": "paint/" + view.identity, "owner": view.owner as Any? ?? NSNull(), "rect": ElementCapture.box(rect),
                    "screenRect": NSValue(rect: screen), "foreground": foreground,
                    "icon": ["source": "svg", "glyph": glyph],
                    "evidence": ["source": "live-NSView-shape-probe", "renderer": "SwiftUI.Shape/CoreGraphics", "resource": view.name, "path": source, "viewBox": "0 0 24 24", "stroke_width": 1.7 * Double(view.size) / 24, "line_cap": "round", "line_join": "round"]]
        }
    }
    final class PaintView: NSView {
        let identity = UUID().uuidString
        var name = "", size: CGFloat = 0, color = NSColor.clear
        var owner: String?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
