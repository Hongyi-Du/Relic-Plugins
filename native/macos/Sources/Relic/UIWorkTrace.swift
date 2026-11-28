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
    /// Bumped on every change to `totals`, so an unchanged copy can be reused.
    private var version = 0
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
        trace.version &+= 1
    }
    /// Calls and milliseconds so far, to attribute work to one scripted action.
    func counts() -> [String: (calls: Int, ms: Double)] {
        lock.lock(); defer { lock.unlock() }
        return totals.mapValues { (calls: $0.count, ms: $0.ms) }
    }
    /// The totals' version, and a copy of them only if they changed since
    /// `known`: the watchdog takes one for every probe it sends, and in the
    /// idle phase nothing changes between probes.
    func counts(ifChangedSince known: Int) -> (version: Int, counts: [String: (calls: Int, ms: Double)]?) {
        lock.lock(); defer { lock.unlock() }
        guard version != known else { return (version, nil) }
        return (version, totals.mapValues { (calls: $0.count, ms: $0.ms) })
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
        trace.version &+= 1
    }
    /// The traced work since `before`, most time first: what ran on the main
    /// thread while a probe waited, even when it ended before the answer.
    func work(since before: [String: (calls: Int, ms: Double)], limit: Int = 16) -> [String] {
        typealias Entry = (name: String, calls: Int, ms: Double)
        var entries: [Entry] = []
        for (name, values) in delta(since: before) {
            let calls: Int = values["calls"] as? Int ?? 0
            let ms: Double = values["ms"] as? Double ?? 0
            entries.append((name: name, calls: calls, ms: ms))
        }
        entries.sort { (a: Entry, b: Entry) -> Bool in a.ms != b.ms ? a.ms > b.ms : a.calls > b.calls }
        return entries.prefix(limit).map { (entry: Entry) -> String in
            entry.ms > 0 ? entry.name + " " + String(entry.calls) + "/" + String(entry.ms) + " ms"
                         : entry.name + " " + String(entry.calls) + "x"
        }
    }
    /// CI only. Splits the main run loop's time into named parts, so a probe
    /// that waited names the part that held it:
    /// - runloop.observers.<stage>: every observer of that stage, first to
    ///   last. AppKit flushes the display there (Core Animation's commit runs
    ///   the window's layout, SwiftUI's update and drawing), at whichever
    ///   stage this macOS uses.
    /// - runloop.after.<stage>: the work that follows that stage's observers.
    ///   After "woke" that is timers, the main queue (main-actor jobs) and
    ///   ports such as events; after "sources", run loop blocks and sources,
    ///   and the same work as after "woke" when the loop goes on without sleeping.
    /// The thread's sleep after "waiting" is not counted.
    ///
    /// Only parts of at least a millisecond are recorded, so "calls" counts
    /// those parts: each observer callout reads the clock once and takes no
    /// lock otherwise. The full version of this timer, a scope begun and
    /// ended for every part, raised the idle phase's CPU from about 0.9% to
    /// 1.1-1.6%; the capture also leaves it off in the idle phase.
    ///
    /// Each stage's observers are also split by order, "runloop.<stage>.<part>":
    /// "early" below -1, "order0" from -1 to 1, "middle" up to 1,999,999,
    /// "order2m" up to 2,000,001 (Core Animation's commit observer has order
    /// 2,000,000) and "late" after it. FlushTrace writes this macOS's observers
    /// and their orders to runloop-observers.txt.
    @MainActor static func observeRunLoop() {
        guard enabled, !observingRunLoop else { return }
        observingRunLoop = true
        func stage(_ activity: CFRunLoopActivity) -> String {
            switch activity {
            case .entry: return "entry"
            case .beforeTimers: return "timers"
            case .beforeSources: return "sources"
            case .beforeWaiting: return "waiting"
            case .afterWaiting: return "woke"
            default: return "exit"
            }
        }
        func after(_ activity: CFRunLoopActivity) -> String? {
            switch activity {
            case .entry, .beforeTimers, .beforeSources, .afterWaiting: return "runloop.after." + stage(activity)
            default: return nil
            }
        }
        var part: String?, started = uptime
        func close(_ now: Double) {
            if let name = part, now - started >= 0.001 { record(name, ms: (now - started) * 1000) }
        }
        var segmentStarted = started, segment = "early"
        func closeSegment(_ now: Double, _ activity: CFRunLoopActivity, next: String) {
            if now - segmentStarted >= 0.001 { record("runloop." + stage(activity) + "." + segment, ms: (now - segmentStarted) * 1000) }
            segmentStarted = now; segment = next
        }
        let all = CFRunLoopActivity.allActivities.rawValue
        let first = CFRunLoopObserverCreateWithHandler(nil, all, true, CFIndex.min) { _, activity in
            let now = uptime; close(now); part = "runloop.observers." + stage(activity); started = now
            segmentStarted = now; segment = "early"
        }
        CFRunLoopAddObserver(CFRunLoopGetMain(), first, .commonModes)
        let bounds: [(order: CFIndex, next: String)] = [(-1, "order0"), (1, "middle"), (1_999_999, "order2m"), (2_000_001, "late")]
        for bound in bounds {
            let observer = CFRunLoopObserverCreateWithHandler(nil, all, true, bound.order) { _, activity in
                closeSegment(uptime, activity, next: bound.next)
            }
            CFRunLoopAddObserver(CFRunLoopGetMain(), observer, .commonModes)
        }
        let last = CFRunLoopObserverCreateWithHandler(nil, all, true, CFIndex.max) { _, activity in
            let now = uptime; closeSegment(now, activity, next: "early")
            close(now); part = after(activity); started = now
        }
        CFRunLoopAddObserver(CFRunLoopGetMain(), last, .commonModes)
    }
    @MainActor private static var observingRunLoop = false
    /// Adds one finished part of the given length, without a begun scope.
    static func record(_ name: String, ms: Double) {
        guard enabled else { return }
        let trace = shared; trace.lock.lock(); defer { trace.lock.unlock() }
        let previous = trace.totals[name] ?? (0, 0, 0)
        trace.totals[name] = (previous.count + 1, previous.ms + ms, max(previous.maximum, ms))
        trace.version &+= 1
    }
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
