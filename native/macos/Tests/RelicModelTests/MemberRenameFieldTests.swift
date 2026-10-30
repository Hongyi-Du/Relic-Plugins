import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class MemberRenameFieldTests: XCTestCase {
    func testNativeInputOwnsItsPaddingAndLeavesSpaceForMicrophone() async throws {
        _ = NSApplication.shared
        let input = MemberRenameField(placeholder: "Member", identifier: "relic-input/member-rename", hint: "Rename", text: .constant("Current name"), focused: .constant(false), save: {}, cancel: {})
        let host = NSHostingView(rootView: input.frame(width: 195, height: 32.4))
        let window = NSWindow(contentRect: CGRect(x: 80, y: 80, width: 195, height: 32.4), styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil); defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(50))
        func find(_ view: NSView) -> MemberRenameField.Control? {
            if let field = view as? MemberRenameField.Control { return field }
            return view.subviews.lazy.compactMap { find($0) }.first
        }
        let field = try XCTUnwrap(find(host))
        XCTAssertEqual(field.frame.width, 195)
        XCTAssertEqual(field.alignmentRectInsets.left, 0)
        XCTAssertEqual(field.alignmentRectInsets.right, 0)
        XCTAssertEqual(field.accessibilityIdentifier(), "relic-input/member-rename")
        XCTAssertEqual(field.accessibilityFrame(), window.convertToScreen(field.convert(field.bounds, to: nil)))
        let cell = try XCTUnwrap(field.cell as? MemberRenameField.PaddedCell)
        let drawing = cell.drawingRect(forBounds: field.bounds)
        XCTAssertEqual(drawing.minX, 9)
        XCTAssertEqual(field.bounds.maxX - drawing.maxX, 35)
        XCTAssertEqual(drawing.midY, field.bounds.midY)
        XCTAssertTrue(field.isAccessibilityElement())
        XCTAssertTrue(field.isEditable)
        XCTAssertEqual(field.stringValue, "Current name")
        let editor = try XCTUnwrap(field.currentEditor() as? NSTextView)
        XCTAssertEqual(editor.selectedRange(), NSRange(location: 0, length: 0))
    }

    func testCommitCancelAndLengthLimitUseNativeTextFieldDelegate() {
        var text = "", focused = false, saves = 0, cancels = 0
        let input = MemberRenameField(placeholder: "Member", identifier: "test", hint: "Rename", text: Binding(get: { text }, set: { text = $0 }), focused: Binding(get: { focused }, set: { focused = $0 }), save: { saves += 1 }, cancel: { cancels += 1 })
        let coordinator = MemberRenameField.Coordinator(input)
        let field = NSTextField(string: String(repeating: "a", count: 39) + "🙂")
        let event = Notification(name: NSControl.textDidChangeNotification, object: field)
        coordinator.controlTextDidChange(event)
        XCTAssertEqual(text, String(repeating: "a", count: 39))
        XCTAssertEqual(field.stringValue, text)
        coordinator.controlTextDidBeginEditing(event); XCTAssertTrue(focused)
        coordinator.controlTextDidEndEditing(event); XCTAssertFalse(focused)
        let editor = NSTextView()
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: #selector(NSResponder.insertNewline(_:))))
        XCTAssertTrue(coordinator.control(field, textView: editor, doCommandBy: #selector(NSResponder.cancelOperation(_:))))
        XCTAssertFalse(coordinator.control(field, textView: editor, doCommandBy: #selector(NSResponder.moveLeft(_:))))
        XCTAssertEqual(saves, 1); XCTAssertEqual(cancels, 1)
        editor.setMarkedText("拼", selectedRange: NSRange(location: 1, length: 0), replacementRange: NSRange(location: NSNotFound, length: 0))
        XCTAssertTrue(editor.hasMarkedText())
        XCTAssertFalse(coordinator.control(field, textView: editor, doCommandBy: #selector(NSResponder.insertNewline(_:))))
        XCTAssertEqual(saves, 1, "IME confirmation must not submit the rename")
    }
}
