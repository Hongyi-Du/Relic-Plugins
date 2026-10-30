import XCTest
import AppKit
@testable import Relic

@MainActor final class TextAreaResizeTests: XCTestCase {
    func testCornerHitTestingDoesNotBlockEditor() {
        let parent = NSView(frame: NSRect(x: 0, y: 0, width: 600, height: 400))
        let grip = TextAreaResizeView(frame: NSRect(x: 20, y: 30, width: 400, height: 76))
        parent.addSubview(grip)
        XCTAssertNil(grip.hitTest(grip.convert(NSPoint(x: 50, y: 30), to: parent)))
        XCTAssertTrue(grip.hitTest(grip.convert(NSPoint(x: 397, y: 73), to: parent)) === grip)
    }
    func testScreenDeltaTracksBothDimensionsAndMinimum() {
        let size = CGSize(width: 476, height: 76), start = NSPoint(x: 950, y: 500), minimum = CGSize(width: 24, height: 36)
        XCTAssertEqual(TextAreaResizeView.resized(size, from: start, to: NSPoint(x: 950, y: 436), minimum: minimum), CGSize(width: 476, height: 140))
        XCTAssertEqual(TextAreaResizeView.resized(size, from: start, to: NSPoint(x: 990, y: 468), minimum: minimum), CGSize(width: 516, height: 108))
        XCTAssertEqual(TextAreaResizeView.resized(size, from: start, to: NSPoint(x: 0, y: 1000), minimum: minimum), minimum)
    }
}
