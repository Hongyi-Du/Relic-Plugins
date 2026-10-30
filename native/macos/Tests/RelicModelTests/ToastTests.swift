import XCTest
@testable import Relic

@MainActor final class ToastTests: XCTestCase {
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
