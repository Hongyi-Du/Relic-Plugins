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
    }
}
