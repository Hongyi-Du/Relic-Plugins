import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class ElementCaptureTests: XCTestCase {
    func testScreenCoordinatesBecomeContentCoordinatesWithoutTitlebarOffset() {
        let content = NSRect(x: 100, y: 200, width: 1024, height: 700)
        let element = NSRect(x: 140, y: 550, width: 80, height: 20)
        XCTAssertEqual(ElementCapture.topLeft(element, in: content), NSRect(x: 40, y: 330, width: 80, height: 20))
        XCTAssertEqual(ElementCapture.topLeft(element.offsetBy(dx: 600, dy: -120), in: content.offsetBy(dx: 600, dy: -120)), ElementCapture.topLeft(element, in: content))
    }

    func testActualSystemFontsRetainSizeAndSemiboldWeight() {
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .regular)), 400)
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .semibold)), 600)
        XCTAssertEqual(ElementCapture.cssWeight(.systemFont(ofSize: 14, weight: .bold)), 700)
    }

    func testInformalAccessibilityNodesDoNotRequireProtocolConformance() {
        let child = InformalAccessibilityNode(label: "Actual child", children: [])
        let root = InformalAccessibilityNode(label: "Actual root", children: [child])
        let properties = RelicAXRead(root)
        XCTAssertEqual(properties["role"] as? String, "AXStaticText")
        XCTAssertEqual(properties["label"] as? String, "Actual root")
        XCTAssertEqual((properties["frame"] as? NSValue)?.rectValue, NSRect(x: 12, y: 34, width: 80, height: 20))
        XCTAssertEqual(RelicAXChildren(root).count, 1)
        XCTAssertTrue((RelicAXChildren(root).first as AnyObject?) === child)
    }
    func testTextKitCaptureUsesActualRunFontsAndWrappedLineFragments() throws {
        let view = NSTextView(frame: NSRect(x: 0, y: 0, width: 90, height: 300))
        view.isEditable = false; view.textContainerInset = .zero
        view.textContainer?.lineFragmentPadding = 0
        view.textContainer?.containerSize = NSSize(width: 90, height: 300)
        let source = NSMutableAttributedString(string: "Header. A longer description wraps onto several lines.",
                                              attributes: [.font: NSFont.systemFont(ofSize: 12), .foregroundColor: NSColor.red])
        source.addAttribute(.font, value: NSFont.systemFont(ofSize: 14, weight: .bold), range: NSRange(location: 0, length: 7))
        view.textStorage?.setAttributedString(source)
        let rows = ElementCapture.textRuns(view)
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(rows.compactMap { $0["text"] as? String }.joined(), source.string)
        let first = try XCTUnwrap(rows.first?["style"] as? [String: Any])
        XCTAssertEqual(first["fontSize"] as? Double, 14); XCTAssertEqual(first["fontWeight"] as? Int, 700)
        let last = try XCTUnwrap(rows.last?["layout"] as? [String: Any])
        XCTAssertEqual(last["wrap"] as? String, "word")
        XCTAssertGreaterThan(try XCTUnwrap(last["line_count"] as? Int), 1)
    }
}

private final class InformalAccessibilityNode: NSObject {
    let label: String
    let children: [InformalAccessibilityNode]
    init(label: String, children: [InformalAccessibilityNode]) { self.label = label; self.children = children }
    @objc func accessibilityRole() -> String { "AXStaticText" }
    @objc func accessibilityLabel() -> String { label }
    @objc func accessibilityChildren() -> [Any] { children }
    @objc func accessibilityFrame() -> NSRect { NSRect(x: 12, y: 34, width: 80, height: 20) }
    @objc func isAccessibilityElement() -> Bool { true }
}
