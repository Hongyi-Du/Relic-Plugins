import AppKit

/// CI observation only: how far the row being read moved when the
/// conversation window changed around it. Before a window change the stream
/// records that row's distance from its viewport edge (the latest row's from
/// the bottom while following the latest message, the first shown row's from
/// the top while paging older history). When AppKit's update resizes the
/// document (after the conversation's own correction there), or else at the
/// stream's next update, it records the distance again: any difference is
/// movement the next displayed frame shows. "kind/settled" measures once more
/// at the stream's next update, after the stream's own scroll requests.
@MainActor enum ReadingPositionTrace {
    private struct Pending { let kind: String, row: String, top: Bool, offset: CGFloat }
    private struct Totals { var steps = 0, unmeasured = 0, moved = 0; var largest = 0.0 }
    private static var pending: Pending?
    /// Measured again at the stream's next update: whether the position seen
    /// right after AppKit's update is still where the reader left it.
    private static var verifying: Pending?
    private static var action: [String: Totals] = [:]
    private static var phase: [String: Totals] = [:]

    static func before(_ kind: String, row: String, top: Bool, scroll: NSScrollView?) {
        guard ResponsivenessCapture.enabled else { return }
        guard let scroll, let offset = offset(of: row, top: top, in: scroll) else {
            pending = nil; add(kind) { $0.unmeasured += 1 }; return
        }
        pending = Pending(kind: kind, row: row, top: top, offset: offset)
    }

    static func after(scroll: NSScrollView?) {
        guard let current = pending else { return }
        pending = nil; verifying = current
        record(current, kind: current.kind, scroll: scroll)
    }

    /// The stream's next update, after any scroll of its own was requested.
    static func settle(scroll: NSScrollView?) {
        guard let current = verifying else { return }
        verifying = nil
        record(current, kind: current.kind + "/settled", scroll: scroll)
    }

    private static func record(_ current: Pending, kind: String, scroll: NSScrollView?) {
        guard let scroll, let offset = offset(of: current.row, top: current.top, in: scroll) else {
            add(kind) { $0.unmeasured += 1 }; return
        }
        let shift = Double(abs(offset - current.offset))
        add(kind) {
            $0.steps += 1; $0.largest = max($0.largest, shift)
            if shift > 1 { $0.moved += 1 }
        }
    }

    /// The window changes observed since the previous call, for one action's receipt.
    static func take() -> [String: Any] {
        defer { action = [:] }
        return record(action)
    }

    static func summary() -> [String: Any] { record(phase) }

    private static func add(_ kind: String, _ change: (inout Totals) -> Void) {
        change(&action[kind, default: Totals()]); change(&phase[kind, default: Totals()])
    }

    private static func record(_ values: [String: Totals]) -> [String: Any] {
        values.mapValues { ["steps": $0.steps, "moved": $0.moved, "unmeasured": $0.unmeasured,
                            "largest_shift_pt": ($0.largest * 10).rounded() / 10] }
    }

    /// The row's distance from the top or bottom edge of the visible clip,
    /// measured through its mounted readiness probe.
    private static func offset(of row: String, top: Bool, in scroll: NSScrollView) -> CGFloat? {
        guard let window = scroll.window,
              let probe = RenderReadiness.probes(in: window).first(where: { $0.kind == "conversation-row" && $0.identity == row }),
              !probe.isHiddenOrHasHiddenAncestor else { return nil }
        let clip = scroll.contentView, visible = clip.bounds
        let rect = probe.convert(probe.bounds, to: clip)
        if clip.isFlipped { return top ? rect.minY - visible.minY : visible.maxY - rect.maxY }
        return top ? visible.maxY - rect.maxY : rect.minY - visible.minY
    }
}
