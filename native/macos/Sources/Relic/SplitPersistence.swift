import AppKit
import SwiftUI

// Use the native split view's divider movement; persist its actual measured widths.
struct SplitPersistence: NSViewRepresentable {
    @EnvironmentObject var m: Model
    func makeNSView(context: Context) -> Probe { let view = Probe(); view.configure(m); return view }
    func updateNSView(_ nsView: Probe, context: Context) { nsView.configure(m) }
    static func dismantleNSView(_ nsView: Probe, coordinator: ()) { nsView.detach() }
    final class Probe: NSView {
        weak var model: Model?
        weak var split: NSSplitView?
        private var signature = ""
        private var panelKey = ""
        private var hasSidebar = false
        private var hasPanel = false
        private var restoring = false
        private var queued = false
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        func configure(_ model: Model) { self.model = model; schedule() }
        override func viewDidMoveToWindow() { schedule() }
        private func schedule() {
            guard !queued else { return }; queued = true
            DispatchQueue.main.async { [weak self] in self?.queued = false; self?.attach() }
        }
        private func attach() {
            guard window != nil, let model else { return }
            var ancestor = superview
            while ancestor != nil && !(ancestor is NSSplitView) { ancestor = ancestor?.superview }
            guard let found = ancestor as? NSSplitView else { return }
            if found !== split {
                detach(); split = found
                found.autosaveName = "Relic.MainColumns"
                NotificationCenter.default.addObserver(self, selector: #selector(resized), name: NSSplitView.didResizeSubviewsNotification, object: found)
            }
            let key = model.pane == "files" ? "width.files" : "width.panel"
            let next = "\(model.sidebarOpen)/\(model.panelOpen)/\(Int(found.bounds.width))/" + key
            guard signature != next, found.bounds.width > 0 else { return }
            signature = next; panelKey = key; hasSidebar = model.sidebarOpen; hasPanel = model.panelOpen
            restoring = true; defer { restoring = false }
            if let controller = found.delegate as? NSSplitViewController {
                for (index, item) in controller.splitViewItems.enumerated() {
                    let flexible = index == (hasSidebar ? 1 : 0)
                    item.holdingPriority = NSLayoutConstraint.Priority(flexible ? 250 : 750)
                }
            }
            if hasSidebar, found.subviews.count >= 2 {
                let saved = model.defaults.double(forKey: "width.sidebar")
                found.setPosition(min(320, max(208, saved > 0 ? saved : 276)), ofDividerAt: 0)
            }
            if hasPanel, found.subviews.count >= 2 {
                let saved = model.defaults.double(forKey: key), width = saved > 0 ? saved : key == "width.files" ? 460 : 320
                let available = max(280, found.bounds.width - (hasSidebar ? 208 : 0) - 320)
                found.setPosition(found.bounds.width - min(740, available, max(280, width)) - found.dividerThickness, ofDividerAt: found.subviews.count - 2)
            }
        }
        @objc private func resized() {
            guard !restoring, !signature.isEmpty, let model, let split, split.subviews.count >= 2 else { return }
            if hasSidebar, model.sidebarOpen, let first = split.subviews.first, first.frame.width >= 200 { model.defaults.set(first.frame.width, forKey: "width.sidebar") }
            if hasPanel, model.panelOpen, let last = split.subviews.last, last.frame.width >= 270 { model.defaults.set(last.frame.width, forKey: panelKey) }
        }
        func detach() { NotificationCenter.default.removeObserver(self); split = nil; signature = "" }
        deinit { NotificationCenter.default.removeObserver(self) }
    }
}
