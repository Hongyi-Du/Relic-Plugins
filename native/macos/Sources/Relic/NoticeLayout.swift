import SwiftUI

// The event pill wraps at 86% of the actual stream width, as in app.css.
struct NoticeLayout: Layout {
    // No subview defines an explicit alignment guide. Without these, SwiftUI's
    // default merges the subviews' guides, measuring every subview again each
    // time a parent stack asks this view for its leading or center guide.
    func explicitAlignment(of guide: HorizontalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
    func explicitAlignment(of guide: VerticalAlignment, in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGFloat? { nil }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard let child = subviews.first else { return .zero }
        let width = proposal.width ?? child.sizeThatFits(.unspecified).width
        let size = child.sizeThatFits(ProposedViewSize(width: width * 0.86, height: nil))
        return CGSize(width: width, height: size.height)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let child = subviews.first else { return }
        let offered = ProposedViewSize(width: bounds.width * 0.86, height: nil)
        let size = child.sizeThatFits(offered)
        child.place(at: CGPoint(x: bounds.midX - size.width / 2, y: bounds.minY), proposal: offered)
    }
}
