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
        XCTAssertEqual(rendered.string, "Review both in README.md.")
        let plain = try XCTUnwrap(rendered.attribute(.font, at: 0, effectiveRange: nil) as? NSFont)
        let bold = try XCTUnwrap(rendered.attribute(.font, at: 7, effectiveRange: nil) as? NSFont)
        let code = try XCTUnwrap(rendered.attribute(.font, at: 15, effectiveRange: nil) as? NSFont)
        XCTAssertNotEqual(plain.fontName, bold.fontName)
        XCTAssertEqual(code.fontName, "Menlo-Regular")
        XCTAssertEqual(code.pointSize, 12.6, accuracy: 0.001)
        XCTAssertGreaterThan(NativeTextStyle.preferredWidth(rendered), 0)
    }
}
