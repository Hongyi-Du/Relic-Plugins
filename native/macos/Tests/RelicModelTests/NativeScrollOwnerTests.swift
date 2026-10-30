import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeScrollOwnerTests: XCTestCase {
    func testDialogNameBelongsToTheActualScrollableViewport() throws {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 760, height: 370))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 760, height: 600))
        scroll.documentView = document
        let label = NSTextField(labelWithString: "Protocol summary")
        document.addSubview(label)
        let mount = NativeScrollOwner.Mount()
        mount.update(identifier: "relic-dialog-panel/test", title: "Copies")
        document.addSubview(mount)
        mount.layoutSubtreeIfNeeded()
        XCTAssertTrue(mount.owner === scroll)
        XCTAssertEqual(scroll.accessibilityRole(), .scrollArea)
        XCTAssertEqual(scroll.accessibilityIdentifier(), "relic-dialog-panel/test")
        XCTAssertEqual(scroll.accessibilityLabel(), "Copies")
        XCTAssertFalse(mount.isAccessibilityElement())
        XCTAssertTrue(mount.subviews.isEmpty)
        XCTAssertTrue(label.superview === document)
        XCTAssertTrue(scroll.documentView === document)
        mount.update(identifier: "relic-dialog-panel/test", title: "抄送")
        XCTAssertEqual(scroll.accessibilityLabel(), "抄送")
        let before = scroll.contentView.bounds.origin
        scroll.contentView.scroll(to: NSPoint(x: 0, y: 100))
        XCTAssertNotEqual(scroll.contentView.bounds.origin, before, "Naming retains native scrolling")
    }
}
