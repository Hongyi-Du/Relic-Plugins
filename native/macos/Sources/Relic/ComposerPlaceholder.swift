import AppKit

/// The visible placeholder is a real read-only TextKit child of its editor.
/// Its source and glyph draw are observable through the same native renderer
/// as other labels, while the editor remains the sole accessible input.
@MainActor enum ComposerPlaceholder {
    static func makeLabel() -> ReferenceLabelView {
        let storage = NSTextStorage(), manager = NativeGlyphLayoutManager()
        manager.recordDraws = VisualCapture.enabled
        let container = NSTextContainer(containerSize: NSSize(width: 400, height: .greatestFiniteMagnitude))
        storage.addLayoutManager(manager); manager.addTextContainer(container)
        let view = ReferenceLabelView(frame: .zero, textContainer: container)
        view.sourceStorage = storage
        view.isEditable = false; view.isSelectable = false; view.drawsBackground = false
        view.focusRingType = .none; view.isRichText = true
        view.isHorizontallyResizable = false; view.isVerticallyResizable = false
        view.textContainerInset = .zero; container.lineFragmentPadding = 0
        container.widthTracksTextView = true; container.heightTracksTextView = false
        view.setAccessibilityElement(false)
        return view
    }
}

extension ComposerTextView {
    static func makeObserved(frame: NSRect) -> ComposerTextView {
        let storage = NSTextStorage(), manager = NativeGlyphLayoutManager()
        manager.recordDraws = VisualCapture.enabled
        let container = NSTextContainer(containerSize: NSSize(width: frame.width, height: .greatestFiniteMagnitude))
        storage.addLayoutManager(manager); manager.addTextContainer(container)
        let view = ComposerTextView(frame: frame, textContainer: container)
        view.observedStorage = storage
        return view
    }

    func updatePlaceholder() {
        let visible = string.isEmpty && !placeholder.isEmpty
        guard visible else { placeholderView?.isHidden = true; return }
        let label: ReferenceLabelView
        if let existing = placeholderView { label = existing }
        else { label = ComposerPlaceholder.makeLabel(); placeholderView = label; addSubview(label) }
        label.isHidden = false
        label.productionOwner = accessibilityIdentifier()
        let value = NSAttributedString(string: placeholder, attributes: placeholderAttributes)
        if !label.attributedString().isEqual(to: value) { label.textStorage?.setAttributedString(value) }
        label.setAccessibilityLabel(placeholder)
        label.frame = NSRect(x: textContainerInset.width, y: textContainerInset.height,
            width: max(0, bounds.width - textContainerInset.width * 2),
            height: max(0, bounds.height - textContainerInset.height * 2))
    }
}
