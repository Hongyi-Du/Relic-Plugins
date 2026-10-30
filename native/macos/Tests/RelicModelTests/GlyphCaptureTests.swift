import XCTest
import AppKit
@testable import Relic

@MainActor final class GlyphCaptureTests: XCTestCase {
    func testDirectLabelPrimitivePreservesTextKitsActualGlyphBitmap() throws {
        for (index, text) in ["Relic → 组织", "A long label that must end in an ellipsis", "Done 任务", "🙂 Relic"].enumerated() {
            var images: [Data] = []
            for direct in [false, true] {
                let view = ReferenceLabel(text, size: 14, lines: 1, struck: text.hasPrefix("Done")).makeLabelView()
                let layout = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
                layout.drawsGlyphsIntoCurrentContext = direct
                view.frame = NSRect(x: 0, y: 0, width: 120, height: 30)
                view.textContainer?.containerSize = view.bounds.size
                let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
                view.cacheDisplay(in: view.bounds, to: bitmap)
                images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            }
            if images[0] != images[1] {
                // Retain the actual failed CI renders, never synthetic expected
                // pixels, so the next correction can inspect the exact defect.
                let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try images[0].write(to: directory.appendingPathComponent("glyph-\(index)-appkit.png"))
                try images[1].write(to: directory.appendingPathComponent("glyph-\(index)-direct.png"))
                try text.write(to: directory.appendingPathComponent("glyph-\(index)-source.txt"), atomically: true, encoding: .utf8)
            }
            XCTAssertEqual(images[0], images[1], "The drawing primitive must preserve shaping, truncation, fallback and decorations: \(text)")
        }
    }

