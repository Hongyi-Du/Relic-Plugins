import AppKit
import CoreText

/// Resolve the first organization's real font fallback and glyphs on one
/// background executor before the panes appear. CoreText's cold font/raster
/// initialization otherwise happens inside the first native label display.
actor NativeTextPreparation {
    static let shared = NativeTextPreparation()
    struct Result: Sendable { let styles: Int, glyphs: Int, mainThread: Bool }
    func prepare(_ text: String) -> Result {
        let trace = UIWorkTrace.begin("font.prepare"); defer { UIWorkTrace.end(trace) }
        return autoreleasepool {
            guard !text.isEmpty, let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let bitmap = CGContext(data: nil, width: 4096, height: 48, bitsPerComponent: 8,
                    bytesPerRow: 0, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
                return Result(styles: 0, glyphs: 0, mainThread: Thread.isMainThread)
            }
            let styles: [(CGFloat, Int)] = [(10, 400), (11.5, 400), (12, 400), (12, 650),
                (12.5, 400), (12.5, 600), (13, 400), (13.3, 600), (13.44, 600),
                (14, 400), (15, 400), (15, 650), (16, 700)]
            var glyphs = 0
            for (size, weight) in styles {
                let font = RelicStyle.nativeFont(size, weight: weight)
                _ = NativeLineMetrics.baselineOffset(font: font, lineHeight: size * 1.6)
                let value = NSAttributedString(string: text, attributes: [.font: font,
                    .foregroundColor: NSColor.black])
                let line = CTLineCreateWithAttributedString(value)
                bitmap.textPosition = CGPoint(x: 0, y: 12)
                CTLineDraw(line, bitmap)
                glyphs += CTLineGetGlyphCount(line)
            }
            return Result(styles: styles.count, glyphs: glyphs, mainThread: Thread.isMainThread)
        }
    }
}
