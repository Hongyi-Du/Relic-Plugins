import AppKit

/// Keep fixed-height line leading on both sides of the actual font. Calculate
/// the attributed baseline before TextKit starts shaping, rather than querying
/// glyph/character layout recursively from its line-fragment delegate.
enum NativeLineMetrics {
    private static let heights: NSCache<NSFont, NSNumber> = {
        let cache = NSCache<NSFont, NSNumber>(); cache.countLimit = 256; return cache
    }()
    static func baselineOffset(font: NSFont, lineHeight: CGFloat) -> CGFloat {
        let height: CGFloat
        if let cached = heights.object(forKey: font) { height = CGFloat(cached.doubleValue) }
        else {
            height = NSLayoutManager().defaultLineHeight(for: font)
            heights.setObject(NSNumber(value: Double(height)), forKey: font)
        }
        return max(0, lineHeight - height) / 2
    }
}
