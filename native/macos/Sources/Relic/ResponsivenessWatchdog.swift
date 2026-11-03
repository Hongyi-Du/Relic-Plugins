import Foundation

/// Persistence cadence is separate from the unchanged UI probe cadence.
/// Unfinished probes and new failures are never delayed by healthy batching.
struct HeartbeatPersistence {
    private var writtenAt: Double?, writtenAction = "", writtenWorst: Double = -1
    mutating func shouldWrite(now: Double, action: String, worst: Double, unfinished: Bool) -> Bool {
        guard writtenAt == nil || now - writtenAt! >= 0.2 || action != writtenAction || worst > writtenWorst || unfinished else { return false }
        writtenAt = now; writtenAction = action; writtenWorst = worst
        return true
    }
}

/// One independent timer and at most one outstanding main-queue dispatch.
/// The shared driver owns resource sampling and all fixed acceptance limits.
final class ResponsivenessWatchdog: @unchecked Sendable {
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "Relic.ResponsivenessWatchdog", qos: .userInitiated)
    private let output: URL
    private var source: DispatchSourceTimer?
    private var pending: Double = 0, pendingEpoch: Double = 0, worst: Double = 0
    private var runLoopPending: Double = 0, runLoopWorst: Double = 0
    private var runLoopPings = 0
    private var pings = 0, sequence = 0
    private var stage = "startup"
    private var pendingStage = "startup"
    private var stalls: [[String: Any]] = []
    private var sampledStall = false
    private var sampledStartup = false
    private var sampledDialog = false
    /// Diagnostic runs only. A phase that studies a later action can skip the
    /// startup sample, whose overhead can fail the phase before that action.
    var samplesStartup = true
    private var persistence = HeartbeatPersistence()

    init(output: URL) { self.output = output }
    func begin() {
        write(["pid": ProcessInfo.processInfo.processIdentifier, "unix_ms": Self.epoch, "phases_version": 2,
               "capture_diagnostics": NativeDiagnostics.enabled], "performance-ready.json")
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now(), repeating: .milliseconds(50), leeway: .milliseconds(1))
        timer.setEventHandler { [weak self] in self?.probe() }
        source = timer; timer.resume()
    }
    func action(_ name: String) {
        let diagnostic = ProcessEnvironment.value("RELIC_PERF_DIAGNOSTIC") == "true"
        lock.lock(); stage = name
        let sample = !sampledStartup && name == "startup:publish" && diagnostic && samplesStartup
        if sample { sampledStartup = true }
        // The first dialog of a run opens cold. Sample it from its start, not
        // from a failed probe, which sees only the end of a 300 ms stall.
        let sampleDialog = diagnostic && !sampledDialog && name.hasSuffix(":dialog")
        if sampleDialog { sampledDialog = true }
        lock.unlock()
        // Diagnostic-only sampling begins before the cold native view layout.
        // Starting sample after a 250 ms failure misses a 300 ms stall entirely.
        // Normal acceptance retains its original workload and watchdog limit.
        if sample { queue.async { self.sample("startup-diagnostic", seconds: 8) } }
        if sampleDialog { queue.async { self.sample("first-dialog", seconds: 2) } }
    }
    var maximum: Double { lock.lock(); defer { lock.unlock() }; return worst }
    func recordActions(_ receipt: [String: Any]) {
        // The external watchdog may stop a failed phase before finish(). Keep
        // already-observed input/results, without serializing or writing on UI.
        // A partial receipt never supplies completion or acceptance eligibility.
        queue.async { self.write(receipt, "performance-actions.json") }
    }
    func finish(_ receipt: [String: Any]) {
        source?.cancel(); source = nil
        queue.sync {} // Retain the last partial receipt before process shutdown.
        lock.lock(); sequence += 1
        let heartbeat: [String: Any] = ["unix_ms": Self.epoch, "sequence": sequence, "pings": pings,
            "max_ui_stall_ms": worst, "pending_since_unix_ms": pendingEpoch, "action": stage,
            "max_runloop_stall_ms": runLoopWorst, "runloop_pings": runLoopPings]
        lock.unlock()
        write(heartbeat, "heartbeat.json")
        var result = receipt; result["max_ui_stall_ms"] = maximum
        write(result, "performance-complete.json")
    }
    private static var epoch: Double { Date().timeIntervalSince1970 * 1000 }
    private func probe() {
        lock.lock()
        let now = ProcessInfo.processInfo.systemUptime
        if pending > 0 { worst = max(worst, (now - pending) * 1000) }
        if runLoopPending > 0 { runLoopWorst = max(runLoopWorst, (now - runLoopPending) * 1000) }
        let probeRunLoop = runLoopPending == 0
        if probeRunLoop { runLoopPending = now }
        let enqueue = pending == 0
        let sampleStall = worst > 250 && !sampledStall
        if sampleStall { sampledStall = true }
        let persist = persistence.shouldWrite(now: now, action: stage, worst: worst, unfinished: !enqueue)
        if enqueue { pending = now; pendingEpoch = Self.epoch; pendingStage = stage }
        if persist { sequence += 1 }
        let receipt: [String: Any] = ["unix_ms": Self.epoch, "sequence": sequence, "pings": pings,
            "max_ui_stall_ms": worst, "pending_since_unix_ms": pendingEpoch, "action": stage,
            "max_runloop_stall_ms": runLoopWorst, "runloop_pings": runLoopPings]
        let observations = stalls
        lock.unlock()
        if probeRunLoop {
            // Supplemental observation only: the existing DispatchQueue probe
            // and its unchanged 250 ms gate remain authoritative. Compare actual
            // event-loop service with queue delay before diagnosing starvation.
            let main = CFRunLoopGetMain()
            CFRunLoopPerformBlock(main, CFRunLoopMode.commonModes.rawValue) { [weak self] in
                guard let self else { return }
                self.lock.lock()
                self.runLoopWorst = max(self.runLoopWorst, (ProcessInfo.processInfo.systemUptime - self.runLoopPending) * 1000)
                self.runLoopPending = 0; self.runLoopPings += 1
                self.lock.unlock()
            }
            CFRunLoopWakeUp(main)
        }
        if sampleStall {
            write(UIWorkTrace.shared.snapshot(), "first-stall-work.json")
            // CI-only diagnosis after the unchanged limit has already failed.
            // Sampling our own process preserves the blocked native call stack.
            sample("first-stall", seconds: 1)
        }
        if enqueue {
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.lock.lock()
                let delay = (ProcessInfo.processInfo.systemUptime - self.pending) * 1000
                self.worst = max(self.worst, delay)
                if delay > 250 {
                    if self.stalls.count >= 512 { self.stalls.removeFirst() }
                    self.stalls.append(["started_unix_ms": self.pendingEpoch, "milliseconds": delay,
                                       "started_action": self.pendingStage, "completed_action": self.stage])
                }
                self.pending = 0; self.pendingEpoch = 0; self.pings += 1
                self.lock.unlock()
            }
        }
        if persist { write(receipt, "heartbeat.json") }
        if sampledStall {
            write(UIWorkTrace.shared.snapshot(), "ui-work.json")
            write(["completed_probes_over_250ms": observations], "ui-stalls.json")
        }
    }
    private func sample(_ name: String, seconds: Int) {
        let sampler = Process()
        sampler.executableURL = URL(fileURLWithPath: "/usr/bin/sample")
        // A long 1 ms startup sample can spend the entire diagnostic retention
        // interval symbolicating millions of recursive SwiftUI frames and leave
        // no file. A 10 ms interval covers the same eight seconds with bounded
        // diagnostic overhead. The acceptance probes are completely separate.
        // The first dialog's 2 s at 5 ms still resolves a 300 ms stall and
        // finishes symbolicating within the 30 s diagnostic retention.
        let interval = name == "startup-diagnostic" ? "10" : name == "first-dialog" ? "5" : "1"
        sampler.arguments = [String(ProcessInfo.processInfo.processIdentifier), String(seconds), interval, "-mayDie", "-file", output.appendingPathComponent(name + ".sample.txt").path]
        let log = output.appendingPathComponent(name + ".sampler.log")
        FileManager.default.createFile(atPath: log.path, contents: nil)
        sampler.standardOutput = try? FileHandle(forWritingTo: log); sampler.standardError = sampler.standardOutput
        try? sampler.run()
    }
    private func write(_ value: [String: Any], _ name: String) {
        do { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: output.appendingPathComponent(name), options: .atomic) }
        catch { fputs("Cannot write responsiveness evidence: \(error)\n", stderr) }
    }
}
