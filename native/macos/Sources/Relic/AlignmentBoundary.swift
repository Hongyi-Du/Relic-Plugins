import SwiftUI

/// A transparent container for one large region of the window. It sizes and
/// places its view exactly as the parent would, but answers that the region
/// has no alignment guides of its own.
///
/// Without it, an overlay or a stack that aligns the region (a dialog over the
/// window, the inspector beside the chat, a loading cover) asks SwiftUI for the
/// region's center, leading or trailing guide, and SwiftUI answers by merging
/// every descendant's guides: it measures the whole subtree again, scroll
/// content and lazy rows included, inside the transaction that shows the
/// overlay. No view in these regions defines an explicit guide, so the merged
/// answer was always the default one the region now gives directly.
struct AlignmentBoundary: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        subviews.first?.sizeThatFits(proposal) ?? .zero
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, anchor: .topLeading, proposal: proposal)
    }
    func explicitAlignment(of guide: HorizontalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
    func explicitAlignment(of guide: VerticalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
}

/// A scroll region that takes the space its stack offers. SwiftUI sizes a
/// ScrollView by measuring its content, so whenever the stack around it probes
/// how far each child can shrink and grow (a chat switch, every row the
/// sidebar admits), the scroll view measured all its lazy rows again. With a
/// definite offer it answers that offer, which is the size the scroll view
/// takes; only an unspecified offer still asks the scroll view itself.
struct ScrollRegion: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        if let width = proposal.width, let height = proposal.height { return CGSize(width: width, height: height) }
        return subviews.first?.sizeThatFits(proposal) ?? .zero
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, anchor: .topLeading, proposal: ProposedViewSize(bounds.size))
    }
    func explicitAlignment(of guide: HorizontalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
    func explicitAlignment(of guide: VerticalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
}
