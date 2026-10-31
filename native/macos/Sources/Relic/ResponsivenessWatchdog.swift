import Foundation
import RelicAX
import Darwin

/// Independent sampling survives a blocked UI thread. The 250 ms limit is fixed,
/// not configurable by a capture manifest. All counters describe this process.
final class ResponsivenessWatchdog: @unchecked Sendable {
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "Relic.ResponsivenessWatchdog", qos: .userInitiated, autoreleaseFrequency: .workItem)
    private let output: URL, completion: URL
    private let seed: UInt64
    private var source: DispatchSourceTimer?, heartbeat: Timer?
    private let start = ProcessInfo.processInfo.systemUptime
    private var lastBeat = ProcessInfo.processInfo.systemUptime, lastSample = 0.0, worst = 0.0
    private var samples: [[String: Any]] = [], actions: [String: Int] = [:], errors: [String] = []
    private var stage = "startup", stopped = false, episode = false

    init(output: URL, completion: URL, seed: UInt64) { self.output = output; self.completion = completion; self.seed = seed }

    @MainActor func begin() {
        let timer = Timer(timeInterval: 0.02, repeats: true) { [weak self] _ in self?.beat() }
        heartbeat = timer; RunLoop.main.add(timer, forMode: .common)
        let source = DispatchSource.makeTimerSource(queue: queue)
        source.schedule(deadline: .now() + .milliseconds(20), repeating: .milliseconds(20), leeway: .milliseconds(2))
        source.setEventHandler { [weak self] in self?.sample() }
        self.source = source; source.resume()
    }

    func action(_ name: String) {
        lock.lock(); stage = name; actions[name, default: 0] += 1; lock.unlock()
    }

    private func beat() {
        lock.lock(); defer { lock.unlock() }
        let now = ProcessInfo.processInfo.systemUptime
        worst = max(worst, (now - lastBeat) * 1000)
        lastBeat = now
    }

    private func sample() {
        let now = ProcessInfo.processInfo.systemUptime
        lock.lock()
        if stopped { lock.unlock(); return }
        let stall = (now - lastBeat) * 1000
        worst = max(worst, stall)
        if stall > 250 && !episode { errors.append("UI stall >250 ms during " + stage); episode = true }
        if stall <= 250 { episode = false }
        if now - lastSample >= 1 {
            let stats = RelicProcessStats()
            samples.append(["seconds": now - start, "ui_stall_ms": stall, "resident_bytes": stats["resident_bytes"]?.uint64Value ?? 0,
                            "threads": stats["threads"]?.intValue ?? 0, "cpu_seconds": stats["cpu_seconds"]?.doubleValue ?? 0, "stage": stage])
            lastSample = now
            if stats["valid"]?.boolValue != true { errors.append("Cannot read actual process resource counters") }
        }
        lock.unlock()
        // Retain evidence and stop an irrecoverable baseline. This does not
        // waive shorter stalls: any interval above 250 ms still fails the run.
        if stall > 10_000 { write(extraErrors: ["UI did not progress for 10 seconds"], seed: seed); exit(2) }
    }

    @MainActor func finish(errors: [String], seed: UInt64) {
        heartbeat?.invalidate(); heartbeat = nil
        write(extraErrors: errors, seed: seed)
        source?.cancel(); source = nil
    }

    private func write(extraErrors: [String], seed: UInt64) {
        lock.lock()
        stopped = true
        let faults = errors + extraErrors
        let actionCount = actions.values.reduce(0, +)
        let rss = samples.compactMap { ($0["resident_bytes"] as? NSNumber)?.uint64Value }
        let threads = samples.compactMap { ($0["threads"] as? NSNumber)?.intValue }
        let report: [String: Any] = ["platform": "macos", "seed": seed, "duration_seconds": ProcessInfo.processInfo.systemUptime - start,
            "worst_ui_stall_ms": worst, "ui_stall_limit_ms": 250,
            "peak_resident_bytes": rss.max() ?? 0, "final_resident_bytes": rss.last ?? 0,
            "peak_threads": threads.max() ?? 0, "final_threads": threads.last ?? 0,
            "samples": samples, "actions": actions, "errors": faults, "success": faults.isEmpty,
            "watchdog": "20 ms common-mode main-run-loop heartbeat and independent background sampler"]
        lock.unlock()
        do {
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
            try JSONSerialization.data(withJSONObject: ["errors": faults, "count": actionCount, "report": output.path], options: [.prettyPrinted, .sortedKeys]).write(to: completion, options: .atomic)
        } catch { fputs("Could not retain responsiveness report: \(error)\n", stderr) }
    }
}
