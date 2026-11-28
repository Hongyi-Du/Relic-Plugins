import XCTest
import AppKit
@testable import Relic

@MainActor final class RenderReadinessTests: XCTestCase {
    func testVisibleUnformattedTextAndMissingRequestedInspectorFailReadiness() {
        XCTAssertFalse(RenderReadiness.Observation(markdown: 3, pendingMarkdown: 1, inspectors: 1, expectInspector: true).ready)
        XCTAssertFalse(RenderReadiness.Observation(markdown: 3, pendingMarkdown: 0, inspectors: 0, expectInspector: true).ready)
        XCTAssertTrue(RenderReadiness.Observation(markdown: 3, pendingMarkdown: 0, inspectors: 1, expectInspector: true).ready)
        XCTAssertTrue(RenderReadiness.Observation(markdown: 3, pendingMarkdown: 0, inspectors: 0, expectInspector: false).ready)
    }
    func testHiddenAndClippedProbeDoesNotCountAsVisibleMarkdown() {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 100))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 200, height: 500))
        scroll.documentView = document; scroll.tile()
        let visible = RenderReadiness.Probe(frame: NSRect(x: 0, y: scroll.contentView.bounds.minY, width: 100, height: 30))
        document.addSubview(visible)
        XCTAssertTrue(visible.visibleInViewport)
        visible.isHidden = true; XCTAssertFalse(visible.visibleInViewport)
        visible.isHidden = false
        visible.setFrameOrigin(NSPoint(x: 0, y: scroll.contentView.bounds.maxY + 10))
        XCTAssertFalse(visible.visibleInViewport)
    }
}
