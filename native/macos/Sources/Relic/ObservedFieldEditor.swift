import AppKit

/// An ordinary AppKit field editor with the same observable TextKit renderer
/// as the composer. NSCell owns selection, IME and Return/Tab dispatch.
final class ObservedFieldEditor: NSTextView {
    private var sourceStorage: NSTextStorage?
    var focusChanged: ((Bool) -> Void)?
    override func becomeFirstResponder() -> Bool {
        let accepted = super.becomeFirstResponder()
        if accepted { focusChanged?(true) }
        return accepted
    }
    override func resignFirstResponder() -> Bool {
        let accepted = super.resignFirstResponder()
        if accepted { focusChanged?(false) }
        return accepted
    }
    static func make() -> ObservedFieldEditor {
        let storage = NSTextStorage(), manager = NativeGlyphLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 400, height: CGFloat.greatestFiniteMagnitude))
        storage.addLayoutManager(manager); manager.addTextContainer(container)
        manager.recordDraws = VisualCapture.enabled
        let editor = ObservedFieldEditor(frame: .zero, textContainer: container)
        editor.sourceStorage = storage
        editor.isFieldEditor = true; editor.isRichText = false
        editor.drawsBackground = false; editor.focusRingType = .none
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false
        return editor
    }
}
