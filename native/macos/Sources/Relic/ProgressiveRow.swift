import SwiftUI

/// Serialize cold row construction across native display turns. A lazy stack
/// can admit several complex rows in one layout pass even when it recycles
/// offscreen content correctly. No data is removed from the collection.
@MainActor final class RowMountQueue {
    static let shared = RowMountQueue()
    private var active: UUID?
    private var activeTrace: Int?
    private var waiting: [(UUID, CheckedContinuation<Bool, Never>, String)] = []
    var waitingCount: Int { waiting.count }
    var isIdle: Bool { active == nil && waiting.isEmpty }
    func acquire(_ id: UUID, label: String = "row") async -> Bool {
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: false) }
                else if active == nil {
                    active = id; activeTrace = UIWorkTrace.begin("mount-turn." + label)
                    continuation.resume(returning: true)
                }
                else { waiting.append((id, continuation, label)) }
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

struct ProgressiveRow<Content: View>: View {
    @Environment(\.captureRegion) private var region
    var estimatedHeight: CGFloat
    var estimatedWidth: CGFloat? = nil
    @ViewBuilder var content: () -> Content
    @State private var mounted = false
    var body: some View {
        Group {
            if mounted { content() }
            else { Color.clear.frame(width: estimatedWidth, height: estimatedHeight).accessibilityHidden(true) }
        }.task {
            guard !mounted else { return }
            let ticket = PerformanceRendering.beginSurface(), turn = UUID()
            defer { PerformanceRendering.endSurface(ticket) }
            guard await RowMountQueue.shared.acquire(turn, label: "row." + region) else { return }
            defer { RowMountQueue.shared.release(turn) }
            guard !Task.isCancelled else { return }
            mounted = true
            // Release the next row only after this actual display turn. Booking
            // fixed future deadlines would let overdue rows all mount at once.
            try? await Task.sleep(for: .milliseconds(32))
        }
    }
}
