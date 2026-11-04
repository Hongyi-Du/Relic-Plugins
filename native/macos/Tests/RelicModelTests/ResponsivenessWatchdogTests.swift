import XCTest
@testable import Relic

final class ResponsivenessWatchdogTests: XCTestCase {
    func testPartialActionsSurviveBeforeCompletionAndNeverClaimEligibility() async throws {
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("Relic-action-evidence-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: output) }
        let watchdog = ResponsivenessWatchdog(output: output)
        watchdog.recordActions(["phase": "open-every-chat", "actions": [["id": "open-0000", "passed": true, "click_events": 1, "open_ms": 72.0]]])
        let partial = output.appendingPathComponent("performance-actions.json")
        let deadline = Date().addingTimeInterval(2)
        while !FileManager.default.fileExists(atPath: partial.path), Date() < deadline {
            try await Task.sleep(for: .milliseconds(10))
        }
        let first = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: partial)) as? [String: Any])
        XCTAssertEqual((first["actions"] as? [[String: Any]])?.first?["id"] as? String, "open-0000")
        XCTAssertNil(first["acceptance_eligible"])
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.appendingPathComponent("performance-complete.json").path))
        watchdog.recordActions(["phase": "open-every-chat", "actions": [["id": "open-0000", "passed": true], ["id": "open-0001", "passed": false]]])
        watchdog.finish(["actions": [], "errors": ["Scenario interrupted"]])
        let last = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: partial)) as? [String: Any])
        XCTAssertEqual((last["actions"] as? [[String: Any]])?.count, 2)
        XCTAssertEqual((last["actions"] as? [[String: Any]])?.last?["passed"] as? Bool, false)
    }

    func testHealthyProbesKeepTheirSampleCadenceButBoundDiskPersistence() {
        var persistence = HeartbeatPersistence()
        var writes: [Double] = []
        let probes = (0...100).map { Double($0) * 0.05 }
        for now in probes {
            if persistence.shouldWrite(now: now, action: "idle-measure", worst: 10, unfinished: false) { writes.append(now) }
        }
        XCTAssertEqual(probes.count, 101, "All 50 ms probes still run")
        XCTAssertLessThan(writes.count, 30, "Healthy idle probes need not atomically replace the same file twenty times a second")
        for (earlier, later) in zip(writes, writes.dropFirst()) {
            XCTAssertLessThanOrEqual(later - earlier, 0.251, "The next 50 ms probe must flush a completed 200 ms batch")
        }
    }
    func testPhaseChangesAndNewMaximumArePublishedBeforeBatchDeadline() {
        var persistence = HeartbeatPersistence()
        XCTAssertTrue(persistence.shouldWrite(now: 0, action: "startup", worst: 10, unfinished: false))
        XCTAssertFalse(persistence.shouldWrite(now: 0.05, action: "startup", worst: 10, unfinished: false))
        XCTAssertTrue(persistence.shouldWrite(now: 0.06, action: "idle-measure", worst: 10, unfinished: false))
        XCTAssertTrue(persistence.shouldWrite(now: 0.07, action: "idle-measure", worst: 251, unfinished: false), "A new violation must not wait for batching")
    }
    func testAnUnansweredUIProbeIsPublishedOnEveryObservation() {
        var persistence = HeartbeatPersistence()
        XCTAssertTrue(persistence.shouldWrite(now: 0, action: "switch:1", worst: 300, unfinished: false))
        for tick in 1...3 {
            XCTAssertTrue(persistence.shouldWrite(now: Double(tick) * 0.05, action: "switch:1", worst: 300, unfinished: true),
                "A currently blocked UI must stay observable even if an earlier maximum was larger")
        }
    }
}
