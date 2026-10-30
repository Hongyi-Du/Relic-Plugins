import AppKit
import CoreText
import SwiftUI

/// The banner's two flex items both shrink in proportion to their natural
/// width. Its text minimum comes from native line-break tokens of the same
/// attributed string that is displayed, never from a scene's reference data.
enum BannerTextMetrics {
    struct Widths { let natural: CGFloat; let minimum: CGFloat }
    static func measure(_ value: NSAttributedString) -> Widths {
        guard value.length > 0 else { return Widths(natural: 0, minimum: 0) }
        let source = value.string as NSString
        func width(_ range: NSRange) -> CGFloat {
            var end = NSMaxRange(range)
            // CSS normal white-space collapses these separators, but not NBSP.
            while end > range.location && [0x20, 0x09, 0x0a, 0x0d].contains(Int(source.character(at: end - 1))) { end -= 1 }
            guard end > range.location else { return 0 }
            return CGFloat(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(
                value.attributedSubstring(from: NSRange(location: range.location, length: end - range.location))), nil, nil, nil))
        }
        var natural: CGFloat = 0
        source.enumerateSubstrings(in: NSRange(location: 0, length: source.length), options: [.byParagraphs, .substringNotRequired]) { _, range, _, _ in
            natural = max(natural, width(range))
        }
        let tokenizer = CFStringTokenizerCreate(kCFAllocatorDefault, value.string as CFString,
            CFRange(location: 0, length: value.length), kCFStringTokenizerUnitLineBreak, nil)
        var minimum: CGFloat = 0
        while CFStringTokenizerAdvanceToNextToken(tokenizer).rawValue != 0 {
            let token = CFStringTokenizerGetCurrentTokenRange(tokenizer)
            minimum = max(minimum, width(NSRange(location: token.location, length: token.length)))
        }
        return Widths(natural: natural, minimum: min(natural, minimum))
    }
}

struct BannerFlexLayout: Layout {
    let textWidths: BannerTextMetrics.Widths
    var iconWidth: CGFloat = 15
    var iconHeight: CGFloat = 15
    var gap: CGFloat = 8
    struct Allocation { let icon: CGFloat; let text: CGFloat }
    static func allocate(available: CGFloat, gap: CGFloat, icon: CGFloat, text: BannerTextMetrics.Widths) -> Allocation {
        let content = max(0, available - gap), total = icon + text.natural
        guard total > 0, content < total else { return Allocation(icon: icon, text: text.natural) }
        let scaledText = content * text.natural / total
        if scaledText < text.minimum { return Allocation(icon: max(0, content - text.minimum), text: text.minimum) }
        return Allocation(icon: content * icon / total, text: scaledText)
    }
    private func allocation(_ width: CGFloat) -> Allocation {
        Self.allocate(available: width, gap: gap, icon: iconWidth, text: textWidths)
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? iconWidth + gap + textWidths.natural
        let value = allocation(width)
        let text = subviews[1].sizeThatFits(ProposedViewSize(width: value.text, height: nil))
        return CGSize(width: width, height: max(iconHeight, text.height))
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let value = allocation(bounds.width)
        subviews[0].place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(width: value.icon, height: iconHeight))
        subviews[1].place(at: CGPoint(x: bounds.minX + value.icon + gap, y: bounds.minY), anchor: .topLeading,
            proposal: ProposedViewSize(width: value.text, height: nil))
    }
}
