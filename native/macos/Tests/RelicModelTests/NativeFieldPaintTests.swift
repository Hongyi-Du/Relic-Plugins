import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeFieldPaintTests: XCTestCase {
    func testCurrentCellSwitchesDoNotClaimUnmeasuredOutlineOrShadow() throws {
        let field = ObservedSearchField.Control(frame: NSRect(x: 0, y: 0, width: 176, height: 22.4))
        let cell = try XCTUnwrap(field.cell as? NSTextFieldCell)
        var node: [String: Any] = ["style": ["outline": NSNull(), "shadow": NSNull()]]
        NativeFieldPaint.attach(to: &node, object: cell)
        let style = try XCTUnwrap(node["style"] as? [String: Any])
        XCTAssertEqual(style["backgroundColor"] as? [Int], [0, 0, 0, 0])
        XCTAssertEqual(style["borderWidth"] as? Int, 0)
        XCTAssertEqual(style["border_styles"] as? [String], Array(repeating: "none", count: 4))
        XCTAssertTrue(style["outline"] is NSNull); XCTAssertTrue(style["shadow"] is NSNull)
        let evidence = try XCTUnwrap(node["native_field_paint"] as? [String: Any])
        XCTAssertEqual(evidence["control_identity"] as? String, String(describing: ObjectIdentifier(field)))
        cell.drawsBackground = true; cell.isBordered = true
        var changed: [String: Any] = ["style": [:]]
        NativeFieldPaint.attach(to: &changed, object: cell)
        let unknown = try XCTUnwrap(changed["style"] as? [String: Any])
        XCTAssertNil(unknown["backgroundColor"]); XCTAssertNil(unknown["borderWidth"])
        var ordinary: [String: Any] = ["style": [:]]
        NativeFieldPaint.attach(to: &ordinary, object: NSTextFieldCell(textCell: "Unowned"))
        XCTAssertNil(ordinary["native_field_paint"])
    }
}
