import SwiftUI

/// Serialize cold row construction across native display turns. A lazy stack
/// can admit several complex rows in one layout pass even when it recycles
/// offscreen content correctly. No data is removed from the collection.
@MainActor final class RowMountQueue {
    static let shared = RowMountQueue()
    private var active: UUID?
    private var activeTrace: Int?
    private var waiting: [(UUID, CheckedContinuation<Bool, Never>, String, Int)] = []
    var waitingCount: Int { waiting.count }
    var isIdle: Bool { active == nil && waiting.isEmpty }
    func acquire(_ id: UUID, label: String = "row", priority: Int = 0) async -> Bool {
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: false) }
                else if active == nil {
                    active = id; activeTrace = UIWorkTrace.begin("mount-turn." + label)
                    continuation.resume(returning: true)
                }
                else {
                    let position = waiting.firstIndex { $0.3 < priority } ?? waiting.endIndex
                    waiting.insert((id, continuation, label, priority), at: position)
                }
            }
        }, onCancel: { Task { @MainActor in self.cancelWaiting(id) } })
    }
    private func cancelWaiting(_ id: UUID) {
        if let index = waiting.firstIndex(where: { $0.0 == id }) {
            waiting.remove(at: index).1.resume(returning: false)
        }
    }
    func release(_ id: UUID) {
        guard active == id else { return }
        UIWorkTrace.end(activeTrace); activeTrace = nil
        active = nil
        if !waiting.isEmpty {
            let next = waiting.removeFirst(); active = next.0
            activeTrace = UIWorkTrace.begin("mount-turn." + next.2)
            next.1.resume(returning: true)
        }
    }
}

private struct RowMountPriority: EnvironmentKey { static let defaultValue = 0 }
extension EnvironmentValues {
    var rowMountPriority: Int { get { self[RowMountPriority.self] } set { self[RowMountPriority.self] = newValue } }
}

/// A state assignment only requests a SwiftUI update. It does not mean the row
/// has entered the view graph. Do not admit the next cold row until that actual
/// content has appeared, even if an earlier fixed delay has already elapsed.
@MainActor final class RowMountAcknowledgement {
    private var appeared = false
    private var waiter: CheckedContinuation<Bool, Never>?
    func contentAppeared() {
        appeared = true
        let pending = waiter; waiter = nil; pending?.resume(returning: true)
    }
    func wait() async -> Bool {
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: false) }
                else if appeared { continuation.resume(returning: true) }
                else { waiter = continuation }
            }
        }, onCancel: { Task { @MainActor in self.cancel() } })
    }
    private func cancel() {
        let pending = waiter; waiter = nil; pending?.resume(returning: false)
    }
}

struct ProgressiveRow<Content: View>: View {
    @Environment(\.captureRegion) private var region
    @Environment(\.rowMountPriority) private var priority
    var estimatedHeight: CGFloat
    var estimatedWidth: CGFloat? = nil
    var workLabel: String? = nil
    @ViewBuilder var content: () -> Content
    @State private var mounted = false
    @State private var acknowledgement = RowMountAcknowledgement()
    var body: some View {
        Group {
            if mounted { content().onAppear { acknowledgement.contentAppeared() } }
            else { Color.clear.frame(width: estimatedWidth, height: estimatedHeight).accessibilityHidden(true) }
        }.task {
            guard !mounted else { return }
            let ticket = PerformanceRendering.beginSurface(), turn = UUID()
            defer { PerformanceRendering.endSurface(ticket) }
            guard await RowMountQueue.shared.acquire(turn, label: workLabel ?? "row." + region, priority: priority) else { return }
            defer { RowMountQueue.shared.release(turn) }
            guard !Task.isCancelled else { return }
            mounted = true
            guard await acknowledgement.wait(), !Task.isCancelled else { return }
            // Start the display-turn delay after actual content admission, not
            // after merely requesting it. Delayed updates cannot accumulate a
            // batch of cold native rows behind the same layout transaction.
            try? await Task.sleep(for: .milliseconds(32))
        }
    }
}
