import AppKit
import SwiftUI

extension NSAttributedString.Key {
    static let relicCodeGroup = NSAttributedString.Key("RelicInlineCodeGroup")
    static let relicCodePadding = NSAttributedString.Key("RelicInlineCodePadding")
}

enum NativeInlineCode {
    static func decorate(_ value: NSMutableAttributedString, ranges: [NSRange]) {
        for range in ranges.reversed() {
            let attributes = value.attributes(at: range.location, effectiveRange: nil)
            func padding() -> NSAttributedString {
                let attachment = NSTextAttachment()
                attachment.attachmentCell = NSTextAttachmentCell(imageCell: NSImage(size: NSSize(width: 5, height: 1)))
                let spacer = NSMutableAttributedString(attachment: attachment)
                spacer.addAttributes(attributes, range: NSRange(location: 0, length: 1))
                spacer.addAttribute(.relicCodePadding, value: true, range: NSRange(location: 0, length: 1))
                spacer.removeAttribute(.link, range: NSRange(location: 0, length: 1))
                return spacer
            }
            value.insert(padding(), at: NSMaxRange(range)); value.insert(padding(), at: range.location)
            value.addAttribute(.relicCodeGroup, value: "code-\(range.location)", range: NSRange(location: range.location, length: range.length + 2))
        }
    }
    static func source(_ value: NSAttributedString) -> String {
        let result = NSMutableAttributedString(attributedString: value)
        value.enumerateAttribute(.relicCodePadding, in: NSRange(location: 0, length: value.length), options: .reverse) { marker, range, _ in
            if marker as? Bool == true { result.deleteCharacters(in: range) }
        }
        return result.string
    }
}

// Padding participates in the actual TextKit line layout. The code background
// uses those very same glyph positions; selection/copy preserves source text.
final class InlineCodeLayoutManager: NativeGlyphLayoutManager {
    struct Fragment {
        let group: String
        let range: NSRange
        let rect: NSRect
    }
    var fill: NSColor { NSColor(RelicStyle.ink).withAlphaComponent(0.07) }
    func codeFragments(in container: NSTextContainer) -> [Fragment] {
        guard let textStorage else { return [] }
        ensureLayout(for: container)
        var fragments: [Fragment] = []
        textStorage.enumerateAttribute(.relicCodeGroup, in: NSRange(location: 0, length: textStorage.length), options: []) { value, range, _ in
            guard let group = value as? String, let font = textStorage.attribute(.font, at: range.location, effectiveRange: nil) as? NSFont else { return }
            let glyphs = self.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
            self.enumerateLineFragments(forGlyphRange: glyphs) { line, _, actualContainer, lineGlyphs, _ in
                guard actualContainer === container else { return }
                let part = NSIntersectionRange(glyphs, lineGlyphs)
                guard part.length > 0 else { return }
                let box = self.boundingRect(forGlyphRange: part, in: container)
                let baseline = line.minY + self.location(forGlyphAt: part.location).y
                let height = font.ascender - font.descender
                fragments.append(Fragment(group: group, range: range, rect: NSRect(x: box.minX, y: baseline - font.ascender - 1, width: box.width, height: height + 2)))
            }
        }
        return fragments
    }
    override func drawBackground(forGlyphRange glyphsToShow: NSRange, at origin: NSPoint) {
        if glyphsToShow.length > 0, let container = textContainer(forGlyphAt: glyphsToShow.location, effectiveRange: nil) {
            fill.setFill()
            for fragment in codeFragments(in: container) {
                let glyphs = glyphRange(forCharacterRange: fragment.range, actualCharacterRange: nil)
                if NSIntersectionRange(glyphs, glyphsToShow).length > 0 {
                    NSBezierPath(roundedRect: fragment.rect.offsetBy(dx: origin.x, dy: origin.y), xRadius: 5, yRadius: 5).fill()
                }
            }
        }
        super.drawBackground(forGlyphRange: glyphsToShow, at: origin)
    }
}
