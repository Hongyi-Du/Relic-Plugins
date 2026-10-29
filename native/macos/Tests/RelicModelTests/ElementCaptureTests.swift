import XCTest
import AppKit
import RelicAX
import SwiftUI
import ApplicationServices
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
    func testAXSystemFontNamesNeverFallBackToAnotherFamily() throws {
        let font = try XCTUnwrap(ElementCapture.fontFromAX(["AXFontFamily": ".AppleSystemUIFont", "AXFontName": ".SFNS-Bold", "AXFontSize": 12.5]))
        XCTAssertEqual(font.pointSize, 12.5)
        XCTAssertEqual(ElementCapture.cssWeight(font), 700)
        XCTAssertFalse(font.fontName.contains("Times"))
        XCTAssertNil(ElementCapture.fontFromAX(["AXFontFamily": ".AppleSystemUIFont", "AXFontName": ".SFNS-Unknown", "AXFontSize": 12]))
    }
    func testFontEvidenceContainsActualCoreTextFacesAndGlyphs() throws {
        let font = RelicStyle.nativeFont(14, weight: 400)
        let runs = ElementCapture.renderedFonts(NSAttributedString(string: "Relic 组织", attributes: [.font: font]))
        XCTAssertFalse(runs.isEmpty)
        XCTAssertTrue(runs.allSatisfy { !($0["family_name"] as? String ?? "").isEmpty && !($0["postscript_name"] as? String ?? "").isEmpty })
        XCTAssertTrue(runs.contains { $0["postscript_name"] as? String == font.fontName })
        XCTAssertGreaterThan(runs.compactMap { $0["glyph_count"] as? Int }.reduce(0, +), 0)
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

    func testTextKitDynamicColorsResolveInTheActualViewAppearance() throws {
        let view = NSTextView(frame: NSRect(x: 0, y: 0, width: 200, height: 50))
        view.textStorage?.setAttributedString(NSAttributedString(string: "Actual appearance", attributes: [.font: NSFont.systemFont(ofSize: 14), .foregroundColor: NSColor(RelicStyle.ink)]))
        for (appearance, expected) in [(NSAppearance.Name.darkAqua, [236.0, 234, 229, 255]), (.aqua, [27.0, 27, 26, 255])] {
            view.appearance = NSAppearance(named: appearance)
            let style = try XCTUnwrap(ElementCapture.textRuns(view).first?["style"] as? [String: Any])
            let rgba = try XCTUnwrap(style["color"] as? [Double])
            for index in expected.indices { XCTAssertEqual(rgba[index], expected[index], accuracy: 0.001) }
        }
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
