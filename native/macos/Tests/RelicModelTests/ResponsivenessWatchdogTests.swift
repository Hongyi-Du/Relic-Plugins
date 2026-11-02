import XCTest
@testable import Relic

final class ResponsivenessWatchdogTests: XCTestCase {
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
