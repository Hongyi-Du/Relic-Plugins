import AppKit
import SwiftUI

/// Names the actual scroll viewport that contains this mount. It creates no
/// replacement AX tree and draws nothing; native scroll actions and descendants
/// stay owned by the same NSScrollView.
struct NativeScrollOwner: NSViewRepresentable {
    let identifier: String
    let title: String
    func makeNSView(context: Context) -> Mount { Mount() }
    func updateNSView(_ view: Mount, context: Context) {
        view.update(identifier: identifier, title: title)
    }
    final class Mount: NSView {
        private var ownerIdentifier = "", ownerTitle = ""
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
            guard !ownerIdentifier.isEmpty, let scroll = enclosingScrollView else { owner = nil; return }
            owner = scroll
            scroll.setAccessibilityIdentifier(ownerIdentifier)
            scroll.setAccessibilityLabel(ownerTitle)
        }
    }
}
