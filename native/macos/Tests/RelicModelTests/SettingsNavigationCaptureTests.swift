import XCTest
import AppKit
@testable import Relic

@MainActor final class SettingsNavigationCaptureTests: XCTestCase {
    func testPageReceiptReadsMountedNativeContentInsideItsAllocation() throws {
        _ = NSApplication.shared
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 200))
        let page = SettingsContentProbe.Probe(frame: NSRect(x: 200, y: 0, width: 200, height: 200))
        let outside = NSTextField(labelWithString: "Navigation")
        outside.frame = NSRect(x: 10, y: 40, width: 100, height: 24)
        let inside = NSTextField(labelWithString: "Actual page content")
        inside.frame = NSRect(x: 220, y: 40, width: 150, height: 24)
        root.addSubview(page); root.addSubview(outside); root.addSubview(inside)
        let window = NSWindow(contentRect: root.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = root; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let before = page.observation()
        let content = try XCTUnwrap(before["native_content"] as? [[String: Any]])
        XCTAssertEqual(content.compactMap { $0["text"] as? String }, ["Actual page content"])
        XCTAssertEqual(content.first?["identity"] as? String, String(describing: ObjectIdentifier(inside)))
        inside.stringValue = "Changed production content"
        let changed = try XCTUnwrap(page.observation()["native_content"] as? [[String: Any]])
        XCTAssertEqual(changed.first?["text"] as? String, "Changed production content")
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: page.observation()))
        XCTAssertFalse(page.isAccessibilityElement()); XCTAssertNil(page.hitTest(NSPoint(x: 20, y: 20)))
    }

    func testNavigationProbePreservesSeparateHoverAndSelectionBindings() throws {
        let probe = SettingsNavigationProbe.Probe(frame: NSRect(x: 0, y: 0, width: 200, height: 34))
        let trace = SettingsNavigationTrace()
        probe.key = "notify"; probe.owner = "actual-owner"; probe.trace = trace
        probe.selected = false; probe.hovered = true; trace.receivedHover(true)
        let row = probe.observation()
        XCTAssertEqual(row["selected"] as? Bool, false); XCTAssertEqual(row["hovered"] as? Bool, true)
        XCTAssertEqual((row["hover_callbacks"] as? [[String: Any]])?.last?["hovered"] as? Bool, true)
        XCTAssertFalse(probe.isAccessibilityElement()); XCTAssertNil(probe.hitTest(.zero))
        XCTAssertEqual(row["owner"] as? String, "actual-owner")
    }
}
