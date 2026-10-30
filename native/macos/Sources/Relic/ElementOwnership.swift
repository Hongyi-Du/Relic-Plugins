import Foundation

enum ElementOwnership {
    /// Restore children omitted by SwiftUI's compound-button AX projection
    /// using the component's actual parent and mounted native sibling paths.
    /// No bounding boxes, label values or reference ordering participate.
    static func attachMeasuredChildren(to elements: inout [[String: Any]]) -> [String] {
        var groups: [String: [(id: String, path: [Int])]] = [:], errors: [String] = []
        for index in elements.indices {
            guard let structure = elements[index]["native_structure"] as? [String: Any],
                  let parent = structure["parent_identifier"] as? String,
                  let id = elements[index]["id"] as? String,
                  elements[index]["identifier"] as? String != parent else { continue }
            let owners = elements.filter { $0["identifier"] as? String == parent }
            guard owners.count == 1, let owner = owners[0]["id"] as? String,
                  let path = structure["native_subview_path"] as? [Int], !path.isEmpty else {
                errors.append("Native child \(id) has no unique mounted parent/path for \(parent)"); continue
            }
            var ancestor: String? = owner, visited = Set<String>()
            while let current = ancestor, current != id, visited.insert(current).inserted {
                ancestor = elements.first(where: { $0["id"] as? String == current })?["parent"] as? String
            }
            guard ancestor != id, ancestor == nil else {
                errors.append("Native child \(id) has cyclic parent evidence for \(parent)"); continue
            }
            elements[index]["parent"] = owner
            groups[owner, default: []].append((id, path))
        }
        // Inner components first, then their actual parent retains the complete
        // child block (including owned icon/label descendants).
        let owners = groups.keys.sorted { left, right in
            func depth(_ id: String) -> Int {
                var current: String? = id, visited = Set<String>()
                while let value = current, visited.insert(value).inserted {
                    current = elements.first(where: { $0["id"] as? String == value })?["parent"] as? String
                }
                return visited.count
            }
            return depth(left) > depth(right)
        }
        for owner in owners {
            let members = groups[owner]!.sorted { $0.path.lexicographicallyPrecedes($1.path) }
            guard Set(members.map { $0.path }).count == members.count else {
                errors.append("Native parent \(owner) has ambiguous sibling paths"); continue
            }
            var blocks: [[String: Any]] = [], removed = Set<String>()
            for member in members {
                var descendants = Set([member.id]), changed = true
                while changed {
                    changed = false
                    for node in elements {
                        if let parent = node["parent"] as? String, descendants.contains(parent),
                           let id = node["id"] as? String, descendants.insert(id).inserted { changed = true }
                    }
                }
                blocks += elements.filter { ($0["id"] as? String).map { descendants.contains($0) } == true }
                removed.formUnion(descendants)
            }
            elements.removeAll { ($0["id"] as? String).map { removed.contains($0) } == true }
            if let index = elements.firstIndex(where: { $0["id"] as? String == owner }) { elements.insert(contentsOf: blocks, at: index + 1) }
        }
        return errors
    }

    /// Production identifiers connect the real label and its drawing/control.
    /// Never infer an owner from expected text, geometry or a reference element.
    /// The original AX/TextKit nodes remain in the separately saved raw tree.
    static func attachLabels(to elements: inout [[String: Any]]) -> [String] {
        let labels = elements.filter { $0["production_owner"] is String }
        var errors: [String] = []
        for var label in labels.reversed() {
            guard let identifier = label["production_owner"] as? String,
                  let labelID = label["id"] as? String else { continue }
            let owners = elements.filter { $0["identifier"] as? String == identifier && $0["id"] as? String != labelID }
            guard owners.count == 1, let ownerID = owners.first?["id"] as? String else {
                errors.append("Native label \(labelID) has \(owners.count) actual production owners for \(identifier)")
                continue // Preserve unresolved labels in their original order.
            }
            elements.removeAll { $0["id"] as? String == labelID }
            guard let index = elements.firstIndex(where: { $0["id"] as? String == ownerID }) else { continue }
            let simple = ["relic-text-button/", "relic-chip-button/", "relic-avatar/", "relic-chip/", "relic-badge/", "relic-tab/", "relic-dropdown/"].contains { identifier.hasPrefix($0) }
            if simple && labels.filter({ $0["production_owner"] as? String == identifier }).count == 1 {
                var style = elements[index]["style"] as? [String: Any] ?? [:]
                let textStyle = label["style"] as? [String: Any] ?? [:]
                for key in ["fontSize", "fontWeight", "fontFamily", "rendered_fonts", "color"] { style[key] = textStyle[key] ?? NSNull() }
                elements[index]["style"] = style
                for key in ["text", "layout", "text_bounds"] { elements[index][key] = label[key] ?? NSNull() }
                elements[index]["owned_text_id"] = labelID
                elements[index]["owned_text_evidence"] = label
                elements[index]["projection_reason"] = "Actual production component owns its single native label; original TextKit node retained"
            } else {
                label["parent"] = ownerID
                elements.insert(label, at: index + 1)
            }
        }
        return errors
    }
}
