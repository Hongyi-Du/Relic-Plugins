import XCTest
import AppKit
@testable import Relic

@MainActor final class TextAreaResizeTests: XCTestCase {
    func testShrinkingViewportDoesNotKeepAnEmptyEditorsOldScrollExtent() {
        let editor = ComposerTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 200))
        editor.isVerticallyResizable = true; editor.string = ""
        editor.fitViewport(height: 120)
        XCTAssertEqual(editor.frame.height, 120, accuracy: 0.01)
        editor.fitViewport(height: 60)
        XCTAssertEqual(editor.frame.height, 60, accuracy: 0.01)
        editor.string = Array(repeating: "A real text line", count: 20).joined(separator: "\n")
        editor.fitViewport(height: 60)
        XCTAssertGreaterThan(editor.frame.height, 60, "Real overflow remains scrollable")
    }
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
