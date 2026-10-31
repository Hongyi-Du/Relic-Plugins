import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class ScrollAppearanceTests: XCTestCase {
    func testScrollViewsMountedAfterInitialLayoutReceiveTheirNativeStyleOnWindowUpdate() throws {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 300, height: 200), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 200))
        let probe = ScrollAppearance.Probe(frame: .zero)
        root.addSubview(probe); window.contentView = root
        defer { window.contentView = nil; window.close() }
        root.layoutSubtreeIfNeeded()
        func newScroll() -> NSScrollView {
            let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
            scroll.borderType = .noBorder; scroll.hasVerticalScroller = true
            scroll.documentView = NSView(frame: NSRect(x: 0, y: 0, width: 190, height: 600))
            root.addSubview(scroll); return scroll
        }
        let late = newScroll()
        XCTAssertFalse(late.verticalScroller is ReferenceScroller)
        window.update(); late.tile()
        let scroller = try XCTUnwrap(late.verticalScroller as? ReferenceScroller)
        XCTAssertEqual(late.contentSize.width, 190, accuracy: 0.01)
        XCTAssertEqual(scroller.frame.width, 10, accuracy: 0.01)
        late.contentView.scroll(to: NSPoint(x: 0, y: 100))
        late.reflectScrolledClipView(late.contentView)
        let position = late.contentView.bounds.origin
        window.update()
        XCTAssertTrue(late.verticalScroller === scroller, "Repeated updates retain the actual native scroller and its state")
        XCTAssertEqual(late.contentView.bounds.origin, position)
        probe.removeFromSuperview()
        let detached = newScroll(); window.update()
        XCTAssertFalse(detached.verticalScroller is ReferenceScroller, "An unmounted observer must leave its former window alone")
    }

    func testRoleOnlyReaderDoesNotEnumerateTheQueriedElementsChildren() {
        final class Part: NSAccessibilityElement {
            var childReads = 0
            override func accessibilityRole() -> NSAccessibility.Role? { .valueIndicator }
            override func accessibilityChildren() -> [Any]? { childReads += 1; return [] }
        }
        let part = Part()
        XCTAssertEqual(RelicAXRole(part), "AXValueIndicator")
        XCTAssertEqual(part.childReads, 0)
    }

    func testThumbOnlyScrollerDoesNotExposeUnpaintedLegacyButtons() throws {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
        scroll.hasVerticalScroller = true; scroll.verticalScroller = ReferenceScroller()
        scroll.scrollerStyle = .legacy; scroll.autohidesScrollers = false
        scroll.documentView = NSView(frame: NSRect(x: 0, y: 0, width: 190, height: 600)); scroll.tile()
        let scroller = try XCTUnwrap(scroll.verticalScroller as? ReferenceScroller)
        let children = RelicAXChildren(scroller)
        XCTAssertEqual(children.count, 1)
        XCTAssertEqual(RelicAXRead(try XCTUnwrap(children.first))["role"] as? String, "AXValueIndicator")
        // Role registration reenters the parent's child lookup on macOS 15.
        // Subsequent complete snapshots must retain one real native thumb.
        for _ in 0..<3 {
            let current = RelicAXChildren(scroller)
            XCTAssertEqual(current.count, 1)
            let thumb = try XCTUnwrap(current.first)
            XCTAssertEqual(RelicAXRead(thumb)["role"] as? String, "AXValueIndicator")
            XCTAssertEqual(scroller.accessibilityIndex(ofChild: thumb), 0)
        }
        XCTAssertTrue(scroller.isEnabled)
        XCTAssertGreaterThan(scroller.rect(for: .knob).height, 0)
        scroller.doubleValue = 0.5
        XCTAssertEqual(scroller.doubleValue, 0.5, accuracy: 0.001)
    }

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
