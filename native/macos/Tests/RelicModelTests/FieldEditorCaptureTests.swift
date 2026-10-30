import XCTest
@testable import Relic

@MainActor final class FieldEditorCaptureTests: XCTestCase {
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
