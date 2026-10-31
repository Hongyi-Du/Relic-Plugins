import Foundation

/// One independent timer and at most one outstanding main-queue dispatch.
/// The shared driver owns resource sampling and all fixed acceptance limits.
final class ResponsivenessWatchdog: @unchecked Sendable {
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "Relic.ResponsivenessWatchdog", qos: .userInitiated)
    private let output: URL
    private var source: DispatchSourceTimer?
    private var pending: Double = 0, pendingEpoch: Double = 0, worst: Double = 0
    private var pings = 0, sequence = 0
    private var stage = "startup"

    init(output: URL) { self.output = output }
    func begin() {
        write(["pid": ProcessInfo.processInfo.processIdentifier, "unix_ms": Self.epoch], "performance-ready.json")
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now(), repeating: .milliseconds(50), leeway: .milliseconds(1))
        timer.setEventHandler { [weak self] in self?.probe() }
        source = timer; timer.resume()
    }
    func action(_ name: String) { lock.lock(); stage = name; lock.unlock() }
    var maximum: Double { lock.lock(); defer { lock.unlock() }; return worst }
    func finish(_ receipt: [String: Any]) {
        source?.cancel(); source = nil
        var result = receipt; result["max_ui_stall_ms"] = maximum
        write(result, "performance-complete.json")
    }
    private static var epoch: Double { Date().timeIntervalSince1970 * 1000 }
    private func probe() {
        lock.lock()
        let now = ProcessInfo.processInfo.systemUptime
        if pending > 0 { worst = max(worst, (now - pending) * 1000) }
        let enqueue = pending == 0
        if enqueue { pending = now; pendingEpoch = Self.epoch }
        sequence += 1
        let receipt: [String: Any] = ["unix_ms": Self.epoch, "sequence": sequence, "pings": pings,
            "max_ui_stall_ms": worst, "pending_since_unix_ms": pendingEpoch, "action": stage]
        lock.unlock()
        if enqueue {
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.lock.lock()
                self.worst = max(self.worst, (ProcessInfo.processInfo.systemUptime - self.pending) * 1000)
                self.pending = 0; self.pendingEpoch = 0; self.pings += 1
                self.lock.unlock()
            }
        }
        write(receipt, "heartbeat.json")
    }
    private func write(_ value: [String: Any], _ name: String) {
        do { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: output.appendingPathComponent(name), options: .atomic) }
        catch { fputs("Cannot write responsiveness evidence: \(error)\n", stderr) }
    }
}
