import XCTest
import AppKit
@testable import Relic

@MainActor final class ElementCaptureTests: XCTestCase {
    func testScreenCoordinatesBecomeContentCoordinatesWithoutTitlebarOffset() {
        let content = NSRect(x: 100, y: 200, width: 1024, height: 700)
        let element = NSRect(x: 140, y: 550, width: 80, height: 20)
        XCTAssertEqual(ElementCapture.topLeft(element, in: content), NSRect(x: 40, y: 330, width: 80, height: 20))
        XCTAssertEqual(ElementCapture.topLeft(element.offsetBy(dx: 600, dy: -120), in: content.offsetBy(dx: 600, dy: -120)), ElementCapture.topLeft(element, in: content))
    }

    func testActualSystemFontsRetainSizeAndSemiboldWeight() {
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .regular)), 400)
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .semibold)), 600)
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .bold)), 700)
    }
}
