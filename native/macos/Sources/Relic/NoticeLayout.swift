import SwiftUI

// The event pill wraps at 86% of the actual stream width, as in app.css.
struct NoticeLayout: Layout {
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
