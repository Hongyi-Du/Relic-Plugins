import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class NativeControlStateTests: XCTestCase {
    func testKnobStateComesFromItsMountedCheckboxAndChangesWithTheRealControl() throws {
        let window = NSWindow(contentRect: NSRect(x: 20, y: 20, width: 200, height: 100), styleMask: [.borderless], backing: .buffered, defer: false)
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 200, height: 100))
        window.contentView = root
        let button = NativeSwitchControl.makeButton(), knob = NSView(frame: NSRect(x: 2, y: 2, width: 14, height: 14))
        button.setAccessibilityIdentifier("switch-owner"); root.addSubview(button); root.addSubview(knob)
        for enabled in [true, false] {
            button.isEnabled = enabled; button.state = enabled ? .on : .off
            let raw = RelicAXRead(button)
            let state: [String: Any] = ["enabled": raw["enabled"] ?? NSNull(), "focused": raw["focused"] ?? NSNull(),
                "checked": (raw["value"] as? NSNumber).map { $0.intValue == 1 } as Any? ?? NSNull(),
                "indeterminate": (raw["value"] as? NSNumber).map { $0.intValue == 2 } as Any? ?? NSNull()]
            var elements: [[String: Any]] = [
                ["id": "knob", "kind": "card", "state": ["checked": NSNull()], "native_structure": NativeElementStructure.evidence(knob, parent: "switch-owner")],
                ["id": "control", "identifier": raw["identifier"]!, "role": raw["role"]!, "state": state,
                 "native_structure": NativeElementStructure.evidence(button, parent: nil)]
            ]
            XCTAssertTrue(NativeControlState.attach(to: &elements).isEmpty)
            let measured = try XCTUnwrap(elements[0]["native_control_state"] as? [String: Any])
            XCTAssertEqual(measured["enabled"] as? Bool, enabled)
            XCTAssertEqual(measured["checked"] as? Bool, enabled)
            XCTAssertEqual(measured["indeterminate"] as? Bool, false)
            XCTAssertTrue((elements[0]["state"] as? [String: Any])?["checked"] is NSNull, "The raw decoration state must remain available")
        }
    }

    func testDirectLabelRequiresOneActualOwnerInTheSameWindow() {
        let label: [String: Any] = ["id": "label", "native_control_label_owner": "owner",
            "native_structure": ["window_identity": "window-A", "native_subview_path": [0, 3]]]
        let owner: [String: Any] = ["id": "button", "identifier": "owner", "role": "AXButton", "state": ["enabled": true, "focused": false],
            "native_structure": ["window_identity": "window-A", "native_subview_path": [0, 4]]]
        var valid = [label, owner]
        XCTAssertTrue(NativeControlState.attach(to: &valid).isEmpty)
        XCTAssertEqual((valid[0]["native_control_state"] as? [String: Any])?["enabled"] as? Bool, true)
        XCTAssertNil((valid[0]["native_control_state"] as? [String: Any])?["expanded"])
        for expanded in [false, true] {
            var disclosure = owner; disclosure["recorded_expanded"] = expanded
            var decorated = [label, disclosure]
            XCTAssertTrue(NativeControlState.attach(to: &decorated).isEmpty)
            XCTAssertEqual((decorated[0]["native_control_state"] as? [String: Any])?["expanded"] as? Bool, expanded)
            XCTAssertEqual((decorated[0]["native_control_state_evidence"] as? [String: Any])?["owner_rendered_expanded"] as? Bool, expanded)
        }
        var wrongWindow = owner
        wrongWindow["native_structure"] = ["window_identity": "window-B", "native_subview_path": [0, 4]]
        for owners in [[], [owner, owner], [wrongWindow]] {
            var nodes = [label] + owners
            XCTAssertEqual(NativeControlState.attach(to: &nodes).count, 1)
            XCTAssertNil(nodes[0]["native_control_state"], "Missing, ambiguous or unrelated controls must not provide states")
        }
    }
}
