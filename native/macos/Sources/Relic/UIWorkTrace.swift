import Foundation

/// CI diagnosis only. Aggregate actual native work and retain the active scope
/// at a failed probe even when the runner kills a blocked process before sample
/// has finished symbolicating its stack.
final class UIWorkTrace: @unchecked Sendable {
    static let shared = UIWorkTrace()
    private static let enabled = ProcessInfo.processInfo.environment["RELIC_PERF_MANIFEST"] != nil
    private let lock = NSLock()
    private var ordinal = 0
    private var active: [Int: (name: String, started: Double, main: Bool)] = [:]
    private var totals: [String: (count: Int, ms: Double, maximum: Double)] = [:]
    static func begin(_ name: String) -> Int? {
        guard enabled else { return nil }
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        trace.ordinal += 1
        trace.active[trace.ordinal] = (name, ProcessInfo.processInfo.systemUptime, Thread.isMainThread)
        return trace.ordinal
    }
    static func end(_ token: Int?) {
        guard let token else { return }
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        guard let scope = trace.active.removeValue(forKey: token) else { return }
        let ms = (ProcessInfo.processInfo.systemUptime - scope.started) * 1000
        let previous = trace.totals[scope.name] ?? (0, 0, 0)
        trace.totals[scope.name] = (previous.count + 1, previous.ms + ms, max(previous.maximum, ms))
    }
    func snapshot() -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        let now = ProcessInfo.processInfo.systemUptime
        let activeRows: [[String: Any]] = active.values.map { ["name": $0.name, "milliseconds": (now - $0.started) * 1000, "main_thread": $0.main] }
        let summaries: [String: [String: Any]] = totals.mapValues { ["calls": $0.count, "total_ms": $0.ms, "max_ms": $0.maximum] }
        return ["active": activeRows, "totals": summaries]
    }
}
