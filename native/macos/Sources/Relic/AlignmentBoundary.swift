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
