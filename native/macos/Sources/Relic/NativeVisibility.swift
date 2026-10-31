import AppKit

enum NativeVisibility {
    static func opacityAncestry(_ view: NSView) -> [[String: Any]] {
        var result: [[String: Any]] = [], ancestor: NSView? = view
        while let current = ancestor {
            result.append(["identity": String(describing: ObjectIdentifier(current)), "class": String(describing: type(of: current)), "alpha": Double(current.alphaValue)])
            ancestor = current.superview
        }
        return result
    }
    static func opacity(_ view: NSView) -> Double {
        var value = 1.0, ancestor: NSView? = view
        while let current = ancestor { value *= Double(current.alphaValue); ancestor = current.superview }
        return value
    }
    static func localClip(_ view: NSView, limitingToBounds: Bool = true) -> NSRect {
        guard !view.isHiddenOrHasHiddenAncestor, opacity(view) > 0 else { return .null }
        return limitingToBounds ? view.visibleRect.intersection(view.bounds) : view.visibleRect
    }
    static func screenClip(_ view: NSView, limitingToBounds: Bool = true) -> NSRect? {
        guard let window = view.window else { return nil }
        let clip = localClip(view, limitingToBounds: limitingToBounds)
        guard window.isVisible, !clip.isNull, !clip.isEmpty else { return .null }
        return window.convertToScreen(view.convert(clip, to: nil))
    }
}
