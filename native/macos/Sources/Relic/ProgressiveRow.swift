import SwiftUI

/// Serialize cold row construction across native display turns. A lazy stack
/// can admit several complex rows in one layout pass even when it recycles
/// offscreen content correctly. No data is removed from the collection.
///
/// A turn may admit several waiting rows of the same list together while
/// their combined weight fits in `budget`. In the CI traces each admitted row
/// cost its list a full update whatever the row held: a one-line notice took
/// as long to admit as a message (person-shape 56-90 ms per turn), because the
/// conversation's table measured every visible row again and the inspector's
/// lazy stack estimated all its rows again. One-line rows admitted together
/// share that update; any heavier row still keeps a turn of its own, since
/// two messages or four cards in one turn made 250-280 ms flushes.
/// Unweighted acquisitions keep a turn each.
@MainActor final class RowMountQueue {
    static let shared = RowMountQueue()
    /// Four one-line rows (notices, activity lines, overview headings).
    static let budget = 4
    /// A model publication (a chat or organization opened, a refreshed
    /// snapshot) and a list's adoption of the rows it published take the
    /// queue ahead of every waiting row, so no row is built in their display
    /// update. In CI a chat's publication or adoption that shared its update
    /// with a sidebar row's mount made 410 and 344 ms flushes, and an
    /// organization's publication with one 220-235 ms (run 41709167265, large
    /// open-0071 and warmup-0043).
    static let publishPriority = 100, adoptPriority = 90
    private struct Waiting { let id: UUID, continuation: CheckedContinuation<Bool, Never>, label: String, priority: Int, group: String?, weight: Int }
    private var active: Set<UUID> = []
    private var activeTrace: Int?
    private var waiting: [Waiting] = []
    private var grantScheduled = false
    var waitingCount: Int { waiting.count }
    var isIdle: Bool { active.isEmpty && waiting.isEmpty }
    /// `group` names the list a row belongs to; rows of one group with a
    /// weight may share a turn. Without a group the turn is this caller's alone.
    func acquire(_ id: UUID, label: String = "row", priority: Int = 0, group: String? = nil, weight: Int = 0) async -> Bool {
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: false); return }
                let entry = Waiting(id: id, continuation: continuation, label: label, priority: priority, group: group, weight: weight)
                let position = waiting.firstIndex { $0.priority < priority } ?? waiting.endIndex
                waiting.insert(entry, at: position)
                // An idle queue grants on the main actor's next turn: the other
                // rows that one update showed ask first, so the turn goes to the
                // highest priority and admits its group's rows together.
                if active.isEmpty, !grantScheduled {
                    grantScheduled = true
                    Task { @MainActor in self.grantScheduled = false; self.grant() }
                }
            }
        }, onCancel: { Task { @MainActor in self.cancelWaiting(id) } })
    }
    private func cancelWaiting(_ id: UUID) {
        if let index = waiting.firstIndex(where: { $0.id == id }) {
            waiting.remove(at: index).continuation.resume(returning: false)
        }
    }
    func release(_ id: UUID) {
        guard active.remove(id) != nil else { return }
        guard active.isEmpty else { return }
        UIWorkTrace.end(activeTrace); activeTrace = nil
        grant()
    }
    /// Keep a publication's or adoption's turn through the display update that
    /// shows its changes, as a row keeps its turn for 32 ms after its content
    /// appeared, then release it.
    func releaseAfterUpdate(_ id: UUID) {
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(32))
            self.release(id)
        }
    }
    private func grant() {
        guard active.isEmpty, !waiting.isEmpty else { return }
        let first = waiting.removeFirst()
        var admitted = [first]
        if let group = first.group, first.weight > 0 {
            var total = first.weight, index = 0
            while index < waiting.count, total < Self.budget {
                let next = waiting[index]
                if next.group == group, next.weight > 0, total + next.weight <= Self.budget {
                    total += next.weight; admitted.append(waiting.remove(at: index))
                } else { index += 1 }
            }
        }
        active = Set(admitted.map(\.id))
        activeTrace = UIWorkTrace.begin("mount-turn." + first.label)
        if let group = first.group { for _ in admitted { UIWorkTrace.count("mount-rows." + group) } }
        for entry in admitted { entry.continuation.resume(returning: true) }
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
    /// What admitting this row costs its list, in RowMountQueue.budget units.
    var weight = 1
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
            guard await RowMountQueue.shared.acquire(turn, label: workLabel ?? "row." + region, priority: priority, group: region, weight: weight) else { return }
            defer { RowMountQueue.shared.release(turn) }
            guard !Task.isCancelled else { return }
            mounted = true
            guard await acknowledgement.wait(), !Task.isCancelled else { return }
            // Start the display-turn delay after actual content admission, not
            // after merely requesting it. Delayed updates cannot accumulate
            // more cold native rows behind the same layout transaction than
            // the queue admitted together.
            try? await Task.sleep(for: .milliseconds(32))
        }
    }
}
