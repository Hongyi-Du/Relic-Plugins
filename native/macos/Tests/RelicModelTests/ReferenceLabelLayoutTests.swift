import XCTest
import AppKit
@testable import Relic

@MainActor final class ReferenceLabelLayoutTests: XCTestCase {
    func testListMarkerKeepsItsTrailingSpaceAndActualGlyphIconEvidence() throws {
        let view = ReferenceLabel("• ", size: 13.5, alignment: .right, textGlyphIcon: true).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 14, height: 21.6)
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        XCTAssertEqual(view.string, "• ")
        let runs = ElementCapture.textRuns(view)
        XCTAssertEqual(runs.count, 1)
        let run = try XCTUnwrap(runs.first)
        XCTAssertEqual(run["text"] as? String, "• ")
        XCTAssertEqual(run["kind"] as? String, "icon")
        let icon = try XCTUnwrap(run["icon"] as? [String: Any])
        XCTAssertEqual(icon["source"] as? String, "text-glyph")
        XCTAssertEqual(icon["glyph"] as? String, view.string)
        let plain = ReferenceLabel("• ", size: 13.5).makeLabelView()
        plain.frame = view.frame
        XCTAssertEqual(ElementCapture.textRuns(plain).first?["kind"] as? String, "text")
    }

    func testHierarchyNoteMatchesActualReferenceLineAdvancesAndSpacing() throws {
        // 2cb073c reference macOS zh-CN/light/1440x900/group, dom-382:text-0.
        // The reference's .hier-note uses 12px text and 1.55 line height.
        // Its measured owner box is 297px: 340px pane - 1px border -
        // 10px actual overflow scrollbar - 32px block padding.
        let source = "全库只有一个秘书处，它的负责人就是秘书长：成员新建或调整正式组织，要秘书长批准；各正式组织的负责人也会自动在秘书处有一个席位。"
        let view = ReferenceLabel(source, size: 12, lineHeight: 18.6, lines: 0).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 297, height: 100)
        let manager = try XCTUnwrap(view.layoutManager), container = try XCTUnwrap(view.textContainer)
        manager.ensureLayout(for: container)
        var fragments: [NSRect] = []
        manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { _, used, _, _, _ in fragments.append(used) }
        XCTAssertEqual(fragments.count, 3)
        for (actual, expected) in zip(fragments, [294.0625, 294.0625, 183.78125]) {
            XCTAssertEqual(actual.width, expected, accuracy: 0.5)
        }
        for pair in zip(fragments, fragments.dropFirst()) {
            XCTAssertEqual(pair.1.minY - pair.0.minY, 18.59375, accuracy: 0.02)
        }
        XCTAssertEqual(view.string, source)
    }

    func testCompletedInspectorTitleDrawsStrikeWithoutChangingItsTextOrAdvance() throws {
        var rasters: [Data] = [], advances: [CGFloat] = []
        for struck in [false, true] {
            let view = ReferenceLabel("Completed task", size: 13, weight: 600, struck: struck).makeLabelView()
            view.frame = NSRect(x: 0, y: 0, width: 180, height: 20.8)
            let manager = try XCTUnwrap(view.layoutManager), container = try XCTUnwrap(view.textContainer)
            manager.ensureLayout(for: container); advances.append(manager.usedRect(for: container).width)
            let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            rasters.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            XCTAssertEqual(view.string, "Completed task")
        }
        XCTAssertEqual(advances[0], advances[1])
        XCTAssertNotEqual(rasters[0], rasters[1], "The real label must draw the completed-state decoration")
    }

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
        let rows = ElementCapture.textRuns(view)
        let layout = try XCTUnwrap(rows.first?["layout"] as? [String: Any])
        XCTAssertEqual(layout["wrap"] as? String, "word", "A measured three-line paragraph keeps word wrapping before its clamped last line")
        XCTAssertEqual(layout["truncation"] as? String, "ellipsis")
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
