import SwiftUI
import AppKit

/// Inspect the actual mounted, clipped native views in CI. A timer or an empty
/// task counter alone cannot prove that the visible Markdown was prepared.
@MainActor struct RenderReadiness: NSViewRepresentable {
    let kind: String
    var ready = true
    static var enabled: Bool { VisualCapture.enabled || TitlebarCapture.enabled || ResponsivenessCapture.enabled }
    private static let live = NSHashTable<Probe>.weakObjects()
    func makeNSView(context: Context) -> Probe {
        let view = Probe(); Self.live.add(view); updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: Probe, context: Context) { view.kind = kind; view.ready = ready }
    static func observation(in window: NSWindow, expectInspector: Bool) -> Observation {
        let views = live.allObjects.filter { $0.window === window && $0.visibleInViewport }
        let markdown = views.filter { $0.kind == "markdown" }
        return Observation(markdown: markdown.count, pendingMarkdown: markdown.filter { !$0.ready }.count,
            inspectors: views.filter { $0.kind == "inspector" }.count, expectInspector: expectInspector)
    }
    struct Observation {
        let markdown: Int, pendingMarkdown: Int, inspectors: Int
        let expectInspector: Bool
        var ready: Bool { pendingMarkdown == 0 && (!expectInspector || inspectors == 1) }
        var record: [String: Any] { ["visible_markdown": markdown, "unprepared_visible_markdown": pendingMarkdown,
            "visible_inspectors": inspectors, "inspector_expected": expectInspector, "ready": ready] }
    }
    final class Probe: NSView {
        var kind = "", ready = false
        var visibleInViewport: Bool {
            guard !isHiddenOrHasHiddenAncestor else { return false }
            var rect = bounds, ancestor = superview
            while let view = ancestor {
                // AppKit visibleRect alone can include a document's offscreen
                // children. Intersect the actual native scrolling viewport.
                if view is NSClipView || view.clipsToBounds {
                    rect = rect.intersection(convert(view.bounds, from: view))
                }
                ancestor = view.superview
            }
            if let root = window?.contentView { rect = rect.intersection(convert(root.bounds, from: root)) }
            return !rect.isNull && rect.width > 1 && rect.height > 1
        }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
