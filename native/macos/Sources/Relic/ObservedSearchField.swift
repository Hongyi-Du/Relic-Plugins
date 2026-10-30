import AppKit
import SwiftUI

/// A native search input whose placeholder uses the same observed TextKit
/// painter as the other labels. The NSCell still owns editing, selection and
/// input methods; the placeholder is not a second accessible element.
struct ObservedSearchField: NSViewRepresentable {
    let placeholder: String
    let accessibleName: String
    @Binding var text: String
    @Binding var focused: Bool
    @Environment(\.isEnabled) private var enabled
    static let identifier = "relic-input/sidebar-search"

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> Control {
        let field = Control(frame: .zero)
        field.delegate = context.coordinator
        updateNSView(field, context: context)
        return field
    }
    func updateNSView(_ field: Control, context: Context) {
        context.coordinator.parent = self
        field.isEnabled = enabled
        field.focusChanged = { [weak coordinator = context.coordinator] value in coordinator?.parent.focused = value }
        field.placeholder = placeholder
        field.cell?.setAccessibilityLabel(accessibleName)
        if field.stringValue != text, (field.currentEditor() as? NSTextView)?.hasMarkedText() != true {
            field.stringValue = text
        }
        field.updatePlaceholder()
        field.requestFocus(focused)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: Control, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? 176, height: 22.4)
    }

    final class Control: NSTextField {
        let placeholderView = ComposerPlaceholder.makeLabel()
        var placeholder = ""
        var focusChanged: ((Bool) -> Void)?
        private var pendingFocus: Bool?
        override init(frame: NSRect) {
            super.init(frame: frame)
            cell = Cell(textCell: "")
            isEditable = true; isSelectable = true
            isBezeled = false; isBordered = false; drawsBackground = false; focusRingType = .none
            font = RelicStyle.nativeFont(14, weight: 400); textColor = NSColor(RelicStyle.ink)
            cell?.isScrollable = true; cell?.usesSingleLineMode = true
            cell?.setAccessibilityIdentifier(ObservedSearchField.identifier)
            setAccessibilityIdentifier(ObservedSearchField.identifier)
            placeholderView.productionOwner = ObservedSearchField.identifier
            placeholderView.productionRegion = "sidebar"
            placeholderView.textContainer?.maximumNumberOfLines = 1
            placeholderView.textContainer?.lineBreakMode = .byClipping
            addSubview(placeholderView)
        }
        required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
        override var alignmentRectInsets: NSEdgeInsets { NSEdgeInsets(top: 0, left: 0, bottom: 0, right: 0) }
        override func isAccessibilityElement() -> Bool { false }
        override func layout() { super.layout(); updatePlaceholder() }
        override func textDidChange(_ notification: Notification) {
            super.textDidChange(notification); updatePlaceholder()
        }
        func updatePlaceholder() {
            // The ordinary cell draws no placeholder; this actual child owns
            // those pixels in both focused and unfocused empty-input states.
            placeholderAttributedString = nil
            placeholderView.isHidden = !stringValue.isEmpty || placeholder.isEmpty
            guard !placeholderView.isHidden else { return }
            let value = ReferenceLabel(placeholder, size: 14, color: RelicStyle.placeholder,
                lineHeight: 22.4, truncates: false).attributedText
            if !placeholderView.attributedString().isEqual(to: value) {
                placeholderView.textStorage?.setAttributedString(value)
                placeholderView.invalidateLabelPaint()
            }
            placeholderView.setAccessibilityLabel(placeholder)
            placeholderView.frame = bounds
        }
        func requestFocus(_ wanted: Bool) {
            if wanted == (currentEditor() != nil) { pendingFocus = nil; return }
            guard pendingFocus != wanted else { return }
            pendingFocus = wanted
            DispatchQueue.main.async { [weak self] in
                guard let self, self.pendingFocus == wanted else { return }
                self.pendingFocus = nil
                guard let window = self.window, self.isEnabled else { return }
                if wanted { window.makeFirstResponder(self) }
                else if self.currentEditor() != nil { window.makeFirstResponder(nil) }
            }
        }
    }
    final class Cell: NSTextFieldCell {
        private lazy var editor = ObservedFieldEditor.make()
        override func accessibilityPlaceholderValue() -> String? { (controlView as? Control)?.placeholder }
        override func accessibilityFrame() -> NSRect {
            guard let view = controlView, let window = view.window else { return .zero }
            return window.convertToScreen(view.convert(view.bounds, to: nil))
        }
        override func fieldEditor(for controlView: NSView) -> NSTextView? {
            editor.focusChanged = { [weak controlView] value in (controlView as? Control)?.focusChanged?(value) }
            return editor
        }
        override func setUpFieldEditorAttributes(_ textObj: NSText) -> NSText {
            let value = super.setUpFieldEditorAttributes(textObj)
            if let editor = value as? NSTextView {
                editor.insertionPointColor = NSColor(RelicStyle.ink)
                editor.typingAttributes[.relicConfiguredFontWeight] = 400
                editor.typingAttributes[.tracking] = 0
                editor.typingAttributes[.relicLabelSpan] = "uniform-production-label"
            }
            return value
        }
    }
    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: ObservedSearchField
        init(_ parent: ObservedSearchField) { self.parent = parent }
        func controlTextDidBeginEditing(_ notification: Notification) { parent.focused = true }
        func controlTextDidEndEditing(_ notification: Notification) { parent.focused = false }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? Control else { return }
            // Do not rewrite marked text; AppKit retains the composition.
            if (field.currentEditor() as? NSTextView)?.hasMarkedText() != true { parent.text = field.stringValue }
            field.updatePlaceholder()
        }
    }
}
