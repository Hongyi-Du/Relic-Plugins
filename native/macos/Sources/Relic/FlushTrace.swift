import AppKit

/// CI diagnosis only. Splits a display flush into the passes AppKit runs for
/// the capture window and the conversation table's own work, so a probe that
/// waited behind one flush names the pass that held it:
/// - flush.constraints, flush.layout, flush.display: the window's update
///   constraints, layout and display passes (layout includes SwiftUI's
///   render of the root view and every list row's layout);
/// - table.end-updates: a table applying a batch of inserted and removed
///   rows, with the automatic heights of the inserted and visible rows;
/// - table.layout: a table's own layout (tiling its visible rows).
@MainActor enum FlushTrace {
    private static var installed = false
    static func install(output: URL) {
        guard UIWorkTrace.enabled, !installed else { return }
        installed = true
        exchange(#selector(NSTableView.endUpdates), with: #selector(NSTableView.relicTracedEndUpdates))
        exchange(#selector(NSView.layout), with: #selector(NSTableView.relicTracedLayout))
        // The main run loop's observers (activities, order, callout), which
        // name the parts UIWorkTrace.observeRunLoop records by order.
        let description = (CFCopyDescription(CFRunLoopGetMain()) as String?) ?? ""
        var seen = Set<String>(), lines: [String] = []
        for line in description.components(separatedBy: "\n") where line.contains("CFRunLoopObserver") {
            let text = line.trimmingCharacters(in: .whitespaces)
            if seen.insert(text).inserted { lines.append(text) }
        }
        try? lines.joined(separator: "\n").write(to: output.appendingPathComponent("runloop-observers.txt"), atomically: true, encoding: .utf8)
    }
    /// Only a method NSTableView implements itself: an inherited NSView method
    /// is never exchanged.
    private static func exchange(_ original: Selector, with traced: Selector) {
        guard let own = class_getInstanceMethod(NSTableView.self, original),
              own != class_getInstanceMethod(NSView.self, original),
              let replacement = class_getInstanceMethod(NSTableView.self, traced) else { return }
        method_exchangeImplementations(own, replacement)
    }
}

extension NSTableView {
    /// CI only: exchanged with `endUpdates`; calls the original under a trace.
    @objc dynamic fileprivate func relicTracedEndUpdates() {
        let trace = UIWorkTrace.begin("table.end-updates"); defer { UIWorkTrace.end(trace) }
        relicTracedEndUpdates()
    }
    /// CI only: exchanged with NSTableView's own `layout`.
    @objc dynamic fileprivate func relicTracedLayout() {
        let trace = UIWorkTrace.begin("table.layout"); defer { UIWorkTrace.end(trace) }
        relicTracedLayout()
    }
}

/// CI only: the capture window, timing the passes its display cycle runs.
final class TracedWindow: NSWindow {
    override func updateConstraintsIfNeeded() {
        let trace = UIWorkTrace.begin("flush.constraints"); defer { UIWorkTrace.end(trace) }
        super.updateConstraintsIfNeeded()
    }
    override func layoutIfNeeded() {
        let trace = UIWorkTrace.begin("flush.layout"); defer { UIWorkTrace.end(trace) }
        super.layoutIfNeeded()
    }
    override func displayIfNeeded() {
        let trace = UIWorkTrace.begin("flush.display"); defer { UIWorkTrace.end(trace) }
        super.displayIfNeeded()
    }
}
