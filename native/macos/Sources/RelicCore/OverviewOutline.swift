import Foundation

/// Every unbounded collection is a direct child of the inspector's lazy stack.
/// Nesting a lazy member list inside one section still makes that section a
/// single, potentially very large item in its parent viewport.
public struct OverviewEntry: Identifiable {
    public let id: String, kind: String, source: String
    public let node: Node
    public var first = false, last = false
}

public enum OverviewOutline {
    public static func rows(snapshot: Node, liaison: Bool) -> [OverviewEntry] {
        var result: [OverviewEntry] = []
        func section(_ key: String, _ items: [(String, Node, String)]) {
            let start = result.count
            for (index, item) in items.enumerated() {
                let identity = item.1["id"].text.isEmpty ? item.1["name"].text : item.1["id"].text
                result.append(OverviewEntry(id: key + "/" + item.0 + "/" + item.2 + "/" + (identity.isEmpty ? String(index) : identity),
                    kind: item.0, source: item.2, node: item.1))
            }
            if result.count > start { result[start].first = true; result[result.count - 1].last = true }
        }
        section("introduction", [("introduction", Node(), "")])
        let decisions = snapshot["decisions"].rows
        section("decisions", [("decisions-heading", Node(), "")] + (decisions.isEmpty
            ? [("empty", Node(), "decision.none")] : decisions.map { ("decision", $0, "") }))
        section("hierarchy", [("hierarchy", Node(), "")])
        let tasks = snapshot["tasks"].rows
        let open = tasks.filter { !["done", "dropped"].contains($0["status"].text) }
        let done = tasks.filter { $0["status"].text == "done" }
        var work: [(String, Node, String)] = [("work-heading", Node(), "")]
        if tasks.isEmpty { work.append(("empty", Node(), "org.no_tasks")) }
        else if open.isEmpty { work.append(("nothing-open", Node(), "")) }
        work += open.prefix(8).map { ("task", $0, "") }
        if open.count > 8 { work.append(("more-tasks", Node(), "")) }
        let reports = done.filter { !$0["report"].text.isEmpty }.sorted { $0["done_at"].text > $1["done_at"].text }
        if !reports.isEmpty {
            work.append(("reports-heading", Node(), ""))
            work += reports.prefix(3).map { ("task", $0, "report") }
        }
        section("work", work)
        if !liaison {
            section("people", [("people-heading", Node(), "")] + snapshot["members"].rows.map { ("member", $0, "") })
            var protocols: [(String, Node, String)] = [("protocols-heading", Node(), "")]
            for source in ["protocols", "inherited_protocols", "replaced_protocols"] {
                protocols += snapshot[source].rows.filter { source != "protocols" || ["active", "proposed"].contains($0["status"].text) }
                    .map { ("protocol", $0, source) }
            }
            if protocols.count == 1 { protocols.append(("empty", Node(), "org.no_protocols")) }
            section("protocols", protocols)
            let episodes = snapshot["episodes"].rows
            let visible = episodes.filter { $0["status"].text == "open" } + episodes.filter { $0["status"].text == "closed" }.suffix(3).reversed()
            section("episodes", [("episodes-heading", Node(), "")] + (episodes.isEmpty
                ? [("empty", Node(), "org.no_episodes")] : visible.map { ("episode", $0, "") }))
        }
        section("details", (liaison ? [("empty", Node(), "org.liaison_note")] : []) + [("details", Node(), "")])
        return result
    }
}
