import Foundation
import RelicCore

struct ConversationRow: Identifiable {
    let id: String
    let item: Node
    let separator: String?
    let continued: Bool
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
