import AppKit
import SwiftUI
import RelicCore

/// The native input owns its padding as interactive space. Padding outside a
/// SwiftUI TextField only enlarges its decoration, leaving the inner cell as
/// the accessibility/input rectangle and an unfocusable gutter.
struct MemberRenameField: NSViewRepresentable {
    let placeholder: String, identifier: String, hint: String
    @Binding var text: String
    @Binding var focused: Bool
    let save: () -> Void
    let cancel: () -> Void
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> Control {
        let field = Control(frame: .zero)
        field.cell = PaddedCell(textCell: "")
        field.cell?.isScrollable = true; field.cell?.usesSingleLineMode = true
        field.isEditable = true; field.isSelectable = true; field.isBezeled = false
        field.isBordered = false; field.drawsBackground = false; field.focusRingType = .none
        field.font = RelicStyle.nativeFont(14, weight: 400)
        field.delegate = context.coordinator
        field.setAccessibilityIdentifier(identifier); field.setAccessibilityLabel(placeholder)
        field.setAccessibilityHelp(hint)
        updateNSView(field, context: context)
        return field
    }
    func updateNSView(_ field: Control, context: Context) {
        context.coordinator.parent = self
        field.isEnabled = enabled; field.textColor = NSColor(RelicStyle.ink)
        field.placeholderAttributedString = NSAttributedString(string: placeholder, attributes: [.font: RelicStyle.nativeFont(14, weight: 400), .foregroundColor: NSColor(RelicStyle.placeholder)])
        field.setAccessibilityLabel(placeholder); field.setAccessibilityHelp(hint)
        if field.stringValue != text, (field.currentEditor() as? NSTextView)?.hasMarkedText() != true { field.stringValue = text }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: Control, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? 195, height: 32.4)
    }
    final class Control: NSTextField {
        private var initiallyFocused = false
        // AppKit's standard text-field bezel has alignment outsets. This
        // borderless control paints no bezel; its frame is the input box.
        override var alignmentRectInsets: NSEdgeInsets { NSEdgeInsets(top: 0, left: 0, bottom: 0, right: 0) }
        override func isAccessibilityElement() -> Bool { true }
        override func accessibilityFrame() -> NSRect {
            window.map { $0.convertToScreen(convert(bounds, to: nil)) } ?? .zero
        }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard window != nil, !initiallyFocused else { return }
            initiallyFocused = true
            DispatchQueue.main.async { [weak self] in
                guard let self, let window = self.window, self.isEnabled else { return }
                window.makeFirstResponder(self)
                // The reference focuses a populated input without selecting
                // its contents; opening Rename must not highlight the name.
                (self.currentEditor() as? NSTextView)?.setSelectedRange(NSRange(location: 0, length: 0))
            }
        }
    }
    final class PaddedCell: NSTextFieldCell {
        private lazy var observedEditor = ObservedFieldEditor.make()
        override func fieldEditor(for controlView: NSView) -> NSTextView? { observedEditor }
        override func drawingRect(forBounds rect: NSRect) -> NSRect {
            let content = NSRect(x: rect.minX + 9, y: rect.minY, width: max(0, rect.width - 44), height: rect.height)
            let height = min(content.height, cellSize(forBounds: content).height)
            return NSRect(x: content.minX, y: content.minY + (content.height - height) / 2, width: content.width, height: height)
        }
        override func titleRect(forBounds rect: NSRect) -> NSRect { drawingRect(forBounds: rect) }
        override func edit(withFrame rect: NSRect, in view: NSView, editor: NSText, delegate: Any?, event: NSEvent?) {
            super.edit(withFrame: drawingRect(forBounds: rect), in: view, editor: editor, delegate: delegate, event: event)
        }
        override func select(withFrame rect: NSRect, in view: NSView, editor: NSText, delegate: Any?, start: Int, length: Int) {
            super.select(withFrame: drawingRect(forBounds: rect), in: view, editor: editor, delegate: delegate, start: start, length: length)
        }
    }
    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: MemberRenameField
        init(_ parent: MemberRenameField) { self.parent = parent }
        func controlTextDidBeginEditing(_ notification: Notification) { parent.focused = true }
        func controlTextDidEndEditing(_ notification: Notification) { parent.focused = false }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else { return }
            let value = ReferenceText.inputPrefix(field.stringValue, utf16Limit: 40)
            if (field.currentEditor() as? NSTextView)?.hasMarkedText() == true { return }
            if value != field.stringValue { field.stringValue = value }
            parent.text = value
        }
        func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                guard !textView.hasMarkedText() else { return false }
                parent.save(); return true
            }
            if commandSelector == #selector(NSResponder.cancelOperation(_:)) { parent.cancel(); return true }
            return false
        }
    }
}
