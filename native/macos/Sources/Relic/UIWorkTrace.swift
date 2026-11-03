import Foundation

/// CI diagnosis only. Aggregate actual native work and retain the active scope
/// at a failed probe even when the runner kills a blocked process before sample
/// has finished symbolicating its stack.
final class UIWorkTrace: @unchecked Sendable {
    static let shared = UIWorkTrace()
    static let enabled = ProcessInfo.processInfo.environment["RELIC_PERF_MANIFEST"] != nil
    private let lock = NSLock()
    private var ordinal = 0
    private var active: [Int: (name: String, started: Double, main: Bool)] = [:]
    private var totals: [String: (count: Int, ms: Double, maximum: Double)] = [:]
    private var gauges: [String: (current: Int, peak: Int)] = [:]
    static func gauge(_ name: String, _ value: Int) {
        guard enabled else { return }
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        trace.gauges[name] = (value, max(value, trace.gauges[name]?.peak ?? 0))
    }
    /// The CI samples showed ProcessInfo.systemUptime (an Objective-C call
    /// that retains the shared ProcessInfo) as most of the cost of tracing a
    /// label measurement. Read the same uptime clock directly.
    private static var uptime: Double { Double(clock_gettime_nsec_np(CLOCK_UPTIME_RAW)) / 1_000_000_000 }
    static func begin(_ name: String) -> Int? {
        guard enabled else { return nil }
        let started = uptime, main = pthread_main_np() != 0
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        trace.ordinal += 1
        trace.active[trace.ordinal] = (name, started, main)
        return trace.ordinal
    }
    /// A scope open until the main queue's next turn. A state change made now
    /// is rendered by the SwiftUI transaction before that turn, so the scope
    /// names the transaction a probe waited behind.
    static func untilNextTurn(_ name: String) {
        guard let token = begin(name) else { return }
        DispatchQueue.main.async { end(token) }
    }
    /// Counts a cheap event, such as one view body evaluation, without timing it.
    static func count(_ name: String) {
        guard enabled else { return }
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        let previous = trace.totals[name] ?? (0, 0, 0)
        trace.totals[name] = (previous.count + 1, previous.ms, previous.maximum)
    }
    /// Calls and milliseconds so far, to attribute work to one scripted action.
    func counts() -> [String: (calls: Int, ms: Double)] {
        lock.lock(); defer { lock.unlock() }
        return totals.mapValues { (calls: $0.count, ms: $0.ms) }
    }
    func delta(since before: [String: (calls: Int, ms: Double)]) -> [String: [String: Any]] {
        var result: [String: [String: Any]] = [:]
        for (name, now) in counts() {
            let calls = now.calls - (before[name]?.calls ?? 0)
            guard calls > 0 else { continue }
            result[name] = ["calls": calls, "ms": ((now.ms - (before[name]?.ms ?? 0)) * 10).rounded() / 10]
        }
        return result
    }
    static func end(_ token: Int?) {
        guard let token else { return }
        let ended = uptime
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        guard let scope = trace.active.removeValue(forKey: token) else { return }
        let ms = (ended - scope.started) * 1000
        let previous = trace.totals[scope.name] ?? (0, 0, 0)
        trace.totals[scope.name] = (previous.count + 1, previous.ms + ms, max(previous.maximum, ms))
    }
    /// The traced work since `before`, most time first: what ran on the main
    /// thread while a probe waited, even when it ended before the answer.
    func work(since before: [String: (calls: Int, ms: Double)], limit: Int = 16) -> [String] {
        delta(since: before).map { (name: $0.key, calls: $0.value["calls"] as? Int ?? 0, ms: $0.value["ms"] as? Double ?? 0) }
            .sorted { $0.ms != $1.ms ? $0.ms > $1.ms : $0.calls > $1.calls }
            .prefix(limit).map { $0.ms > 0 ? "\($0.name) \($0.calls)/\($0.ms) ms" : "\($0.name) \($0.calls)x" }
    }
    /// CI only. Times each pass of the main run loop's display work, from the
    /// first to the last observer before the run loop waits: SwiftUI's graph
    /// update, AppKit's layout and drawing, and Core Animation's commit. A
    /// probe that waited behind a long pass then lists "runloop.display" next
    /// to the named regions' layouts and the labels that ran inside it, and a
    /// stall outside any pass shows that its work came from a queued job.
    @MainActor static func observeDisplayPasses() {
        guard enabled, !observingDisplay else { return }
        observingDisplay = true
        var token: Int?
        let first = CFRunLoopObserverCreateWithHandler(nil, CFRunLoopActivity.beforeWaiting.rawValue, true, CFIndex.min) { _, _ in
            end(token); token = begin("runloop.display")
        }
        let last = CFRunLoopObserverCreateWithHandler(nil, CFRunLoopActivity.beforeWaiting.rawValue, true, CFIndex.max) { _, _ in
            end(token); token = nil
        }
        CFRunLoopAddObserver(CFRunLoopGetMain(), first, .commonModes)
        CFRunLoopAddObserver(CFRunLoopGetMain(), last, .commonModes)
    }
    @MainActor private static var observingDisplay = false
    /// Scopes still open now, oldest first, with how long each has been open.
    func openScopes() -> [String] {
        lock.lock(); defer { lock.unlock() }
        let now = Self.uptime
        return active.values.sorted { $0.started < $1.started }
            .map { $0.name + " " + String(Int((now - $0.started) * 1000)) + " ms" }
    }
    func snapshot() -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        let now = Self.uptime
        let activeRows: [[String: Any]] = active.values.map { ["name": $0.name, "milliseconds": (now - $0.started) * 1000, "main_thread": $0.main] }
        let summaries: [String: [String: Any]] = totals.mapValues { ["calls": $0.count, "total_ms": $0.ms, "max_ms": $0.maximum] }
        return ["active": activeRows, "totals": summaries,
                "gauges": gauges.mapValues { ["current": $0.current, "peak": $0.peak] }]
    }
}
