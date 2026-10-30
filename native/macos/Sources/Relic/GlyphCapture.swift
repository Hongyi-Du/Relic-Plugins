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
    private weak var drawnView: NSTextView?
    private weak var drawnContainer: NSTextContainer?
    private var drawnSource: NSAttributedString?
    private var drawnCharacters = NSRange(location: NSNotFound, length: 0)
    private var drawnBounds = NSRect.zero, drawnFrame = NSRect.zero
    private var drawnContainerSize = NSSize.zero, drawnOrigin = NSPoint.zero
    private var drawnWindowIdentity: ObjectIdentifier?
    private var drawnLineLimit = 0
    private var drawnLineBreak = NSLineBreakMode.byWordWrapping

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
        drawnView = nil; drawnContainer = nil; drawnSource = nil
        if textContainers.count == 1, let container = textContainers.first, let view = container.textView, let storage = textStorage {
            drawnView = view; drawnContainer = container
            drawnSource = NSAttributedString(attributedString: storage)
            drawnCharacters = characters; drawnBounds = view.bounds; drawnFrame = view.frame
            drawnContainerSize = container.containerSize; drawnOrigin = view.textContainerOrigin
            drawnWindowIdentity = view.window.map(ObjectIdentifier.init)
            drawnLineLimit = container.maximumNumberOfLines; drawnLineBreak = container.lineBreakMode
            lastDraw?["binding"] = ["view_identity": String(describing: ObjectIdentifier(view)),
                "container_identity": String(describing: ObjectIdentifier(container)),
                "window_identity": drawnWindowIdentity.map { String(describing: $0) } as Any? ?? NSNull()]
        }
        activeRange = nil
    }

    /// Project only callbacks belonging to this exact, still-current text view.
    /// showCGGlyphs does not expose a source range for each fallback callback:
    /// a partial attributed span must remain unknown rather than borrowing all
    /// fonts from its parent or re-shaping its text to guess the actual paint.
    func fontEvidence(for range: NSRange, in view: NSTextView) -> [String: Any] {
        var evidence: [String: Any] = ["provider": "production NSLayoutManager.showCGGlyphs callback",
            "draw_sequence": sequence, "final_png_attribution_proven": false,
            "requested_range": ["location": range.location, "length": range.length]]
        func unknown(_ reason: String) -> [String: Any] {
            evidence["status"] = "unmeasured"; evidence["reason"] = reason; evidence["fonts"] = NSNull()
            return evidence
        }
        guard lastDraw != nil, !calls.isEmpty else { return unknown("No completed actual glyph draw") }
        guard drawnView === view, let container = view.textContainer, drawnContainer === container,
              view.layoutManager === self else { return unknown("Actual draw belongs to a different native text view or container") }
        guard drawnWindowIdentity == view.window.map(ObjectIdentifier.init), drawnBounds == view.bounds,
              drawnFrame == view.frame, drawnContainerSize == container.containerSize, drawnOrigin == view.textContainerOrigin,
              drawnLineLimit == container.maximumNumberOfLines, drawnLineBreak == container.lineBreakMode else {
            return unknown("Native draw binding changed since the actual glyph callback")
        }
        guard let storage = view.textStorage, let source = drawnSource, source.isEqual(to: storage) else {
            return unknown("Attributed text changed since the actual glyph callback")
        }
        guard range == drawnCharacters else { return unknown("Callback-to-partial-source-span ownership is unmeasured") }
        let fonts: [[String: Any]] = calls.compactMap { call in
            guard var font = call["actual_font"] as? [String: Any], let glyphs = call["glyphs"] as? [Int] else { return nil }
            font["glyph_count"] = glyphs.count; font["provider"] = "production NSLayoutManager.showCGGlyphs callback"
            return font
        }
        guard fonts.count == calls.count else { return unknown("An actual glyph callback lacks its font identity") }
        evidence["status"] = "measured-current-draw"; evidence["fonts"] = fonts
        evidence["binding"] = lastDraw?["binding"] ?? NSNull()
        return evidence
    }
    override func showCGGlyphs(_ glyphs: UnsafePointer<CGGlyph>, positions: UnsafePointer<CGPoint>, count glyphCount: Int,
                              font: NSFont, textMatrix: CGAffineTransform, attributes: [NSAttributedString.Key: Any] = [:], in context: CGContext) {
        NativeTextRasterization.begin(context)
        defer { context.restoreGState() }
        if recordDraws, activeRange != nil {
            func transform(_ t: CGAffineTransform) -> [String: Double] { ["a": t.a, "b": t.b, "c": t.c, "d": t.d, "tx": t.tx, "ty": t.ty] }
            func box(_ rect: CGRect) -> Any {
                rect.isInfinite || rect.isNull ? NSNull() : ["x": Double(rect.minX), "y": Double(rect.minY), "width": Double(rect.width), "height": Double(rect.height)]
            }
            let foreground: Any
            if let color = (attributes[.foregroundColor] as? NSColor)?.usingColorSpace(.sRGB) {
                foreground = [color.redComponent, color.greenComponent, color.blueComponent, color.alphaComponent].map { Double($0 * 255) }
            } else { foreground = NSNull() }
            var glyphBounds = Array(repeating: CGRect.zero, count: glyphCount)
            _ = CTFontGetBoundingRectsForGlyphs(font as CTFont, .default, glyphs, &glyphBounds, glyphCount)
            let variations = (CTFontCopyVariation(font as CTFont) as? [NSNumber: NSNumber]).map { values in
                Dictionary(uniqueKeysWithValues: values.map { ($0.key.stringValue, $0.value.doubleValue) })
            }
            calls.append(["glyphs": Array(UnsafeBufferPointer(start: glyphs, count: glyphCount)).map(Int.init),
                "positions_user_space": Array(UnsafeBufferPointer(start: positions, count: glyphCount)).map { ["x": $0.x, "y": $0.y] },
                "font_glyph_bounds": glyphBounds.map(box), "text_matrix": transform(textMatrix), "context_ctm": transform(context.ctm),
                "clip_user_space": box(context.boundingBoxOfClipPath),
                "actual_font": ["postscript_name": font.fontName, "family_name": font.familyName as Any? ?? NSNull(), "size": font.pointSize,
                    "variations": variations as Any? ?? NSNull(), "actual_variations": variations as Any? ?? NSNull(),
                    "optical_size_attribute": CTFontCopyAttribute(font as CTFont, kCTFontOpticalSizeAttribute).map { String(describing: $0) } as Any? ?? NSNull(),
                    "ascent": CTFontGetAscent(font as CTFont), "descent": CTFontGetDescent(font as CTFont), "leading": CTFontGetLeading(font as CTFont)],
                "attribute_font": (attributes[.font] as? NSFont)?.fontName as Any? ?? NSNull(),
                "foreground": foreground, "rasterization_inputs": NativeTextRasterization.inputs,
                "bitmap_width": context.width, "bitmap_height": context.height])
        }
        super.showCGGlyphs(glyphs, positions: positions, count: glyphCount, font: font, textMatrix: textMatrix, attributes: attributes, in: context)
    }
}
