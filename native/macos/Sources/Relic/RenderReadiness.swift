import SwiftUI
import AppKit

/// Inspect the actual mounted, clipped native views in CI. A timer or an empty
/// task counter alone cannot prove that the visible Markdown was prepared.
@MainActor struct RenderReadiness: NSViewRepresentable {
    let kind: String
    var ready = true
    var identity: String = ""
    static var enabled: Bool { VisualCapture.enabled || TitlebarCapture.enabled || ResponsivenessCapture.enabled }
    private static let live = NSHashTable<Probe>.weakObjects()
    func makeNSView(context: Context) -> Probe {
        let view = Probe(); Self.live.add(view); updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: Probe, context: Context) { view.kind = kind; view.ready = ready; view.identity = identity }
    static func visibleConversationRows(in window: NSWindow) -> [String] {
        live.allObjects.filter { $0.window === window && $0.kind == "conversation-row" && $0.visibleInViewport }.map(\.identity)
    }
    static func diagnostic(in window: NSWindow) -> [String: Any] {
        let probes: [[String: Any]] = live.allObjects.filter { $0.window === window }.map { view in
            let rect = view.convert(view.bounds, to: window.contentView)
            return ["kind": view.kind, "identity": view.identity, "ready": view.ready, "visible": view.visibleInViewport,
                    "frame": ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height]]
        }
        return ["probes": probes]
    }
    static func observation(in window: NSWindow, expectInspector: Bool, expectDialog: Bool = false) -> Observation {
        let views = live.allObjects.filter { $0.window === window && $0.visibleInViewport }
        let markdown = views.filter { $0.kind == "markdown" }
        return Observation(markdown: markdown.count, pendingMarkdown: markdown.filter { !$0.ready }.count,
            inspectors: views.filter { $0.kind == "inspector" }.count, expectInspector: expectInspector,
            dialogs: views.filter { $0.kind == "dialog" }.count, expectDialog: expectDialog,
            conversationRows: views.filter { $0.kind == "conversation-row" }.count)
    }
    struct Observation {
        let markdown: Int, pendingMarkdown: Int, inspectors: Int
        let expectInspector: Bool
        var dialogs = 0, expectDialog = false
        var conversationRows = 0
        var ready: Bool { pendingMarkdown == 0 && (!expectInspector || inspectors == 1) && dialogs == (expectDialog ? 1 : 0) }
        var record: [String: Any] { ["visible_markdown": markdown, "unprepared_visible_markdown": pendingMarkdown,
            "visible_inspectors": inspectors, "inspector_expected": expectInspector,
            "visible_dialogs": dialogs, "dialog_expected": expectDialog, "ready": ready,
            "visible_conversation_rows": conversationRows] }
    }
    final class Probe: NSView {
        var kind = "", ready = false, identity = ""
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
