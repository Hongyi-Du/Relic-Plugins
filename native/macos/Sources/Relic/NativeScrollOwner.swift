import AppKit
import SwiftUI

/// Names the actual scroll viewport that contains this mount. It creates no
/// replacement AX tree and draws nothing; native scroll actions and descendants
/// stay owned by the same NSScrollView.
struct NativeScrollOwner: NSViewRepresentable {
    let identifier: String
    let title: String
    /// The scroll views named so far, so CI navigation finds one without
    /// walking every view in the window on the main thread.
    @MainActor private static let named = NSMapTable<NSString, NSScrollView>.strongToWeakObjects()
    @MainActor static func scroll(_ identifier: String, in window: NSWindow) -> NSScrollView? {
        guard let scroll = named.object(forKey: identifier as NSString), scroll.window === window,
              scroll.accessibilityIdentifier() == identifier else { return nil }
        return scroll
    }
    func makeNSView(context: Context) -> Mount { Mount() }
    func updateNSView(_ view: Mount, context: Context) {
        view.update(identifier: identifier, title: title)
    }
    final class Mount: NSView {
        private var ownerIdentifier = "", ownerTitle = ""
        private var binding = false
        private(set) weak var owner: NSScrollView?
        override func isAccessibilityElement() -> Bool { false }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); bind() }
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); bind() }
        override func layout() { super.layout(); bind() }
        func update(identifier: String, title: String) {
            ownerIdentifier = identifier; ownerTitle = title
            bind(); needsLayout = true
        }
        private func bind() {
            guard !binding else { return }
            guard !ownerIdentifier.isEmpty, let scroll = enclosingScrollView else { owner = nil; return }
            binding = true; defer { binding = false }
            owner = scroll
            NativeScrollOwner.named.setObject(scroll, forKey: ownerIdentifier as NSString)
            if scroll.accessibilityIdentifier() != ownerIdentifier { scroll.setAccessibilityIdentifier(ownerIdentifier) }
            if scroll.accessibilityLabel() != ownerTitle { scroll.setAccessibilityLabel(ownerTitle) }
            ScrollAppearance.apply(to: scroll)
        }
    }
}
