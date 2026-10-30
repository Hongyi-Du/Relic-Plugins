import XCTest
@testable import Relic

@MainActor final class ToastTests: XCTestCase {
    func testRealExpiryClockPausesAndResumesTheSameToast() async throws {
        var expired = 0
        let toast = NativeToastMessage(text: "Actual timer", seconds: 0.08)
        toast.start { expired += 1 }
        let receipt = try toast.pauseTimer()
        let paused = try XCTUnwrap(receipt["after"] as? [String: Any])
        let remaining = try XCTUnwrap(paused["remaining_ms"] as? Double)
        XCTAssertGreaterThan(remaining, 0); XCTAssertLessThanOrEqual(remaining, 80)
        try await Task.sleep(for: .milliseconds(120))
        XCTAssertEqual(expired, 0)
        XCTAssertEqual(toast.timerSnapshot()["remaining_ms"] as? Double, remaining)
        XCTAssertEqual(toast.timerSnapshot()["instance"] as? String, paused["instance"] as? String)
        let resumed = toast.resumeTimer()
        XCTAssertEqual((resumed["after"] as? [String: Any])?["state"] as? String, "running")
        try await Task.sleep(for: .milliseconds(160))
        XCTAssertEqual(expired, 1); XCTAssertEqual(toast.timerState, "expired")
    }
    func testRemovedToastCancelsItsActualExpiryTask() async throws {
        var expired = false
        let toast = NativeToastMessage(text: "Cancelled", seconds: 0.02)
        toast.start { expired = true }; toast.cancelTimer()
        try await Task.sleep(for: .milliseconds(60))
        XCTAssertFalse(expired); XCTAssertEqual(toast.timerState, "cancelled")
        XCTAssertThrowsError(try toast.pauseTimer())
    }
    func testRepeatedNotificationsKeepIndependentIdentityAndExpiry() {
        let model = Model()
        model.notice = "Copied"; model.notice = "Copied"
        XCTAssertEqual(model.toasts.count, 2)
        let first = model.toasts[0].id, second = model.toasts[1].id
        XCTAssertNotEqual(first, second)
        XCTAssertEqual(model.toasts.map(\.seconds), [3.6,3.6])
        model.dismissToast(first)
        XCTAssertEqual(model.toasts.map(\.id), [second])
        model.showNotice("Renamed", seconds: 5)
        XCTAssertEqual(model.notice, "Renamed")
        XCTAssertEqual(model.toasts.last?.seconds, 5)
        model.dismissToast(second)
        XCTAssertEqual(model.toasts.map(\.text), ["Renamed"])
        model.stop(); XCTAssertTrue(model.toasts.isEmpty)
    }
    func testReadyActionErrorsBecomeToastsWithoutDiscardingOtherNotifications() {
        let model = Model()
        model.error = "Startup error"
        XCTAssertTrue(model.toasts.isEmpty)
        model.ready = true; model.notice = "Saved"; model.error = "Request failed"
        XCTAssertEqual(model.toasts.map(\.text), ["Saved", "Request failed"])
        XCTAssertEqual(model.error, "Request failed", "The actual error remains available to diagnostics")
        model.notice = ""; XCTAssertTrue(model.toasts.isEmpty)
        model.stop()
    }
}
