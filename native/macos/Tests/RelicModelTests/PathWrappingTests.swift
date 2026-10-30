import XCTest
import AppKit
@testable import Relic

@MainActor final class PathWrappingTests: XCTestCase {
    func testMemberDirectoryUsesTheReferenceWordBoundariesWithoutChangingItsText() throws {
        let source = "/Users/runner/work/Relic-Plugins/Relic-Plugins/visual/macos/dat…"
        let view = ReferenceLabel(source, size: 11.5, lineHeight: 20, lines: 0, monospaced: true, pathWrapping: true).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 238, height: 200)
        let container = try XCTUnwrap(view.textContainer), layout = try XCTUnwrap(view.layoutManager)
        layout.ensureLayout(for: container)
        var lines: [String] = []
        layout.enumerateLineFragments(forGlyphRange: layout.glyphRange(for: container)) { _, _, _, glyphs, _ in
            let chars = layout.characterRange(forGlyphRange: glyphs, actualGlyphRange: nil)
            lines.append((view.string as NSString).substring(with: chars))
        }
        XCTAssertEqual(view.string, source)
        XCTAssertEqual(lines, ["/Users/runner/work/Relic-", "Plugins/Relic-", "Plugins/visual/macos/dat…"])
        XCTAssertEqual(layout.usedRect(for: container).height, 60, accuracy: 0.5)
    }

    func testLongUnbrokenDirectoryStillFitsTheAvailableColumn() throws {
        let source = "/" + String(repeating: "x", count: 70)
        let view = ReferenceLabel(source, size: 11.5, lineHeight: 20, lines: 0, monospaced: true, pathWrapping: true).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 120, height: 200)
        let container = try XCTUnwrap(view.textContainer), layout = try XCTUnwrap(view.layoutManager)
        layout.ensureLayout(for: container)
        XCTAssertEqual(view.string, source)
        XCTAssertGreaterThan(layout.usedRect(for: container).height, 20)
        XCTAssertLessThanOrEqual(layout.usedRect(for: container).width, 120.5)
        XCTAssertEqual(layout.characterRange(forGlyphRange: layout.glyphRange(for: container), actualGlyphRange: nil).length, (source as NSString).length)
        let observed = NativeLineBreaks.inspect(view, range: NSRange(location: 0, length: (source as NSString).length))
        XCTAssertEqual(observed.layout["normal_break_strategy"] as? String, "word")
        XCTAssertEqual(observed.layout["emergency_break_strategy"] as? String, "break-unbreakable")
        XCTAssertEqual((observed.evidence["raw"] as? [String: Any])?["slash_word_break_suppression"] as? Bool, true)
        XCTAssertEqual(observed.evidence["applicable"] as? Bool, true)
        XCTAssertFalse((observed.evidence["owner"] as? String ?? "").isEmpty)
    }

    func testActualWordAndCharacterWrappingChooseDifferentFirstLines() throws {
        var firstLines: [String] = []
        for mode in [NSLineBreakMode.byWordWrapping, .byCharWrapping] {
            let view = ReferenceLabel("ab cd", size: 12, lineHeight: 20, lines: 0, monospaced: true).makeLabelView()
            view.frame = NSRect(x: 0, y: 0, width: 33, height: 100)
            let paragraph = NSMutableParagraphStyle(); paragraph.lineBreakMode = mode
            view.textStorage?.addAttribute(.paragraphStyle, value: paragraph, range: NSRange(location: 0, length: 5))
            let container = try XCTUnwrap(view.textContainer), manager = try XCTUnwrap(view.layoutManager)
            container.lineBreakMode = mode; manager.ensureLayout(for: container)
            var first: NSRange?
            manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { _, _, _, glyphs, stop in
                first = manager.characterRange(forGlyphRange: glyphs, actualGlyphRange: nil); stop.pointee = true
            }
            firstLines.append((view.string as NSString).substring(with: try XCTUnwrap(first)))
            let observed = NativeLineBreaks.inspect(view, range: NSRange(location: 0, length: 5))
            XCTAssertEqual(observed.layout["normal_break_strategy"] as? String, mode == .byWordWrapping ? "word" : "character")
            XCTAssertEqual(observed.layout["emergency_break_strategy"] as? String, mode == .byWordWrapping ? "break-unbreakable" : "none")
        }
        XCTAssertEqual(firstLines, ["ab ", "ab c"], "The actual TextKit line fragments must distinguish the two strategies")
    }
}
