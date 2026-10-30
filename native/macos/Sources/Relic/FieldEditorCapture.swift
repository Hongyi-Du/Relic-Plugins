import AppKit

@MainActor enum FieldEditorCapture {
    /// AppKit lends a window field editor to a native text field. That editor
    /// draws the same input's current value; it is not another visible input.
    /// Record the actual currentEditor relationship before any projection.
    static func receipts(in window: NSWindow) -> [[String: Any]] {
        var rows: [[String: Any]] = []
        func walk(_ view: NSView) {
            if let field = view as? MemberRenameField.Control,
               let editor = field.currentEditor() as? NSTextView,
               field.window === window, editor.window === window,
               NativeVisibility.screenClip(field).map({ !$0.isNull && !$0.isEmpty }) == true,
               NativeVisibility.screenClip(editor).map({ !$0.isNull && !$0.isEmpty }) == true {
                rows.append([
                    "contract": "appkit-current-field-editor-v1", "provider": "mounted NSTextField.currentEditor and NSWindow.firstResponder",
                    "owner_identity": String(describing: ObjectIdentifier(field)),
                    "owner_class": String(describing: type(of: field)), "owner_identifier": field.accessibilityIdentifier() ?? "",
                    "editor_identity": String(describing: ObjectIdentifier(editor)), "editor_class": String(describing: type(of: editor)),
                    "current_editor_identity": String(describing: ObjectIdentifier(field.currentEditor()!)),
                    "window_identity": String(describing: ObjectIdentifier(window)),
                    "is_field_editor": editor.isFieldEditor, "same_window": editor.window === field.window,
                    "first_responder_is_editor": window.firstResponder === editor,
                    "owner_value": field.stringValue, "editor_value": editor.string,
                    "selection": ["location": editor.selectedRange().location, "length": editor.selectedRange().length],
                    "owner_screen_bounds": ElementCapture.box(window.convertToScreen(field.convert(field.bounds, to: nil))),
                    "editor_screen_bounds": ElementCapture.box(window.convertToScreen(editor.convert(editor.bounds, to: nil)))])
            }
            for child in view.subviews { walk(child) }
        }
        if let root = window.contentView { walk(root) }
        return rows
    }

    static func attach(to elements: inout [[String: Any]], receipts: [[String: Any]]) -> [String] {
        var errors: [String] = []
        for receipt in receipts {
            guard let ownerIdentity = receipt["owner_identity"] as? String,
                  let editorIdentity = receipt["editor_identity"] as? String else { errors.append("Field editor receipt has no native identities"); continue }
            let owners = elements.indices.filter { elements[$0]["object_identity"] as? String == ownerIdentity && elements[$0]["kind"] as? String == "input" }
            let editors = elements.indices.filter { elements[$0]["object_identity"] as? String == editorIdentity && elements[$0]["kind"] as? String == "input" }
            guard receipt["contract"] as? String == "appkit-current-field-editor-v1",
                  receipt["owner_class"] as? String == String(describing: MemberRenameField.Control.self),
                  !(receipt["window_identity"] as? String ?? "").isEmpty,
                  owners.count == 1, editors.count == 1, let owner = owners.first, let editor = editors.first, owner != editor,
                  receipt["current_editor_identity"] as? String == editorIdentity,
                  receipt["is_field_editor"] as? Bool == true, receipt["same_window"] as? Bool == true,
                  receipt["first_responder_is_editor"] as? Bool == true,
                  let source = receipt["owner_value"] as? String, receipt["editor_value"] as? String == source,
                  elements[owner]["identifier"] as? String == receipt["owner_identifier"] as? String else {
                errors.append("Field editor \(editorIdentity) has no unique current native input owner/value/focus binding"); continue
            }
            let original = elements[editor]
            guard let ownerID = elements[owner]["id"] as? String, let editorID = original["id"] as? String else {
                errors.append("Field editor owner or editor has no captured id"); continue
            }
            elements[owner]["native_field_editor"] = receipt
            elements[owner]["owned_editor_evidence"] = original
            // Keep any actual visible children; only the duplicate input
            // representation is owned by the real text field.
            for index in elements.indices where elements[index]["parent"] as? String == editorID { elements[index]["parent"] = ownerID }
            elements.remove(at: editor)
        }
        return errors
    }
}
