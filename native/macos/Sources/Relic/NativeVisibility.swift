import AppKit

enum NativeVisibility {
    static func opacity(_ view: NSView) -> Double {
        var value = 1.0, ancestor: NSView? = view
        while let current = ancestor { value *= Double(current.alphaValue); ancestor = current.superview }
        return value
    }
    static func localClip(_ view: NSView) -> NSRect {
        guard !view.isHiddenOrHasHiddenAncestor, opacity(view) > 0 else { return .null }
        return view.visibleRect
    }
    static func screenClip(_ view: NSView) -> NSRect? {
        guard let window = view.window else { return nil }
        let clip = localClip(view)
        guard window.isVisible, !clip.isNull, !clip.isEmpty else { return .null }
        return window.convertToScreen(view.convert(clip, to: nil))
    }
}
