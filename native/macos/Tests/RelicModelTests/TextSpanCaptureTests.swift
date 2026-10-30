import XCTest
import AppKit
@testable import Relic

@MainActor final class TextSpanCaptureTests: XCTestCase {
    func testActualFallbackFontsStayInsideTheirProductionLabel() throws {
        let view = ReferenceLabel("→ 全体", size: 12, lineHeight: 15.6, lines: 0).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 120, height: 40)
        view.textContainer?.containerSize = NSSize(width: 120, height: 40)
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let rows = ElementCapture.textRuns(view)
        XCTAssertEqual(rows.count, 1)
        let row = try XCTUnwrap(rows.first)
        XCTAssertEqual(row["text"] as? String, "→ 全体")
        let actual = try XCTUnwrap(row["native_attribute_runs"] as? [[String: Any]])
        XCTAssertGreaterThan(actual.count, 1, "The real TextKit fallback attributes remain available inside the one label")
        let style = try XCTUnwrap(row["style"] as? [String: Any])
        let fonts = try XCTUnwrap(style["rendered_fonts"] as? [[String: Any]])
        XCTAssertGreaterThan(Set(fonts.compactMap { $0["postscript_name"] as? String }).count, 1)
        XCTAssertEqual(style["fontSize"] as? Double, 12)
        XCTAssertEqual(style["fontWeight"] as? Int, 400)
        let range = try XCTUnwrap(row["range"] as? [String: Int])
        XCTAssertEqual(range["length"], (view.string as NSString).length)
    }

    func testUnmarkedRichTextPreservesItsDistinctVisibleEmphasis() {
        let storage = NSMutableAttributedString(string: "Plain bold", attributes: [.font: NSFont.systemFont(ofSize: 12)])
        storage.addAttribute(.font, value: NSFont.boldSystemFont(ofSize: 12), range: NSRange(location: 6, length: 4))
        var ranges: [NSRange] = []
        NativeTextSpans.enumerate(storage) { _, range, _, _ in ranges.append(range) }
        XCTAssertEqual(ranges, [NSRange(location: 0, length: 6), NSRange(location: 6, length: 4)])
    }
}
