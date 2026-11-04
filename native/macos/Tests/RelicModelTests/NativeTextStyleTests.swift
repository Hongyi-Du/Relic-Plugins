import XCTest
import AppKit
import RelicCore
@testable import Relic

@MainActor final class NativeTextStyleTests: XCTestCase {
    func testPreformattedTabsUseEightActualMonospacedAdvances() throws {
        let rendered = NativeTextStyle.render(AttributedString("a\tb"), size: 11.5, monospaced: true)
        let storage = NSTextStorage(attributedString: rendered), layout = NSLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 300, height: 100))
        container.lineFragmentPadding = 0; storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        let b = layout.glyphIndexForCharacter(at: 2)
        XCTAssertEqual(layout.location(forGlyphAt: b).x, 55.3828125, accuracy: 0.1,
            "Actual 11.5px Menlo space advance is 6.9228515625; CSS pre-wrap uses tab-size 8")
        XCTAssertEqual(storage.string, "a\tb")
    }

    func testFixedHeightCodeCentersLeadingWithoutChangingLineHeightOrGlyphAdvance() throws {
        let view = ReferenceLabel("# Native app review\nNext line", size: 12.5, lineHeight: 20.625, lines: 0, monospaced: true).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 300, height: 80)
        let manager = try XCTUnwrap(view.layoutManager), container = try XCTUnwrap(view.textContainer)
        manager.ensureLayout(for: container)
        var baselines: [CGFloat] = [], heights: [CGFloat] = []
        manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { line, _, _, glyphs, _ in
            baselines.append(line.minY + manager.location(forGlyphAt: glyphs.location).y); heights.append(line.height)
        }
        // Independent Menlo draw: the former TextKit baseline was 17.625px,
        // with all 5.625px of extra leading above it. Centered leading moves
        // it to 14.8125 while retaining the 20.625px line step and 143px advance.
        XCTAssertEqual(try XCTUnwrap(baselines.first), 14.8125, accuracy: 0.01)
        XCTAssertEqual(baselines.count, 2)
        XCTAssertEqual(baselines[1] - baselines[0], 20.625, accuracy: 0.01)
        XCTAssertTrue(heights.allSatisfy { abs($0 - 20.625) < 0.01 })
        XCTAssertEqual(NativeTextGeometry.advances(manager, container: container, characters: NSRange(location: 0, length: 19)).envelope?.width ?? 0, 143, accuracy: 0.5)
    }

    func testDocumentLineAdvancesDoNotIncludeTheNewlineEditingCaret() throws {
        let source = "# Native app review\n\nKeep the familiar three-column layout with native system controls.\n"
        let storage = NSTextStorage(attributedString: NativeTextStyle.render(AttributedString(source), size: 12.5, lineHeight: 20.625, monospaced: true, uniformSource: true))
        let manager = NSLayoutManager(), container = NSTextContainer(containerSize: NSSize(width: 664, height: 200))
        container.lineFragmentPadding = 0; storage.addLayoutManager(manager); manager.addTextContainer(container)
        manager.ensureLayout(for: container)
        let measured = NativeTextGeometry.advances(manager, container: container, characters: NSRange(location: 0, length: storage.length))
        XCTAssertTrue(measured.complete)
        XCTAssertEqual(measured.rectangles.count, 3, "The empty source line remains in the raw geometry receipt")
        for (rect, width) in zip(measured.rectangles, [CGFloat(143), 0, 496.703125]) { XCTAssertEqual(rect.width, width, accuracy: 0.5) }
        XCTAssertEqual(try XCTUnwrap(measured.envelope).width, 496.703125, accuracy: 0.5)
        XCTAssertEqual(storage.string, source)
    }

    func testReadOnlyDocumentDoesNotReserveATerminalInsertionLine() {
        // Actual 0a1d569 en-US/dark/1024x700 document: 14 lines at 20.625px,
        // including four empty interior lines. The 318.75px reference card
        // includes 30px of border/padding, with no fifteenth editing line.
        let source = "# Native app review\n\nKeep the familiar three-column layout with native system controls.\n\n## This week\n\n- Compact organization tree\n- Clear conversation and composer\n- Light and dark themes\n\n| Project | Status |\n| --- | --- |\n| Windows | In review |\n| macOS | In review |\n"
        let rendered = NativeTextStyle.render(AttributedString(source), size: 12.5, lineHeight: 20.625, monospaced: true, uniformSource: true)
        let measured = NativeTextStyle.contentSize(rendered, available: 664)
        XCTAssertEqual(measured.height + 30, 318.75, accuracy: 0.01)
        XCTAssertEqual(rendered.string, source, "Measuring read-only content must retain the copyable terminal newline")
        let withoutTerminal = NativeTextStyle.render(AttributedString(String(source.dropLast())), size: 12.5, lineHeight: 20.625, monospaced: true)
        XCTAssertEqual(measured.height, NativeTextStyle.contentSize(withoutTerminal, available: 664).height, accuracy: 0.01)
        let narrow = NativeTextStyle.contentSize(rendered, available: 180)
        XCTAssertGreaterThan(narrow.height, measured.height, "Real wrapping still contributes to height")
    }

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
