import AppKit

/// Read only the paint switches of our final, borderless native field classes.
/// An external SwiftUI decoration or a field editor's paint is not inferred
/// from these switches; unmeasured shadow/outline/corner properties stay null.
@MainActor enum NativeFieldPaint {
    static func attach(to node: inout [String: Any], object: AnyObject) {
        guard let cell = object as? NSTextFieldCell,
              type(of: cell) == ObservedSearchField.Cell.self || type(of: cell) == MemberRenameField.PaddedCell.self,
              let control = cell.controlView as? NSTextField, control.cell === cell else { return }
        let editor = control.currentEditor() as? NSTextView
        let evidence: [String: Any] = [
            "source": "current production NSTextFieldCell paint switches",
            "cell_identity": String(describing: ObjectIdentifier(cell)),
            "control_identity": String(describing: ObjectIdentifier(control)),
            "window_identity": control.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "cell_class": String(describing: type(of: cell)),
            "draws_background": cell.drawsBackground, "bordered": cell.isBordered, "bezeled": cell.isBezeled,
            "editor_draws_background": editor.map(\.drawsBackground) as Any? ?? NSNull(),
            "scope": "Cell background and border only; excludes parent and editor effects"]
        node["native_field_paint"] = evidence
        var style = node["style"] as? [String: Any] ?? [:]
        if !cell.drawsBackground && editor?.drawsBackground != true {
            style["backgroundColor"] = [0, 0, 0, 0]
        }
        if !cell.isBordered && !cell.isBezeled {
            style["borderColor"] = [0, 0, 0, 0]; style["borderWidth"] = 0
            style["border_widths"] = [0, 0, 0, 0]
            style["border_styles"] = ["none", "none", "none", "none"]
            style["border_colors"] = Array(repeating: [0, 0, 0, 0], count: 4)
        }
        style["opacity"] = NativeVisibility.opacity(control)
        node["style"] = style
    }
}