    func testActualDrawSeparatesFontExtentFromCodeParagraphLeading() throws {
        let view = ReferenceLabel("review('Windows')\nreview('macOS')", size: 11.25, lineHeight: 19.375, lines: 0, monospaced: true).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 180, height: 60)
        let manager = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
        manager.recordDraws = true
        let container = try XCTUnwrap(view.textContainer)
        manager.ensureLayout(for: container)
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let before = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        let range = NSRange(location: 0, length: (view.string as NSString).length)
        let advances = NativeTextGeometry.advances(manager, container: container, characters: range)
        let draw = try XCTUnwrap(manager.lastDraw)
        let measured = NativeTypographicGeometry.measure(advances: advances, draw: draw, characters: range, origin: view.textContainerOrigin)
        XCTAssertTrue(measured.complete, String(describing: measured.lines))
        XCTAssertEqual(measured.rectangles.count, 2)
        let first = try XCTUnwrap(measured.rectangles.first)
        let envelope = try XCTUnwrap(measured.envelope)
        XCTAssertEqual(first.height, 13.095703125, accuracy: 0.001)
        XCTAssertEqual(envelope.height, 32.470703125, accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(advances.envelope).height, 38.75, accuracy: 0.001,
            "Original TextKit line boxes remain available and include the paragraph leading")
        XCTAssertEqual(first.width, try XCTUnwrap(advances.rectangles.first).width)
        let exported = try XCTUnwrap(ElementCapture.textRuns(view).first)
        XCTAssertEqual(exported["text_bounds_quantity"] as? String, "native-insertion-advance-and-actual-font-typographic-extent")
        let after = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: after)
        XCTAssertEqual(before, after.representation(using: .png, properties: [:]), "Measurement does not alter the actual draw")
        view.textStorage?.addAttribute(.foregroundColor, value: NSColor.red, range: range)
        XCTAssertNotEqual(ElementCapture.textRuns(view).first?["text_bounds_quantity"] as? String,
            "native-insertion-advance-and-actual-font-typographic-extent", "Stale draw receipts cannot replace current geometry")
    }

    func testTypographicMeasurementRejectsMissingDrawAndUnboundBaseline() {
        var advances = NativeTextGeometry.Measurement()
        advances.rectangles = [NSRect(x: 0, y: 0, width: 20, height: 22)]
        advances.lines = [["fragment": ElementCapture.box(advances.rectangles[0])]]
        let range = NSRange(location: 0, length: 2)
        XCTAssertFalse(NativeTypographicGeometry.measure(advances: advances, draw: [:], characters: range, origin: .zero).complete)
        let draw: [String: Any] = ["draw_returned": true, "callbacks": [[
            "source_character_range": ["location": 0, "length": 2],
            "actual_font": ["ascent": 10.0, "descent": 3.0],
            "text_matrix": ["a": 1.0, "b": 0.0, "c": 0.0, "d": -1.0],
            "context_ctm": ["a": 1.0, "b": 0.0, "c": 0.0, "d": -1.0],
            "positions_user_space": [["x": 0.0, "y": 40.0]]
        ]]]
        XCTAssertFalse(NativeTypographicGeometry.measure(advances: advances, draw: draw, characters: range, origin: .zero).complete)
    }

    func testActualAttributeDrawsBindRichSpansWithoutChangingTheRenderedBitmap() throws {
        let source = NativeTextStyle.render(try AttributedString(markdown: "Before **bold 组织** after →"), size: 14)
        let bold = (source.string as NSString).range(of: "bold 组织")
        var bitmaps: [Data] = []
        for mode in 0..<3 {
            let manager = mode == 0 ? UnpartitionedGlyphManager() : NativeGlyphLayoutManager()
            manager.recordDraws = mode == 1
            let storage = NSTextStorage(attributedString: source)
            let container = NSTextContainer(containerSize: NSSize(width: 300, height: 80))
            container.lineFragmentPadding = 0; storage.addLayoutManager(manager); manager.addTextContainer(container)
            let view = NSTextView(frame: NSRect(x: 0, y: 0, width: 300, height: 80), textContainer: container)
            view.textContainerInset = .zero; view.isEditable = false; view.drawsBackground = false
            manager.ensureLayout(for: container)
            let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            bitmaps.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            if mode == 1 {
                let actual = manager.fontEvidence(for: bold, in: view)
                XCTAssertEqual(actual["status"] as? String, "measured-current-draw")
                let fonts = try XCTUnwrap(actual["fonts"] as? [[String: Any]])
                XCTAssertFalse(fonts.isEmpty)
                XCTAssertTrue(fonts.allSatisfy { $0["postscript_name"] as? String == "PingFangSC-Semibold" })
                XCTAssertEqual(actual["source_draw_spans"] as? [[String: Int]], [["location": bold.location, "length": bold.length]])
                XCTAssertTrue(manager.fontEvidence(for: NSRange(location: bold.location + 1, length: 2), in: view)["fonts"] is NSNull,
                              "An arbitrary substring still has no independent actual draw invocation")
            }
        }
        XCTAssertEqual(bitmaps[0], bitmaps[1], "Partitioning actual TextKit paint must not alter the glyph pixels")
        XCTAssertEqual(bitmaps[1], bitmaps[2], "Capture observation must use the same production drawing")
    }
    func testOnlyTheCurrentActualDrawSuppliesACompleteLabelsFonts() throws {
        let view = ReferenceLabel("Relic → 组织", size: 14, lines: 0).makeLabelView()
        let layout = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
        layout.recordDraws = true
        view.frame = NSRect(x: 0, y: 0, width: 240, height: 60)
        view.textContainer?.containerSize = view.bounds.size
        let full = NSRange(location: 0, length: (view.string as NSString).length)
        func draw() throws {
            view.layoutManager?.ensureLayout(for: try XCTUnwrap(view.textContainer))
            view.cacheDisplay(in: view.bounds, to: try XCTUnwrap(CaptureRaster.forView(view)))
        }
        XCTAssertTrue(layout.fontEvidence(for: full, in: view)["fonts"] is NSNull,
                      "Source attributes and layout alone do not prove the font actually drawn")
        try draw()
        let actual = layout.fontEvidence(for: full, in: view)
        XCTAssertEqual(actual["status"] as? String, "measured-current-draw")
        XCTAssertFalse(try XCTUnwrap(actual["fonts"] as? [[String: Any]]).isEmpty)
        XCTAssertTrue(layout.fontEvidence(for: NSRange(location: 0, length: 5), in: view)["fonts"] is NSNull,
                      "A callback without source indices cannot be assigned to a partial rich-text span")
        view.setFrameSize(NSSize(width: 180, height: 60))
        XCTAssertTrue(layout.fontEvidence(for: full, in: view)["fonts"] is NSNull,
                      "Old glyph callbacks cannot survive a change in native text layout")
        try draw()
        XCTAssertEqual(layout.fontEvidence(for: full, in: view)["status"] as? String, "measured-current-draw")
        view.textStorage?.addAttribute(.foregroundColor, value: NSColor.red, range: full)
        XCTAssertTrue(layout.fontEvidence(for: full, in: view)["fonts"] is NSNull,
                      "Even same-length source changes invalidate the previous draw binding")
    }

    func testActualProductionTextPaintDoesNotDependOnAmbientFontSmoothing() throws {
        let storage = NSTextStorage(attributedString: ReferenceLabel("Relic 组织 11:00", size: 14).attributedText)
        let layout = NativeGlyphLayoutManager(), container = NSTextContainer(containerSize: CGSize(width: 220, height: 50))
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        layout.ensureLayout(for: container)
        let glyphs = layout.glyphRange(for: container)
        var images: [Data] = []
        for inheritedSmoothing in [false, true] {
            let bitmap = try XCTUnwrap(CaptureRaster.composite(width: 240, height: 60) { canvas in
                NSColor.white.setFill(); canvas.fill()
                let context = NSGraphicsContext.current!.cgContext
                context.setShouldSmoothFonts(inheritedSmoothing)
                layout.drawGlyphs(forGlyphRange: glyphs, at: NSPoint(x: 8, y: 8))
            })
            images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
        }
        XCTAssertEqual(images[0], images[1], "The actual label bitmap must use the app's explicit antialiased mode in either incoming context")
    }

    func testEvidenceComesFromAnActualTextKitBitmapDraw() throws {
        let storage = NSTextStorage(attributedString: ReferenceLabel("Actual 绘制", size: 14).attributedText)
        let layout = NativeGlyphLayoutManager(), container = NSTextContainer(containerSize: CGSize(width: 220, height: 100))
        layout.recordDraws = true; container.lineFragmentPadding = 0
        storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        XCTAssertNil(layout.lastDraw, "Measuring or shaping is not a drawing receipt")
        let bitmap = try XCTUnwrap(NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 240, pixelsHigh: 120, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 960, bitsPerPixel: 32))
        let context = try XCTUnwrap(NSGraphicsContext(bitmapImageRep: bitmap))
        NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = context
        defer { NSGraphicsContext.restoreGraphicsState() }
        NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 240, height: 120).fill()
        layout.drawGlyphs(forGlyphRange: layout.glyphRange(for: container), at: NSPoint(x: 8, y: 8))
        let receipt = try XCTUnwrap(layout.lastDraw)
        XCTAssertEqual(receipt["draw_returned"] as? Bool, true)
        let calls = try XCTUnwrap(receipt["callbacks"] as? [[String: Any]])
        XCTAssertFalse(calls.isEmpty)
        for call in calls {
            let glyphs = try XCTUnwrap(call["glyphs"] as? [Int])
            XCTAssertFalse(glyphs.isEmpty)
            XCTAssertEqual((call["positions_user_space"] as? [[String: CGFloat]])?.count, glyphs.count)
            XCTAssertNotNil(call["context_ctm"])
            XCTAssertFalse(((call["actual_font"] as? [String: Any])?["postscript_name"] as? String ?? "").isEmpty)
        }
        var darkPixels = 0
        for y in 0..<120 { for x in 0..<240 {
            if let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB), color.redComponent < 0.5 { darkPixels += 1 }
        } }
        XCTAssertGreaterThan(darkPixels, 20, "The observed draw must paint text into the actual bitmap")
    }
}

private final class UnpartitionedGlyphManager: NativeGlyphLayoutManager {
    override func glyphPaintRanges(_ requested: NSRange) -> [NSRange] { [requested] }
}
