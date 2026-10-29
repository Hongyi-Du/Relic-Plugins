import Foundation

public struct OrganizationLayout {
    public let nodes: [Node]
    public let centers: [String: CGPoint]
    public let parents: [String: String]
    public let size: CGSize
    public static let card = CGSize(width: 236, height: 100)
    private final class Branch {
        let node: Node
        let children: [Branch]
        let width: CGFloat
        init(_ node: Node, _ children: [Branch]) {
            self.node = node; self.children = children
            width = max(OrganizationLayout.card.width, children.reduce(CGFloat(0)) { $0 + $1.width } + CGFloat(max(0, children.count - 1)) * 22)
        }
    }
    public init(_ input: [Node]) {
        func rank(_ node: Node) -> Int { (node["cabinet"].flag ? 0 : 4) + (node["kind"].text == "subgroup" ? 2 : 0) + (node["status"].text == "active" ? 0 : 1) }
        let sorted = input.enumerated().sorted { rank($0.element) == rank($1.element) ? $0.offset < $1.offset : rank($0.element) < rank($1.element) }.map(\.element)
        let ids = Set(sorted.map { $0["id"].text })
        var children: [String: [Node]] = [:], seen: Set<String> = [], order: [Node] = [], parentMap: [String: String] = [:]
        for node in sorted {
            let id = node["id"].text, parent = node["parent"].text
            children[ids.contains(parent) && parent != id ? parent : "", default: []].append(node)
        }
        func walk(_ node: Node, parent: String = "") -> Branch? {
            let id = node["id"].text
            guard seen.insert(id).inserted else { return nil }; order.append(node)
            if !parent.isEmpty { parentMap[id] = parent }
            return Branch(node, (children[id] ?? []).compactMap { walk($0, parent: id) })
        }
        var roots: [Branch] = []
        // Orphans and malformed cycles remain reachable; every organization occurs once.
        for node in (children[""] ?? []) + sorted { if let branch = walk(node) { roots.append(branch) } }
        var centers: [String: CGPoint] = [:], height: CGFloat = 0
        func place(_ branch: Branch, left: CGFloat, depth: Int) {
            let y = 24 + CGFloat(depth) * (Self.card.height + 46) + Self.card.height / 2
            centers[branch.node["id"].text] = CGPoint(x: left + branch.width / 2, y: y); height = max(height, y + Self.card.height / 2 + 24)
            var x = left
            for child in branch.children { place(child, left: x, depth: depth + 1); x += child.width + 22 }
        }
        var left: CGFloat = 24
        for root in roots { place(root, left: left, depth: 0); left += root.width + 22 }
        self.nodes = order; self.centers = centers; self.parents = parentMap
        size = CGSize(width: max(Self.card.width + 48, left - 22 + 24), height: max(Self.card.height + 48, height))
    }
    public func bounds(focus: String = "") -> CGRect {
        var ids: Set<String> = []
        func add(_ id: String) { guard ids.insert(id).inserted else { return }; for (child, parent) in parents where parent == id { add(child) } }
        if !focus.isEmpty, centers[focus] != nil { add(focus) }
        let points = centers.filter { ids.isEmpty || ids.contains($0.key) }.map(\.value)
        guard let first = points.first else { return CGRect(origin: .zero, size: size) }
        return points.reduce(CGRect(x: first.x - Self.card.width / 2, y: first.y - Self.card.height / 2, width: Self.card.width, height: Self.card.height)) { rect, p in
            rect.union(CGRect(x: p.x - Self.card.width / 2, y: p.y - Self.card.height / 2, width: Self.card.width, height: Self.card.height))
        }
    }
}
