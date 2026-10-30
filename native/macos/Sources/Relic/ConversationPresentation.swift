import Foundation
import SwiftUI
import RelicCore

struct ConversationRow: Identifiable {
    let id: String
    let item: Node
    let separator: String?
    let continued: Bool
}

/// Keep the author's avatar first in the native hierarchy, including outgoing
/// messages. Like the reference grid, visual column placement is independent
/// from that reading order; text keeps its ordinary left-to-right environment.
struct MessageColumns: Layout {
    var mine = false
    private func measurements(_ proposal: ProposedViewSize, _ subviews: Subviews) -> (width: CGFloat, avatar: CGSize, body: CGSize, bodyWidth: CGFloat) {
        let avatar = subviews[0].sizeThatFits(.unspecified)
        let available = proposal.width.flatMap { $0.isFinite ? max(0, $0) : nil }
        let bodyWidth = min(720, available.map { max(0, $0 - avatar.width - 10) } ?? subviews[1].sizeThatFits(.unspecified).width)
        let body = subviews[1].sizeThatFits(ProposedViewSize(width: bodyWidth, height: nil))
        return (available ?? avatar.width + 10 + bodyWidth, avatar, body, bodyWidth)
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count == 2 else { return .zero }
        let value = measurements(proposal, subviews)
        return CGSize(width: value.width, height: max(value.avatar.height, value.body.height))
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 2 else { return }
        let value = measurements(ProposedViewSize(width: bounds.width, height: nil), subviews)
        subviews[0].place(at: CGPoint(x: mine ? bounds.maxX - value.avatar.width : bounds.minX, y: bounds.minY),
            anchor: .topLeading, proposal: ProposedViewSize(value.avatar))
        subviews[1].place(at: CGPoint(x: mine ? bounds.maxX - value.avatar.width - 10 - value.bodyWidth : bounds.minX + value.avatar.width + 10, y: bounds.minY),
            anchor: .topLeading, proposal: ProposedViewSize(width: value.bodyWidth, height: value.body.height))
    }
}

enum ConversationSpacing {
    static func messageTop(kind: String, continued: Bool, compact: Bool) -> CGFloat {
        if kind == "notice" { return 8 }
        if kind == "acts" { return 4 }
        return continued ? 4 : compact ? 7 : 14
    }
    // The reference's block margins collapse: .day's bottom 8px and the
    // following message's top margin take their maximum, not their sum.
    static func separatorBottom(kind: String, continued: Bool, compact: Bool) -> CGFloat {
        max(0, 8 - messageTop(kind: kind, continued: continued, compact: compact))
    }
}

// Opening/resizing the inspector changes line wrapping without adding a
// message. Preserve the current scroll offset through that reflow, just as
// the reference's applyPanelWidth does. New content at the same viewport can
// still follow the bottom. A person opening an existing disclosure preserves
// the current reading position rather than treating it as newly received text.
struct ConversationScrollFollowing {
    var followsBottom = true
    private var contentSize = CGSize.zero
    private var viewportSize = CGSize.zero
    private var pendingDisclosure = false

    mutating func disclosureChanged() { pendingDisclosure = true }
    mutating func contentChanged() { pendingDisclosure = false }

    mutating func observe(content: CGSize, bottom: CGFloat, viewport: CGSize) -> Bool {
        let heightChanged = abs(content.height - contentSize.height) > 1
        let reflow = contentSize.width > 0 && abs(content.width - contentSize.width) > 1
        let resized = viewportSize != .zero && viewport != viewportSize
        if pendingDisclosure {
            // TextKit can publish several heights for the same expansion.
            // Only a real server-content revision ends this interaction;
            // another layout pass must not masquerade as an incoming message.
            contentSize = content; viewportSize = viewport
            followsBottom = bottom - viewport.height < 120
            return false
        }
        let follow = heightChanged && !reflow && !resized && followsBottom
        if !heightChanged || reflow || resized { followsBottom = bottom - viewport.height < 120 }
        contentSize = content; viewportSize = viewport
        return follow
    }
}

private struct ConversationDisclosureKey: EnvironmentKey { static let defaultValue: () -> Void = {} }
extension EnvironmentValues {
    var conversationDisclosure: () -> Void {
        get { self[ConversationDisclosureKey.self] }
        set { self[ConversationDisclosureKey.self] = newValue }
    }
}

extension Model {
    func conversationRows(_ items: [Node], separators: Bool = true, calendar: Calendar = .current) -> [ConversationRow] {
        var previous: Node?, lastDay: Date?
        return NodeRow.identify(items).map { row in
            let item = row.node, date = Timeline.date(item["at"])
            var separator: String?
            if separators, let date {
                let start = calendar.startOfDay(for: date)
                if lastDay != start { separator = day(item["at"]) + " " + clock(item["at"]); lastDay = start; previous = nil }
                else if let earlier = previous.flatMap({ Timeline.date($0["at"]) }), date.timeIntervalSince(earlier) > 20 * 60 { separator = clock(item["at"]); previous = nil }
            }
            let continued: Bool
            if let previous, let date, let earlier = Timeline.date(previous["at"]) {
                continued = previous["type"].text == "message" && previous["from"].text == item["from"].text &&
                    previous["to"].rows.map(\.text) == item["to"].rows.map(\.text) &&
                    date.timeIntervalSince(earlier) < 3 * 60 && previous["thread"].isNull
            } else { continued = false }
            if item["type"].text != "acts" { previous = item }
            return ConversationRow(id: row.id, item: item, separator: separator, continued: continued)
        }
    }
    func readReceipt(_ item: Node) -> String {
        let others = item["to"].rows.map(\.text).filter { $0 != "human" }
        let read = item["read_by"].rows.map(\.text).filter { others.contains($0) }
        return others.count == 1 ? t(read.isEmpty ? "msg.unread" : "msg.read") : t("msg.read_count", ["read": String(read.count), "total": String(others.count)])
    }
}
