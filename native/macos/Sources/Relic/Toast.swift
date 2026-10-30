import SwiftUI
import RelicCore

@MainActor final class NativeToastMessage: Identifiable {
    let id = UUID()
    let text: String
    let seconds: Double
    private let clock = ContinuousClock()
    private let created = ContinuousClock.now
    private var deadline: ContinuousClock.Instant?
    private var remaining: Duration
    private var task: Task<Void, Never>?
    private var expire: (() -> Void)?
    private(set) var timerState = "idle"
    init(text: String, seconds: Double) { self.text = text; self.seconds = seconds; self.remaining = .seconds(seconds) }
    deinit { task?.cancel() }
    func start(_ expire: @escaping () -> Void) {
        guard timerState == "idle" else { return }
        self.expire = expire; arm()
    }
    private func arm() {
        let scheduled = clock.now.advanced(by: remaining)
        deadline = scheduled; timerState = "running"
        task = Task { [weak self, clock] in
            do { try await clock.sleep(until: scheduled) } catch { return }
            guard let self, !Task.isCancelled, self.timerState == "running", self.deadline == scheduled else { return }
            self.timerState = "expired"; self.remaining = .zero; self.deadline = nil; self.task = nil
            let callback = self.expire; self.expire = nil; callback?()
        }
    }
    func pauseTimer() throws -> [String: Any] {
        let before = timerSnapshot(), now = clock.now
        guard timerState == "running", let deadline, deadline > now else { throw RelicError.message("Toast timer was not running with a positive remaining lifetime") }
        remaining = now.duration(to: deadline); task?.cancel(); task = nil; self.deadline = nil; timerState = "paused"
        return ["before": before, "after": timerSnapshot()]
    }
    func resumeTimer() -> [String: Any] {
        let before = timerSnapshot()
        if timerState == "paused" { arm() }
        return ["before": before, "after": timerSnapshot()]
    }
    func cancelTimer() {
        if let deadline { remaining = max(.zero, clock.now.duration(to: deadline)) }
        task?.cancel(); task = nil; deadline = nil; expire = nil
        if timerState != "expired" { timerState = "cancelled" }
    }
    func timerSnapshot() -> [String: Any] {
        func milliseconds(_ value: Duration) -> Double { let c = value.components; return Double(c.seconds) * 1_000 + Double(c.attoseconds) / 1e15 }
        let now = clock.now, left = deadline.map { max(.zero, now.duration(to: $0)) } ?? remaining
        return ["id": id.uuidString, "instance": String(describing: ObjectIdentifier(self)), "state": timerState,
                "elapsed_monotonic_ms": milliseconds(created.duration(to: now)), "remaining_ms": milliseconds(left),
                "deadline_from_creation_ms": deadline.map { milliseconds(created.duration(to: $0)) } as Any? ?? NSNull(),
                "source": "Production ContinuousClock deadline and cancellation/rescheduling of its actual expiry task"]
    }
}

extension Model {
    func showNotice(_ text: String, seconds: Double) {
        // Keep legacy notice readers current while giving this production toast
        // the explicit lifetime requested by its action.
        noticeSeconds = seconds; notice = text; noticeSeconds = 3.6
    }
    func appendToast(_ text: String, seconds: Double) {
        let item = NativeToastMessage(text: text, seconds: seconds)
        toasts.append(item)
        item.start { [weak self, weak item] in if let item { self?.dismissToast(item.id) } }
    }
    func dismissToast(_ id: UUID) { toasts.removeAll { $0.id == id } }
}

/// Reference notifications occupy one floating position; later notifications
/// paint above earlier ones, and each owns its independent lifetime.
struct NativeToasts: View {
    @EnvironmentObject var m: Model
    var body: some View {
        ZStack(alignment: .bottom) {
            ForEach(m.toasts) { item in
                ReferenceLabel(item.text, size: 13, color: RelicStyle.background, lineHeight: 20.8, lines: 0, owner: "relic-toast/" + item.id.uuidString)
                    .padding(.horizontal, 16).padding(.vertical, 9)
                    .modifier(RecordedSurface(background: RelicStyle.ink, radius: 10, kind: "card", owner: "relic-toast/" + item.id.uuidString, shadows: SurfaceShadow.dialog))
                    .frame(maxWidth: min(560, max(1, m.windowSize.width - 40)))
                    .accessibilityIdentifier("relic-toast/" + item.id.uuidString)
            }
        }.padding(.bottom, 28).environment(\.captureRegion, "window")
    }
}
