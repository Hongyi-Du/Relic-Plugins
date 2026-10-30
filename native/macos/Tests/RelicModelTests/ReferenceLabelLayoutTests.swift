import XCTest
import AppKit
@testable import Relic

@MainActor final class ReferenceLabelLayoutTests: XCTestCase {
    func testSidebarMixedScriptAdvancesMatchActualReferenceText() throws {
        // Actual DOMRange from 3c652b7 macOS zh-CN/light/group. This checks the
        // production text layout separately from its ink envelope; those are
        // different quantities and cannot be exchanged in element extraction.
        let view = ReferenceLabel("在做：Read layout.png", size: 12, lineHeight: 16.2).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 200, height: 16.2)
        let manager = try XCTUnwrap(view.layoutManager), container = try XCTUnwrap(view.textContainer)
        manager.ensureLayout(for: container)
        let advance = manager.usedRect(for: container).width
        let envelope = manager.boundingRect(forGlyphRange: manager.glyphRange(for: container), in: container)
        print("SIDEBAR MIXED advance=\(advance) envelope=\(envelope)")
        XCTAssertEqual(advance, 130.640625, accuracy: 0.5)
        let measured = NativeTextGeometry.advances(manager, container: container, characters: NSRange(location: 0, length: (view.string as NSString).length))
        XCTAssertEqual(try XCTUnwrap(measured.envelope).width, 130.640625, accuracy: 0.5)
        XCTAssertNotEqual(try XCTUnwrap(measured.envelope).width, envelope.width, "Ink envelope must not be substituted for text advance")
    }

    func testPurposeWrappingUsesTheActualBorderBoxContentWidth() throws {
        // Independent DOMSnapshot text fragments, f7b6bf0 reference macOS,
        // zh-CN/light/1440x900/group. A 340px panel has a 1px border and 32px
        // section padding, leaving 307px. No production code reads this data.
        let source = "为 Hongyi Du 统筹 Codex 与 Claude Code 的日常协作，跟进任务、整理决策，并保留可核查的交付记录。"
        let view = ReferenceLabel(source, size: 12.5, lineHeight: 20, lines: 3).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 307, height: 60)
        let manager = try XCTUnwrap(view.layoutManager), container = try XCTUnwrap(view.textContainer)
        manager.ensureLayout(for: container)
        var ranges: [NSRange] = [], widths: [CGFloat] = []
        manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { _, used, _, glyphs, _ in
            ranges.append(manager.characterRange(forGlyphRange: glyphs, actualGlyphRange: nil)); widths.append(used.width)
        }
        print("PURPOSE LINES ranges=\(ranges) widths=\(widths) frame=\(view.frame)")
        XCTAssertEqual(ranges, [NSRange(location: 0, length: 38), NSRange(location: 38, length: 23), NSRange(location: 61, length: 2)])
        for (actual, reference) in zip(widths, [294.671875, 293.40625, 25.515625]) { XCTAssertEqual(actual, reference, accuracy: 0.5) }
        let measured = NativeTextGeometry.advances(manager, container: container, characters: NSRange(location: 0, length: (source as NSString).length))
        XCTAssertTrue(measured.complete)
        XCTAssertEqual(measured.rectangles.count, 3)
        XCTAssertEqual(view.frame, NSRect(x: 0, y: 0, width: 307, height: 60))
    }

    func testTextInspectionCannotResizeAnAssignedLabelFrame() throws {
        let view = ReferenceLabel("A long wrapping label with enough words to span multiple lines.", size: 12.5, lines: 0).makeLabelView()
        for width in [CGFloat(90), 240, 130] {
            let assigned = NSRect(x: 16, y: 29, width: width, height: 120)
            view.frame = assigned
            let runs = ElementCapture.textRuns(view)
            XCTAssertFalse(runs.isEmpty)
            XCTAssertEqual(view.frame, assigned, "Reading actual text evidence must leave the rendered frame unchanged")
        }
    }
}
