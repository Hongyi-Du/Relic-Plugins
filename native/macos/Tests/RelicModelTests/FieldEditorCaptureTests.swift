import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class FieldEditorCaptureTests: XCTestCase {
    func testMountedStandardFieldBindsItsRealSharedEditorWithoutAClassAllowlist() throws {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 240, height: 100),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 100))
        let field = NSTextField(frame: NSRect(x: 20, y: 20, width: 180, height: 24))
        field.stringValue = "Actual current value"
        field.isEditable = true; field.isSelectable = true
        let cell = try XCTUnwrap(field.cell as? NSTextFieldCell)
        cell.setAccessibilityIdentifier("relic-input/ordinary-field")
        root.addSubview(field); window.contentView = root; window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        field.selectText(nil)
        let editor = try XCTUnwrap(field.currentEditor() as? NSTextView)
        let receipt = try XCTUnwrap(FieldEditorCapture.receipts(in: window).first)
        XCTAssertEqual(receipt["contract"] as? String, "appkit-current-field-editor-v3")
        XCTAssertEqual(receipt["editor_identity"] as? String, String(describing: ObjectIdentifier(editor)))
        XCTAssertEqual(receipt["owner_identity"] as? String, String(describing: ObjectIdentifier(cell)))
        XCTAssertTrue(window.firstResponder === editor)
        func node(_ object: AnyObject, id: String) -> [String: Any] {
            let actual = RelicAXRead(object)
            return ["id": id, "kind": ElementCapture.kind(actual["role"] as? String ?? ""),
                "object_identity": String(describing: ObjectIdentifier(object)),
                "class": String(describing: type(of: object)), "identifier": actual["identifier"] ?? ""]
        }
        let original = [node(cell, id: "field"), node(editor, id: "editor")]
        var values = original
        XCTAssertTrue(FieldEditorCapture.attach(to: &values, receipts: [receipt]).isEmpty)
        XCTAssertEqual(values.count, 1)
        XCTAssertEqual((values[0]["owned_editor_evidence"] as? [String: Any])?["id"] as? String, "editor")
        for key in ["owner_is_text_field_cell", "control_is_text_field", "editor_is_text_view"] {
            var invalid = receipt; invalid[key] = false; values = original
            XCTAssertFalse(FieldEditorCapture.attach(to: &values, receipts: [invalid]).isEmpty, key)
            XCTAssertEqual(values.count, 2, key)
        }
        XCTAssertTrue(window.makeFirstResponder(nil))
        XCTAssertTrue(FieldEditorCapture.receipts(in: window).isEmpty, "An ended edit must not retain an owner binding")
    }
    private var nodes: [[String: Any]] { [
        ["id": "field", "kind": "input", "object_identity": "field-object", "identifier": "relic-input/member-rename", "rect": ["x": 40]],
        ["id": "editor", "kind": "input", "object_identity": "editor-object", "rect": ["x": 49], "text": "Name"],
        ["id": "child", "kind": "text", "parent": "editor", "text": "Retained child"]] }
    private var receipt: [String: Any] { [
        "contract": "appkit-current-field-editor-v2", "owner_class": String(describing: MemberRenameField.PaddedCell.self),
        "owner_identity": "field-object", "owner_identifier": "relic-input/member-rename",
        "control_identity": "control-object", "owner_control_view_identity": "control-object", "control_cell_identity": "field-object",
        "editor_identity": "editor-object", "current_editor_identity": "editor-object", "window_identity": "window-object",
        "is_field_editor": true, "same_window": true, "first_responder_is_editor": true,
        "owner_value": "Name", "editor_value": "Name"] }

    func testCurrentEditorIsOwnedWithoutReplacingTheInputBoxOrDroppingChildren() throws {
        var values = nodes
        XCTAssertTrue(FieldEditorCapture.attach(to: &values, receipts: [receipt]).isEmpty)
        XCTAssertEqual(values.count, 2)
        XCTAssertEqual((values[0]["rect"] as? [String: Int])?["x"], 40)
        XCTAssertEqual((values[0]["owned_editor_evidence"] as? [String: Any])?["id"] as? String, "editor")
        XCTAssertNotNil(values[0]["native_field_editor"])
        XCTAssertEqual(values[1]["parent"] as? String, "field")
        XCTAssertEqual(values[1]["text"] as? String, "Retained child")
    }

    func testStaleAmbiguousOrUnboundEditorsStayVisibleAndFail() {
        let changes: [(String, Any)] = [
            ("current_editor_identity", "another-editor"), ("same_window", false), ("is_field_editor", false),
            ("first_responder_is_editor", false), ("editor_value", "Different value"),
            ("owner_identifier", "other-field"), ("owner_class", "UnmeasuredSubclass"),
            ("control_cell_identity", "another-cell"), ("owner_control_view_identity", "another-control"),
            ("contract", "unknown"), ("window_identity", "")]
        for (key, value) in changes {
            var values = nodes, evidence = receipt; evidence[key] = value
            XCTAssertFalse(FieldEditorCapture.attach(to: &values, receipts: [evidence]).isEmpty, key)
            XCTAssertEqual(values.count, 3, key)
            XCTAssertNil(values[0]["owned_editor_evidence"], key)
        }
        var ambiguous = nodes; var duplicate = nodes[0]; duplicate["id"] = "duplicate-owner"; ambiguous.append(duplicate)
        XCTAssertFalse(FieldEditorCapture.attach(to: &ambiguous, receipts: [receipt]).isEmpty)
        XCTAssertEqual(ambiguous.count, 4)
    }
}
