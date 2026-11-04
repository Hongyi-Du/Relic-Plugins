import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ObservedSearchFieldTests: XCTestCase {
    func testFormConfigurationBindsTheActualCellAndPlaceholderFontToTheSameInput() throws {
        _ = NSApplication.shared
        let field = ObservedSearchField.Control(frame: NSRect(x: 0, y: 0, width: 186, height: 20.608))
        field.configure(.init(identifier: "relic-input/runtime-path", region: "dialog", pointSize: 12.88,
            lineHeight: 20.608, monospaced: true, color: RelicStyle.secondary))
        field.placeholder = "自动查找"; field.updatePlaceholder()
        let window = NSWindow(contentRect: field.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = field; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        field.layoutSubtreeIfNeeded()
        let label = field.placeholderView
        let manager = try XCTUnwrap(label.layoutManager as? NativeGlyphLayoutManager); manager.recordDraws = true
        let bitmap = try XCTUnwrap(CaptureRaster.forView(label)); label.cacheDisplay(in: label.bounds, to: bitmap)
        XCTAssertEqual(field.font?.pointSize ?? 0, 12.88, accuracy: 0.00001)
        XCTAssertEqual(field.font?.fontName, RelicStyle.monoFont(12.88).fontName)
        XCTAssertEqual(field.textColor, NSColor(RelicStyle.secondary))
        XCTAssertEqual(field.cell?.accessibilityIdentifier(), "relic-input/runtime-path")
        XCTAssertEqual(label.productionOwner, "relic-input/runtime-path")
        XCTAssertEqual(label.productionRegion, "dialog")
        let run = try XCTUnwrap(ElementCapture.textRuns(label).first)
        XCTAssertEqual((run["style"] as? [String: Any])?["fontSize"] as? Double ?? 0, 12.88, accuracy: 0.00001)
        XCTAssertEqual(manager.fontEvidence(for: NSRange(location: 0, length: 4), in: label)["status"] as? String,
            "measured-current-draw")
        XCTAssertNil(field.placeholderAttributedString)
    }

    func testInputMethodRetainsEnterBeforeAnyFormOrSuggestionCommand() {
        _ = NSApplication.shared
        var commands: [ObservedSearchField.Command] = []
        let input = ObservedSearchField(placeholder: "", accessibleName: "", text: .constant(""),
            focused: .constant(false), command: { commands.append($0); return true })
        let coordinator = input.makeCoordinator()
        let field = ObservedSearchField.Control(frame: .zero), editor = NSTextView()
        editor.setMarkedText("拼", selectedRange: NSRange(location: 1, length: 0), replacementRange: NSRange(location: NSNotFound, length: 0))
        XCTAssertTrue(editor.hasMarkedText())
        XCTAssertFalse(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("insertNewline:")))
        XCTAssertFalse(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("moveDown:")))
        XCTAssertTrue(commands.isEmpty)
        editor.unmarkText()
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("insertNewline:")))
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("moveDown:")))
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("moveUp:")))
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("cancelOperation:")))
        XCTAssertEqual(commands, [.submit, .down, .up, .cancel])
        XCTAssertFalse(coordinator.control(field, textView: editor, doCommandBy: NSSelectorFromString("deleteBackward:")))
    }
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
        field.requestFocus(true); field.requestFocus(false)
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        XCTAssertNil(field.currentEditor(), "A cancelled keyboard focus request must not steal focus on the next run loop")
    }
}
