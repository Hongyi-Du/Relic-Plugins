import AppKit

/// Keep fixed-height line leading on both sides of the actual font. Calculate
/// the attributed baseline before TextKit starts shaping, rather than querying
/// glyph/character layout recursively from its line-fragment delegate.
enum NativeLineMetrics {
    static func baselineOffset(font: NSFont, lineHeight: CGFloat) -> CGFloat {
        max(0, lineHeight - NSLayoutManager().defaultLineHeight(for: font)) / 2
    }
}
