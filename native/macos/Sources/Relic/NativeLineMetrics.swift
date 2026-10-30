import AppKit

/// Fixed-height reference lines distribute their extra leading above and below
/// the font. TextKit puts that extra space above the baseline by default. Adjust
/// the production typesetter's baseline, preserving its glyphs and line boxes.
class NativeLineMetrics: NSObject, NSLayoutManagerDelegate {
    func layoutManager(_ layoutManager: NSLayoutManager,
                       shouldSetLineFragmentRect lineFragmentRect: UnsafeMutablePointer<NSRect>,
                       lineFragmentUsedRect: UnsafeMutablePointer<NSRect>,
                       baselineOffset: UnsafeMutablePointer<CGFloat>,
                       in textContainer: NSTextContainer, forGlyphRange glyphRange: NSRange) -> Bool {
        guard let storage = layoutManager.textStorage, glyphRange.length > 0 else { return false }
        let range = layoutManager.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil)
        guard range.length > 0, NSMaxRange(range) <= storage.length else { return false }
        var naturalHeight: CGFloat = 0
        storage.enumerateAttribute(.font, in: range) { value, _, _ in
            if let font = value as? NSFont { naturalHeight = max(naturalHeight, layoutManager.defaultLineHeight(for: font)) }
        }
        guard naturalHeight > 0 else { return false }
        let leading = max(0, lineFragmentRect.pointee.height - naturalHeight)
        guard leading > 0 else { return false }
        baselineOffset.pointee -= leading / 2
        return true
    }
}
