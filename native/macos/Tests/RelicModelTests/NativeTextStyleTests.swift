import XCTest
import AppKit
import RelicCore
@testable import Relic

@MainActor final class NativeTextStyleTests: XCTestCase {
    func testPreferredWidthUsesLongestLineAndTheActualCodeFont() throws {
        let first = NativeTextStyle.render(AttributedString("review('macOS')"), size: 11.25, monospaced: true)
        let multiline = NativeTextStyle.render(AttributedString("x\nreview('macOS')"), size: 11.25, monospaced: true)
        XCTAssertEqual(NativeTextStyle.preferredWidth(first), NativeTextStyle.preferredWidth(multiline), accuracy: 0.01)
        let font = try XCTUnwrap(first.attribute(.font, at: 0, effectiveRange: nil) as? NSFont)
        XCTAssertEqual(font.fontName, "Menlo-Regular")
        XCTAssertEqual(font.pointSize, 11.25)
    }
    func testSizingAndRenderingKeepInlineCodeAndEmphasisRuns() throws {
        let rendered = NativeTextStyle.render(NativeMarkdown.attributed("Review **both** in `README.md`."), size: 14)
        XCTAssertEqual(NativeInlineCode.source(rendered), "Review both in README.md.")
        let plain = try XCTUnwrap(rendered.attribute(.font, at: 0, effectiveRange: nil) as? NSFont)
        let bold = try XCTUnwrap(rendered.attribute(.font, at: 7, effectiveRange: nil) as? NSFont)
        let code = try XCTUnwrap(rendered.attribute(.font, at: (rendered.string as NSString).range(of: "README.md").location, effectiveRange: nil) as? NSFont)
        XCTAssertNotEqual(plain.fontName, bold.fontName)
        XCTAssertEqual(code.fontName, "Menlo-Regular")
        XCTAssertEqual(code.pointSize, 12.6, accuracy: 0.001)
        XCTAssertGreaterThan(NativeTextStyle.preferredWidth(rendered), 0)
    }
    func testInlineCodePaddingParticipatesInLayoutAndKeepsCopiedSource() throws {
        let decorated = NativeTextStyle.render(NativeMarkdown.attributed("`README.md`"), size: 14)
        let plain = NativeTextStyle.render(AttributedString("README.md"), size: 12.6, monospaced: true)
        XCTAssertEqual(NativeTextStyle.preferredWidth(decorated) - NativeTextStyle.preferredWidth(plain), 10, accuracy: 0.01)
        let storage = NSTextStorage(attributedString: decorated), manager = InlineCodeLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 300, height: 100))
        container.lineFragmentPadding = 0; storage.addLayoutManager(manager); manager.addTextContainer(container)
        let fragments = manager.codeFragments(in: container)
        XCTAssertEqual(fragments.count, 1)
        XCTAssertEqual(try XCTUnwrap(fragments.first).rect.width, 78.28125, accuracy: 0.1)
        XCTAssertEqual(NativeInlineCode.source(decorated.attributedSubstring(from: NSRange(location: 1, length: 9))), "README.md")
        XCTAssertEqual(NativeInlineCode.source(NSAttributedString(string: "Actual \u{FFFC} input")), "Actual \u{FFFC} input")
    }
}
