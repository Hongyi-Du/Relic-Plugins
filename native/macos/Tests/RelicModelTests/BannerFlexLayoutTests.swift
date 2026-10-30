import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class BannerFlexLayoutTests: XCTestCase {
    func testNativeMinimumKeepsUnbreakableWordsAndNonbreakingSpaces() {
        func widths(_ text: String) -> BannerTextMetrics.Widths {
            BannerTextMetrics.measure(ReferenceLabel(text, size: 12.5, lines: 0).attributedText)
        }
        let word = widths("unbreakable"), spaced = widths("one two"), joined = widths("one\u{00a0}two")
        XCTAssertEqual(word.minimum, word.natural, accuracy: 0.001)
        XCTAssertLessThan(spaced.minimum, spaced.natural)
        XCTAssertEqual(joined.minimum, joined.natural, accuracy: 0.001)
        let cjk = widths("这是一段可以正常换行的说明。")
        XCTAssertLessThan(cjk.minimum, cjk.natural / 2)
        let narrow = BannerFlexLayout.allocate(available: word.minimum / 2, gap: 8, icon: 15, text: word)
        XCTAssertEqual(narrow.icon, 0)
        XCTAssertEqual(narrow.text, word.minimum)
        let wide = BannerFlexLayout.allocate(available: 1000, gap: 8, icon: 15, text: spaced)
        XCTAssertEqual(wide.icon, 15)
        XCTAssertEqual(wide.text, spaced.natural, "The reference has no flex-grow")
    }

    func testMountedBannerShrinksItsActualIconViewportWithoutDistortingItsGlyph() throws {
        _ = NSApplication.shared
        for source in [String(repeating: "The actual conversation and its actions are shown here. ", count: 4),
                       String(repeating: "这里展示成员会话中的消息和操作。", count: 5)] {
            let label = ReferenceLabel(source, size: 12.5, lineHeight: 20, lines: 0)
            let metrics = BannerTextMetrics.measure(label.attributedText)
            let root = BannerFlexLayout(textWidths: metrics) {
                ReferenceIcon(name: "info", size: 15, flexibleWidth: true)
                label.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(width: 340).fixedSize(horizontal: false, vertical: true)
            let host = NSHostingView(rootView: root)
            host.frame = NSRect(x: 0, y: 0, width: 340, height: 160)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
            defer { window.orderOut(nil); window.contentView = nil; window.close() }
            host.layoutSubtreeIfNeeded()
            func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }
            let views = descendants(host)
            let icon = try XCTUnwrap(views.compactMap { $0 as? ElementPaintProbe.PaintView }.first)
            let text = try XCTUnwrap(views.compactMap { $0 as? ReferenceLabelView }.first)
            let allocation = BannerFlexLayout.allocate(available: 340, gap: 8, icon: 15, text: metrics)
            XCTAssertEqual(icon.bounds.width, allocation.icon, accuracy: 0.5)
            XCTAssertLessThan(icon.bounds.width, 10)
            XCTAssertEqual(icon.bounds.height, 15, accuracy: 0.01)
            let iconFrame = icon.convert(icon.bounds, to: host), textFrame = text.convert(text.bounds, to: host)
            XCTAssertEqual(textFrame.minX - iconFrame.maxX, 8, accuracy: 0.5)
            XCTAssertEqual(text.string, source)
            icon.recordDraws = true; icon.needsDisplay = true; icon.layer?.setNeedsDisplay()
            host.displayIfNeeded(); CATransaction.flush()
            let bitmap = try XCTUnwrap(CaptureRaster.forView(host)); host.cacheDisplay(in: host.bounds, to: bitmap)
            let draw = try XCTUnwrap(icon.currentDraw()), path = ElementCapture.rect(draw["rendered_path_bounds"])
            XCTAssertEqual(path.width, path.height, accuracy: 0.01, "The info circle must stay circular in the narrowed SVG viewport")
            XCTAssertEqual(path.midY, 7.5, accuracy: 0.01)
            XCTAssertEqual(try XCTUnwrap(draw["stroke_width"] as? CGFloat), 1.7 * icon.bounds.width / 24, accuracy: 0.001)
            XCTAssertEqual(icon.backingPaintObservation()["current"] as? Bool, true)
        }
    }
}
