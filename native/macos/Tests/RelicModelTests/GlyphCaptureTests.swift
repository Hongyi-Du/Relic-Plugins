import XCTest
import AppKit
@testable import Relic

@MainActor final class GlyphCaptureTests: XCTestCase {
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
