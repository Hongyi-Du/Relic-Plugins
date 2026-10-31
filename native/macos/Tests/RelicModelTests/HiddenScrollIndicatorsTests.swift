import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class HiddenScrollIndicatorsTests: XCTestCase {
    func testOverflowingTabStripKeepsItsHeightAndScrollsWithoutAGutter() async throws {
        _ = NSApplication.shared
        let root = HStack(spacing: 6) {
            ScrollView(.horizontal) {
                Color.gray.frame(width: 400, height: 28).background(HiddenScrollIndicators())
            }.scrollIndicators(.hidden).frame(height: 28)
            Color.clear.frame(width: 28, height: 28)
        }.padding(.leading, 8).padding(.trailing, 6).frame(width: 340, height: 44)
            .background(ScrollAppearance())
        let host = NSHostingView(rootView: root); host.frame = NSRect(x: 0, y: 0, width: 340, height: 44)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); CATransaction.flush()
        try await Task.sleep(for: .milliseconds(80))
        host.layoutSubtreeIfNeeded()
        func scroll(in view: NSView) -> NSScrollView? {
            (view as? NSScrollView) ?? view.subviews.lazy.compactMap { scroll(in: $0) }.first
        }
        let actual = try XCTUnwrap(scroll(in: host)), document = try XCTUnwrap(actual.documentView)
        XCTAssertFalse(actual.hasHorizontalScroller)
        XCTAssertEqual(actual.frame.height, 28, accuracy: 0.01)
        XCTAssertEqual(actual.contentView.frame.height, 28, accuracy: 0.01)
        XCTAssertGreaterThan(document.frame.width, actual.contentView.bounds.width)
        let bounds = host.convert(actual.bounds, from: actual)
        XCTAssertEqual(bounds.midY, host.bounds.midY, accuracy: 0.01)
        actual.contentView.scroll(to: NSPoint(x: 20, y: actual.contentView.bounds.minY))
        actual.reflectScrolledClipView(actual.contentView)
        XCTAssertEqual(actual.contentView.bounds.minX, 20, accuracy: 0.01,
            "Hiding the indicator must retain real native document scrolling")
    }
}
