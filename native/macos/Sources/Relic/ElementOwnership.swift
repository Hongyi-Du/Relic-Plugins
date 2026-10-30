import Foundation

enum ElementOwnership {
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
            let simple = ["relic-text-button/", "relic-chip-button/", "relic-avatar/", "relic-chip/", "relic-badge/", "relic-tab/"].contains { identifier.hasPrefix($0) }
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
