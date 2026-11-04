import Foundation

/// Flat, stable rows let one lazy viewport recycle every member independently.
/// A whole expanded organization must not become one giant list item.
public struct OrganizationOutlineRow: Identifiable {
    public enum Kind: Equatable { case organization, group, member, secretary, addMember }
    public let id: String, organization: String
    public let kind: Kind, node: Node
    public let depth: Int, hasChildren: Bool
    public var first = false, last = false
}

public enum OrganizationOutline {
    public static func rows(organizations: [Node], selected: String, members: [Node], folded: Set<String>,
                            search: String, groupLabel: String, secretaryLabel: String, revealMembers: Bool) -> [OrganizationOutlineRow] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        let ids = Set(organizations.map { $0["id"].text })
        let children = Dictionary(grouping: organizations, by: { $0["parent"].text })
        var result: [OrganizationOutlineRow] = []
        func matches(_ text: String) -> Bool { query.isEmpty || text.localizedCaseInsensitiveContains(query) }
        func visit(_ org: Node, depth: Int, ancestors: Set<String>) {
            let id = org["id"].text
            guard !ancestors.contains(id) else { return }
            let active = id == selected, closed = query.isEmpty && folded.contains(id)
            let descendants = (children[id] ?? []).filter { !ancestors.union([id]).contains($0["id"].text) }
            let orgHit = matches(org["name"].text) || matches(org["purpose"].text)
            let memberHits = active ? members.filter { matches($0.display) || matches($0["name"].text) || matches($0["role"].text) } : []
            if orgHit || !memberHits.isEmpty {
                result.append(OrganizationOutlineRow(id: "org/" + id, organization: id, kind: .organization,
                    node: org, depth: depth, hasChildren: !descendants.isEmpty))
                if active && !closed && revealMembers {
                    let start = result.count
                    func append(_ key: String, _ kind: OrganizationOutlineRow.Kind, _ node: Node = Node()) {
                        result.append(OrganizationOutlineRow(id: id + "/" + key, organization: id, kind: kind, node: node, depth: depth, hasChildren: false))
                    }
                    if orgHit || matches(groupLabel) { append("group", .group) }
                    let secretary = members.first { $0["secretary"].flag }
                    if matches(secretaryLabel) || secretary.map({ item in memberHits.contains { $0["name"].text == item["name"].text } }) == true {
                        append("secretary", .secretary, secretary ?? Node())
                    }
                    for person in memberHits where !person["secretary"].flag { append("member/" + person["name"].text, .member, person) }
                    append("add", .addMember)
                    result[start].first = true; result[result.count - 1].last = true
                }
            }
            if !closed { for child in descendants { visit(child, depth: depth + 1, ancestors: ancestors.union([id])) } }
        }
        for org in organizations where org["parent"].text.isEmpty || !ids.contains(org["parent"].text) { visit(org, depth: 0, ancestors: []) }
        return result
    }
}
