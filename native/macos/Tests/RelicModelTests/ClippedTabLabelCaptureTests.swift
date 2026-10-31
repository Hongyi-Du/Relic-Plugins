import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class ClippedTabLabelCaptureTests: XCTestCase {
    func testFullyClippedRealTabLabelKeepsItsNameWithoutInventingPaintedText() throws {
        _ = NSApplication.shared
        let identity = "relic-tab/actual-clipped-tab"
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 100, height: 40))
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 30, height: 28))
        scroll.borderType = .noBorder; scroll.hasHorizontalScroller = false; scroll.hasVerticalScroller = false
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 120, height: 28))
        let button = NSButton(frame: document.bounds)
        button.title = ""; button.setAccessibilityLabel("Thread"); button.setAccessibilityIdentifier(identity)
        let label = ReferenceLabel("Thread", size: 12.5, owner: identity).makeLabelView()
        label.productionOwner = identity; label.productionParent = identity
        label.frame = NSRect(x: 34, y: 4, width: 60, height: 20)
        button.addSubview(label); document.addSubview(button); scroll.documentView = document; root.addSubview(scroll)
        let window = NSWindow(contentRect: root.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = root; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        root.layoutSubtreeIfNeeded()
        XCTAssertTrue(label.visibleRect.isEmpty || label.visibleRect.isNull,
            "The actual horizontal viewport must clip the label: label=\(label.frame), visible=\(label.visibleRect), clip=\(scroll.contentView.bounds)")
        let actual = RelicAXRead(button)
        let source: [String: Any] = ["id": "actual-tab", "kind": "tab",
            "identifier": actual["identifier"]!, "text": actual["label"]!, "name": actual["label"]!]
        var rows = [source]
        ClippedTabLabelCapture.attach(to: &rows, labels: [label], window: window)
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows[0]["text"] as? String, "")
        XCTAssertEqual(rows[0]["name"] as? String, "Thread")
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: rows))
        let receipt = try XCTUnwrap(rows[0]["native_clipped_tab_label"] as? [String: Any])
        XCTAssertEqual(receipt["source_text"] as? String, "Thread")

        label.setFrameOrigin(NSPoint(x: 20, y: 4))
        XCTAssertFalse(label.visibleRect.isEmpty)
        rows = [source]; ClippedTabLabelCapture.attach(to: &rows, labels: [label], window: window)
        XCTAssertEqual(rows[0]["text"] as? String, "Thread", "A partially visible label must retain its text measurement")
        XCTAssertNil(rows[0]["native_clipped_tab_label"])
        label.setFrameOrigin(NSPoint(x: 34, y: 4))
        rows = [source]; ClippedTabLabelCapture.attach(to: &rows, labels: [label, label], window: window)
        XCTAssertNil(rows[0]["native_clipped_tab_label"], "Ambiguous labels cannot erase a control's text")
        label.productionParent = "foreign-parent"
        rows = [source]; ClippedTabLabelCapture.attach(to: &rows, labels: [label], window: window)
        XCTAssertNil(rows[0]["native_clipped_tab_label"])
    }
}
