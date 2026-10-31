import Foundation

// A knob or a control's direct label is part of that actual control. Read its
// current AX state through the unique mounted production owner, retaining the
// original decoration state separately. Do not infer states from paint colors,
// text, positions, or the reference's expected values.
enum NativeControlState {
    static func attach(to elements: inout [[String: Any]]) -> [String] {
        var errors: [String] = []
        for index in elements.indices {
            let node = elements[index]
            let structure = node["native_structure"] as? [String: Any]
            let directLabel = node["native_control_label_owner"] as? String
            let knobParent = node["kind"] as? String == "card" ? structure?["parent_identifier"] as? String : nil
            guard let identifier = directLabel ?? knobParent else { continue }
            let owners = elements.filter { $0["identifier"] as? String == identifier && $0["id"] as? String != node["id"] as? String }
            // A generic card parent does not imply inherited interaction state.
            if directLabel == nil && !owners.contains(where: { $0["role"] as? String == "AXCheckBox" }) { continue }
            guard owners.count == 1, let owner = owners.first,
                  ["AXButton", "AXCheckBox"].contains(owner["role"] as? String ?? ""),
                  let childWindow = structure?["window_identity"] as? String,
                  let childPath = structure?["native_subview_path"] as? [Int], !childPath.isEmpty,
                  let ownerStructure = owner["native_structure"] as? [String: Any],
                  ownerStructure["window_identity"] as? String == childWindow,
                  let ownerPath = ownerStructure["native_subview_path"] as? [Int], !ownerPath.isEmpty,
                  let actual = owner["state"] as? [String: Any] else {
                errors.append("Native control decoration has no unique mounted AX owner: " + identifier); continue
            }
            let fields = owner["role"] as? String == "AXCheckBox" ? ["enabled", "focused", "checked", "indeterminate"] : ["enabled", "focused"]
            var measured: [String: Any] = [:]
            for field in fields { measured[field] = actual[field] ?? NSNull() }
            if let expanded = owner["recorded_expanded"] as? Bool { measured["expanded"] = expanded }
            elements[index]["native_control_state"] = measured
            elements[index]["native_control_state_evidence"] = [
                "source": "Current AX state of the uniquely mounted control owning this production decoration",
                "owner_identifier": identifier, "owner_id": owner["id"] ?? NSNull(), "role": owner["role"] ?? NSNull(),
                "owner_native_structure": ownerStructure, "child_native_structure": structure ?? [:],
                "raw_owner_state": actual, "raw_decoration_state": node["state"] ?? NSNull(),
                "owner_rendered_expanded": owner["recorded_expanded"] ?? NSNull()
            ]
        }
        return errors
    }
}
