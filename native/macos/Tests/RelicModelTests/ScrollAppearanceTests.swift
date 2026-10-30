import XCTest
import AppKit
@testable import Relic

@MainActor final class ScrollAppearanceTests: XCTestCase {
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
