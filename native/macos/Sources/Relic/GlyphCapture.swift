import AppKit
import CoreText

/// Observe TextKit's actual drawing primitive, including substituted fonts.
/// Re-shaping attributed text separately cannot prove which glyphs were drawn.
/// These raw receipts do not replace canonical geometry or font measurements.
class NativeGlyphLayoutManager: NSLayoutManager {
    var recordDraws = false
    private var sequence = 0
    private var calls: [[String: Any]] = []
    private var activeRange: NSRange?
    private(set) var lastDraw: [String: Any]?

    override func drawGlyphs(forGlyphRange glyphsToShow: NSRange, at origin: NSPoint) {
        guard recordDraws else { super.drawGlyphs(forGlyphRange: glyphsToShow, at: origin); return }
        sequence += 1; calls = []; activeRange = glyphsToShow
        let characters = characterRange(forGlyphRange: glyphsToShow, actualGlyphRange: nil)
        super.drawGlyphs(forGlyphRange: glyphsToShow, at: origin)
        lastDraw = ["provider": "production NSLayoutManager.showCGGlyphs callback",
            "sequence": sequence, "glyph_range": ["location": glyphsToShow.location, "length": glyphsToShow.length],
            "character_range": ["location": characters.location, "length": characters.length],
            "container_origin": ["x": origin.x, "y": origin.y], "callbacks": calls,
            "text": textStorage?.string as Any? ?? NSNull(), "draw_returned": true]
        activeRange = nil
    }
    override func showCGGlyphs(_ glyphs: UnsafePointer<CGGlyph>, positions: UnsafePointer<CGPoint>, count glyphCount: Int,
                              font: NSFont, textMatrix: CGAffineTransform, attributes: [NSAttributedString.Key: Any] = [:], in context: CGContext) {
        if recordDraws, activeRange != nil {
            func transform(_ t: CGAffineTransform) -> [String: Double] { ["a": t.a, "b": t.b, "c": t.c, "d": t.d, "tx": t.tx, "ty": t.ty] }
            func box(_ rect: CGRect) -> Any { rect.isInfinite || rect.isNull ? NSNull() : ElementCapture.box(rect) }
            var glyphBounds = Array(repeating: CGRect.zero, count: glyphCount)
            _ = CTFontGetBoundingRectsForGlyphs(font as CTFont, .default, glyphs, &glyphBounds, glyphCount)
            let variations = (CTFontCopyVariation(font as CTFont) as? [NSNumber: NSNumber]).map { values in
                Dictionary(uniqueKeysWithValues: values.map { ($0.key.stringValue, $0.value.doubleValue) })
            }
            calls.append(["glyphs": Array(UnsafeBufferPointer(start: glyphs, count: glyphCount)).map(Int.init),
                "positions_user_space": Array(UnsafeBufferPointer(start: positions, count: glyphCount)).map { ["x": $0.x, "y": $0.y] },
                "font_glyph_bounds": glyphBounds.map(box), "text_matrix": transform(textMatrix), "context_ctm": transform(context.ctm),
                "clip_user_space": box(context.boundingBoxOfClipPath),
                "actual_font": ["postscript_name": font.fontName, "family_name": font.familyName as Any? ?? NSNull(), "size": font.pointSize, "variations": variations as Any? ?? NSNull()],
                "attribute_font": (attributes[.font] as? NSFont)?.fontName as Any? ?? NSNull(),
                "foreground": ElementCapture.rgba(attributes[.foregroundColor] as? NSColor),
                "bitmap_width": context.width, "bitmap_height": context.height])
        }
        super.showCGGlyphs(glyphs, positions: positions, count: glyphCount, font: font, textMatrix: textMatrix, attributes: attributes, in: context)
    }
}
