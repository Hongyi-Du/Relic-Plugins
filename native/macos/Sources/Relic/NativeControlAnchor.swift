import AppKit
import SwiftUI

/// Reads the mounted control at the moment it is activated. A SwiftUI geometry
/// preference can be reset during overlay layout; it is not a durable anchor.
@MainActor final class NativeControlAnchor: ObservableObject {
    weak var view: Probe?
    var screenBounds: CGRect? {
        guard let view, let window = view.window, !view.bounds.isEmpty else { return nil }
        return window.convertToScreen(view.convert(view.bounds, to: nil))
    }
    var contentBounds: CGRect? {
        guard let view, let root = view.window?.contentView, !view.bounds.isEmpty else { return nil }
        let rect = view.convert(view.bounds, to: root)
        return CGRect(x: rect.minX - root.bounds.minX,
            y: root.isFlipped ? rect.minY - root.bounds.minY : root.bounds.maxY - rect.maxY,
            width: rect.width, height: rect.height)
    }
    final class Probe: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}

struct NativeControlAnchorMount: NSViewRepresentable {
    let anchor: NativeControlAnchor
    func makeNSView(context: Context) -> NativeControlAnchor.Probe {
        let view = NativeControlAnchor.Probe(); anchor.view = view; return view
    }
    func updateNSView(_ view: NativeControlAnchor.Probe, context: Context) { anchor.view = view }
}

enum RecipientMenuGeometry {
    static func origin(anchor: CGRect, windowWidth: CGFloat, height: CGFloat) -> CGPoint {
        CGPoint(x: min(anchor.minX, windowWidth - 260), y: anchor.minY - 6 - height)
    }
}
