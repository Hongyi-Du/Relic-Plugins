import XCTest
import AppKit
@testable import Relic

@MainActor final class GeometryCaptureTests: XCTestCase {
    func testScrollHistoryRetainsActualBoundsWithoutChangingThem() throws {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 100))
        scroll.documentView = NSView(frame: NSRect(x: 0, y: 0, width: 200, height: 600))
        scroll.contentView.scroll(to: NSPoint(x: 0, y: 180))
        let before = scroll.contentView.bounds
        ScrollGeometryTrace.reset()
        defer { ScrollGeometryTrace.reset() }
        ScrollGeometryTrace.observe(scroll, phase: "test-observe")
        XCTAssertEqual(scroll.contentView.bounds, before)
        scroll.contentView.scroll(to: NSPoint(x: 0, y: 200))
        let views = try XCTUnwrap(ScrollGeometryTrace.receipt()["scroll_views"] as? [[String: Any]])
        let rows = try XCTUnwrap(views.first?["observations"] as? [[String: Any]])
        XCTAssertTrue(rows.contains { ($0["clip_bounds"] as? [String: Double])?["y"] == 180 })
        XCTAssertTrue(rows.contains { ($0["clip_bounds"] as? [String: Double])?["y"] == 200 })
        XCTAssertEqual(scroll.contentView.bounds.origin.y, 200)
        XCTAssertEqual(scroll.documentView?.frame.height, 600)
    }

    func testSnapshotRetainsScrolledBoundsWithoutRelayout() throws {
        let clip = NSClipView(frame: NSRect(x: 0, y: 0, width: 200, height: 100))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 200, height: 600))
        let label = ReferenceLabel("Measured native text").makeLabelView()
        label.frame = NSRect(x: 10, y: 240, width: 180, height: 24)
        document.addSubview(label); clip.documentView = document
        clip.scroll(to: NSPoint(x: 0, y: 180))
        let expected = clip.bounds
        let first = GeometryCaptureSession.snapshot(clip)
        let id = String(describing: ObjectIdentifier(clip))
        XCTAssertEqual(try XCTUnwrap(first[id]?["bounds"] as? [String: Double])["y"], 180)
        XCTAssertEqual(clip.bounds, expected)
        XCTAssertEqual(label.frame, NSRect(x: 10, y: 240, width: 180, height: 24))
        clip.scroll(to: NSPoint(x: 0, y: 200))
        let second = GeometryCaptureSession.snapshot(clip)
        XCTAssertEqual(try XCTUnwrap(second[id]?["bounds"] as? [String: Double])["y"], 200)
        XCTAssertFalse(NSDictionary(dictionary: first[id]!).isEqual(to: second[id]!))
    }
}
