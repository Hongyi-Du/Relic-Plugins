import XCTest
import AppKit
@testable import Relic

@MainActor final class ScrollAppearanceTests: XCTestCase {
    func testScrollbarPositionUsesActualProviderRangeWithoutClampingUnknownValues() {
        XCTAssertEqual(ScrollbarCapture.normalized(value: 35, minimum: 10, maximum: 110), 0.25)
        XCTAssertEqual(ScrollbarCapture.normalized(value: 10, minimum: 10, maximum: 10), 0)
        XCTAssertNil(ScrollbarCapture.normalized(value: NSNull(), minimum: 0, maximum: 1))
        XCTAssertNil(ScrollbarCapture.normalized(value: 1.2, minimum: 0, maximum: 1))
        XCTAssertNil(ScrollbarCapture.normalized(value: 0, minimum: 2, maximum: 1))
    }

    func testOverflowReservesTheActualTenPointScrollerWidth() {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
        scroll.borderType = .noBorder; scroll.hasVerticalScroller = true
        scroll.verticalScroller = ReferenceScroller(); scroll.scrollerStyle = .legacy
        scroll.autohidesScrollers = true
        scroll.documentView = NSView(frame: NSRect(x: 0, y: 0, width: 190, height: 600))
        scroll.tile()
        XCTAssertEqual(scroll.contentSize.width, 190, accuracy: 0.01)
        XCTAssertEqual(scroll.verticalScroller?.frame.width ?? 0, 10, accuracy: 0.01)
        let scroller = scroll.verticalScroller as! ReferenceScroller
        XCTAssertEqual(scroller.paintedKnob.width, 4, accuracy: 0.01)
    }
}
