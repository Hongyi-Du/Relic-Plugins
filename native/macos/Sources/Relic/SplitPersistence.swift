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
        private var restoreAttempts = 0
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
                // Widths are stored separately for the inspector and file pane.
                // A second NSSplitView autosave record can restore stale geometry.
                found.autosaveName = nil
                NotificationCenter.default.addObserver(self, selector: #selector(resized), name: NSSplitView.didResizeSubviewsNotification, object: found)
            }
            let key = model.pane == "files" ? "width.files" : "width.panel"
            let next = "\(model.sidebarOpen)/\(model.panelOpen)/\(Int(found.bounds.width))/" + key
            guard found.bounds.width > 0 else { return }
            if signature != next { restoreAttempts = 0 }
            let expectedPanel = model.defaults.double(forKey: key)
            let panelWidth = expectedPanel > 0 ? expectedPanel : key == "width.files" ? 520 : 340
            let panelDiffers = model.panelOpen && abs((found.subviews.last?.frame.width ?? 0) - min(740, max(280, panelWidth), max(280, found.bounds.width - (model.sidebarOpen ? 276 : 0) - 320))) > 1
            guard signature != next || panelDiffers && restoreAttempts < 3 else { return }
            restoreAttempts += 1
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
                found.setPosition(min(340, max(276, saved > 0 ? saved : 276)), ofDividerAt: 0)
            }
            if hasPanel, found.subviews.count >= 2 {
                let saved = model.defaults.double(forKey: key), width = saved > 0 ? saved : key == "width.files" ? 520 : 340
                let available = max(280, found.bounds.width - (hasSidebar ? 276 : 0) - 320)
                found.setPosition(found.bounds.width - min(740, available, max(280, width)) - found.dividerThickness, ofDividerAt: found.subviews.count - 2)
            }
            if VisualCapture.enabled { print("Split restoration \(restoreAttempts): target=\(panelWidth), actual=\(found.subviews.map { $0.frame.width }), bounds=\(found.bounds)") }
        }
        @objc private func resized() {
            guard !restoring, !signature.isEmpty, let model, let split, split.subviews.count >= 2 else { return }
            // SwiftUI also posts this notification while changing panes/window size.
            // Only a real divider drag should replace the person's saved widths.
            guard NSEvent.pressedMouseButtons & 1 != 0 else { schedule(); return }
            if hasSidebar, model.sidebarOpen, let first = split.subviews.first, first.frame.width >= 200 { model.defaults.set(first.frame.width, forKey: "width.sidebar") }
            if hasPanel, model.panelOpen, let last = split.subviews.last, last.frame.width >= 270 { model.defaults.set(last.frame.width, forKey: panelKey) }
        }
        func detach() { NotificationCenter.default.removeObserver(self); split = nil; signature = "" }
        deinit { NotificationCenter.default.removeObserver(self) }
    }
}
