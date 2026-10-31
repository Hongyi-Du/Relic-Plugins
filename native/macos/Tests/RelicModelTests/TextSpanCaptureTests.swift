import XCTest
import AppKit
@testable import Relic

@MainActor final class TextSpanCaptureTests: XCTestCase {
    func testPlainToolOutputRemainsOneTextElementAcrossNativeFontFallbacks() throws {
        let source = "已读取 README.md\n\t布局：三栏\n\t检查：文字、间距与状态\n等待逐元素比较。"
        let storage = NSTextStorage(attributedString: NativeTextStyle.render(AttributedString(source), size: 11.5,
            lineHeight: 17.825, monospaced: true, uniformSource: true))
        let layout = NativeGlyphLayoutManager(), container = NSTextContainer(containerSize: NSSize(width: 650, height: 120))
        layout.recordDraws = true; storage.addLayoutManager(layout); layout.addTextContainer(container)
        let view = QuoteTextView(frame: NSRect(x: 0, y: 0, width: 650, height: 120), textContainer: container)
        view.sourceStorage = storage; view.isEditable = false; view.isSelectable = true
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view)); view.cacheDisplay(in: view.bounds, to: bitmap)
        let rows = ElementCapture.textRuns(view)
        XCTAssertEqual(rows.count, 1)
        let row = try XCTUnwrap(rows.first)
        XCTAssertEqual(row["text"] as? String, source)
        XCTAssertGreaterThan(try XCTUnwrap(row["native_attribute_runs"] as? [[String: Any]]).count, 1)
        let accessible = try XCTUnwrap(row["native_accessible_range"] as? [String: Any])
        XCTAssertEqual(accessible["value"] as? String, source)
        XCTAssertEqual(accessible["matches_rendered_text"] as? Bool, true)
        let fonts = try XCTUnwrap((row["style"] as? [String: Any])?["rendered_fonts"] as? [[String: Any]])
        XCTAssertGreaterThan(Set(fonts.compactMap { $0["postscript_name"] as? String }).count, 1)
    }

    func testRichSpanAccessibleValuesComeFromTheActualNativeRangeAPI() throws {
        let storage = NSTextStorage(attributedString: NativeTextStyle.render(try AttributedString(markdown: "Before **bold** after"), size: 14))
        let layout = NativeGlyphLayoutManager(), container = NSTextContainer(containerSize: NSSize(width: 300, height: 80))
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        let view = QuoteTextView(frame: NSRect(x: 0, y: 0, width: 300, height: 80), textContainer: container)
        view.sourceStorage = storage; view.isEditable = false; view.isSelectable = true
        layout.ensureLayout(for: container)
        let rows = ElementCapture.textRuns(view)
        XCTAssertEqual(rows.compactMap { $0["text"] as? String }, ["Before ", "bold", " after"])
        for row in rows {
            let accessible = try XCTUnwrap(row["native_accessible_range"] as? [String: Any])
            XCTAssertEqual(accessible["value"] as? String, row["text"] as? String)
            XCTAssertEqual(accessible["matches_rendered_text"] as? Bool, true)
        }
    }
    func testActualFallbackFontsStayInsideTheirProductionLabel() throws {
        let view = ReferenceLabel("→ 全体", size: 12, lineHeight: 15.6, lines: 0).makeLabelView()
        (view.layoutManager as? NativeGlyphLayoutManager)?.recordDraws = true
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
        XCTAssertTrue(fonts.allSatisfy { $0["provider"] as? String == "production NSLayoutManager.showCGGlyphs callback" })
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
