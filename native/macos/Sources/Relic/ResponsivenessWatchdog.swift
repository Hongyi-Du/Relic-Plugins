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
    /// The traced work totals when the pending probe was sent: a probe that
    /// waits over 120 ms lists the work that ran meanwhile, finished or not.
    private var pendingWork: [String: (calls: Int, ms: Double)] = [:]
    private var stalls: [[String: Any]] = []
    /// Probes that waited more than 120 ms, with the traced work still open
    /// when each was answered: which actions come close to the 250 ms limit,
    /// how often, and under what work. Written whenever it grows.
    private var nearStalls: [[String: Any]] = []
    private var nearStallsWritten = 0
    private var sampledStall = false
    private var sampledStartup = false
    private var sampledDialog = false
    private var earlySamples = 0
    private let diagnostic = ProcessEnvironment.value("RELIC_PERF_DIAGNOSTIC") == "true"
    /// Diagnostic runs only. A phase that studies a later action can skip the
    /// startup sample, whose overhead can fail the phase before that action.
    var samplesStartup = true
    /// Diagnostic runs only. Early-stall samples slow the actions before the
    /// one a phase studies; the workflows phase samples its first dialog instead.
    var samplesEarlyStalls = true
    /// Diagnostic runs only: the stage whose start arms a two-second sample,
    /// so a known heavy action is sampled from its click, not from its 250 ms.
    var armedStage: String?
    private var sampledArmed = false
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
    /// Diagnostic runs only: start the startup sample now, before the
    /// first request. sample takes its first sample many seconds after it
    /// starts (about 20 s on the CI runners); the capture waits until it
    /// sees it sampling before it begins the startup it should cover.
    func sampleStartupNow() -> Bool {
        lock.lock()
        let sample = diagnostic && samplesStartup && !sampledStartup
        if sample { sampledStartup = true }
        lock.unlock()
        if sample { queue.async { self.sample("startup-diagnostic", seconds: 12) } }
        return sample
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
        let sampleArmed = diagnostic && !sampledArmed && armedStage != nil && name == armedStage
        if sampleArmed { sampledArmed = true }
        lock.unlock()
        // Diagnostic-only sampling begins before the cold native view layout.
        // Starting sample after a 250 ms failure misses a 300 ms stall entirely.
        // Normal acceptance retains its original workload and watchdog limit.
        if sample { queue.async { self.sample("startup-diagnostic", seconds: 8) } }
        if sampleDialog { queue.async { self.sample("first-dialog", seconds: 16) } }
        if sampleArmed { queue.async { self.sample("armed-action", seconds: 4) } }
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
        // Diagnostic runs only: a sample that starts after a 250 ms failure
        // sees idle time. Start while a main-thread block is still growing,
        // so the sample holds the actual work of the long stalls.
        let sampleEarly = diagnostic && samplesEarlyStalls && pending > 0 && (now - pending) * 1000 >= 170 && earlySamples < 3
            && !(stage.hasPrefix("startup") || stage.hasSuffix(":dialog"))
        if sampleEarly { earlySamples += 1 }
        let earlyName = "early-stall-" + String(earlySamples)
        let earlyReceipt: [String: Any] = ["action": stage, "pending_ms": pending > 0 ? (now - pending) * 1000 : 0]
        let persist = persistence.shouldWrite(now: now, action: stage, worst: worst, unfinished: !enqueue)
        if enqueue { pending = now; pendingEpoch = Self.epoch; pendingStage = stage; pendingWork = UIWorkTrace.shared.counts() }
        if persist { sequence += 1 }
        let receipt: [String: Any] = ["unix_ms": Self.epoch, "sequence": sequence, "pings": pings,
            "max_ui_stall_ms": worst, "pending_since_unix_ms": pendingEpoch, "action": stage,
            "max_runloop_stall_ms": runLoopWorst, "runloop_pings": runLoopPings]
        let observations = stalls
        let near = nearStalls.count != nearStallsWritten ? nearStalls : nil
        if near != nil { nearStallsWritten = nearStalls.count }
        lock.unlock()
        if let near { write(["probes_over_120ms": near], "near-stalls.json") }
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
        if sampleEarly {
            var receipt = earlyReceipt; receipt["work"] = UIWorkTrace.shared.snapshot()
            write(receipt, earlyName + "-work.json")
            sample(earlyName, seconds: 1)
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
                if delay > 120, self.nearStalls.count < 400 {
                    self.nearStalls.append(["started_unix_ms": self.pendingEpoch, "milliseconds": (delay * 10).rounded() / 10,
                                            "started_action": self.pendingStage, "completed_action": self.stage,
                                            "open_work": UIWorkTrace.shared.openScopes(),
                                            "work_during": UIWorkTrace.shared.work(since: self.pendingWork)])
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
        // no file. A 5 ms interval over twelve seconds keeps that bounded. The
        // acceptance probes are completely separate.
        // The first dialog's 16 s at 3 ms resolves a 300 ms stall; the dialog
        // action waits until sample has written it.
        let interval = name == "startup-diagnostic" ? "5" : name == "first-dialog" ? "3" : name == "armed-action" ? "2" : "1"
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
