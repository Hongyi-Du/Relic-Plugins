import Foundation

/// A separate diagnostic timeline. The case-progress/watchdog file is never
/// updated here, so recording a phase cannot extend the capture deadline.
@MainActor final class CapturePhaseTrace {
    private let path: URL
    private let caseID: String
    private let started = ProcessInfo.processInfo.systemUptime
    private var events: [[String: Any]] = []
    init(caseID: String, output: URL) {
        self.caseID = caseID
        path = output.appendingPathComponent(caseID + ".capture-phases.json")
    }
    func record(_ phase: String) throws {
        let now = ProcessInfo.processInfo.systemUptime
        events.append(["phase": phase, "uptime_seconds": now, "elapsed_seconds": now - started])
        try JSONSerialization.data(withJSONObject: ["case_id": caseID, "pid": ProcessInfo.processInfo.processIdentifier,
            "source": "actual native capture call boundaries", "refreshes_watchdog": false, "events": events], options: [.sortedKeys])
            .write(to: path, options: .atomic)
    }
}
