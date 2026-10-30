import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ObservedSearchFieldTests: XCTestCase {
    func testMountedPlaceholderHasActualGlyphEvidenceAndTheInputRetainsItsValue() throws {
        _ = NSApplication.shared
        for title in ["搜索组织和成员", "Search organizations and members"] {
            let field = ObservedSearchField.Control(frame: NSRect(x: 0, y: 0, width: 176, height: 22.4))
            field.placeholder = title; field.updatePlaceholder()
            let window = NSWindow(contentRect: field.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = field; window.orderFront(nil)
            defer { window.orderOut(nil); window.contentView = nil; window.close() }
            field.layoutSubtreeIfNeeded()
            let label = field.placeholderView
            let manager = try XCTUnwrap(label.layoutManager as? NativeGlyphLayoutManager); manager.recordDraws = true
            let bitmap = try XCTUnwrap(CaptureRaster.forView(label)); label.cacheDisplay(in: label.bounds, to: bitmap)
            let range = NSRange(location: 0, length: (title as NSString).length)
            XCTAssertEqual(manager.fontEvidence(for: range, in: label)["status"] as? String, "measured-current-draw")
            XCTAssertEqual(label.productionOwner, ObservedSearchField.identifier)
            XCTAssertEqual(field.cell?.accessibilityPlaceholderValue(), title)
            XCTAssertEqual(label.frame, field.bounds)
            XCTAssertEqual(field.cell?.accessibilityFrame(), window.convertToScreen(field.convert(field.bounds, to: nil)))
            XCTAssertNil(label.hitTest(.zero)); XCTAssertEqual(field.stringValue, "")
            XCTAssertNil(field.placeholderAttributedString, "The ordinary cell must not draw a second placeholder")
            field.stringValue = "Actual query"; field.updatePlaceholder()
            XCTAssertTrue(label.isHidden); XCTAssertEqual(field.stringValue, "Actual query")
            field.stringValue = ""; field.updatePlaceholder(); XCTAssertFalse(label.isHidden)
        }
    }

    func testActualNativeFieldEditorOwnsFocusAndSelection() throws {
        _ = NSApplication.shared
        let field = ObservedSearchField.Control(frame: NSRect(x: 0, y: 0, width: 176, height: 22.4))
        field.stringValue = "Search query"
        let window = NSWindow(contentRect: field.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = field; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        var focused = false; field.focusChanged = { focused = $0 }
        XCTAssertTrue(window.makeFirstResponder(field))
        let editor = try XCTUnwrap(field.currentEditor() as? ObservedFieldEditor)
        XCTAssertTrue(window.firstResponder === editor); XCTAssertTrue(focused)
        editor.setSelectedRange(NSRange(location: 2, length: 4))
        XCTAssertEqual(editor.selectedRange(), NSRange(location: 2, length: 4))
        let receipt = try XCTUnwrap(FieldEditorCapture.receipts(in: window).first)
        XCTAssertEqual(receipt["contract"] as? String, "appkit-current-field-editor-v3")
        XCTAssertEqual(receipt["owner_value"] as? String, receipt["editor_value"] as? String)
        window.makeFirstResponder(nil); XCTAssertFalse(focused)
    }
}
