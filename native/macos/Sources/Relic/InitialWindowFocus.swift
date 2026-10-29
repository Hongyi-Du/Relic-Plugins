import AppKit
import SwiftUI

// Opening the app leaves the canvas focused. Editing begins after the user
// chooses an input; AppKit must not automatically focus the chat composer.
struct InitialWindowFocus: NSViewRepresentable {
    func makeNSView(context: Context) -> CanvasFocusView { CanvasFocusView() }
    func updateNSView(_ view: CanvasFocusView, context: Context) {}

    final class CanvasFocusView: NSView {
        private var initialized = false
        override var acceptsFirstResponder: Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard !initialized, let window else { return }
            initialized = true
            window.initialFirstResponder = self
            DispatchQueue.main.async { [weak self, weak window] in
                guard let self, let window, self.window === window else { return }
                window.makeFirstResponder(self)
            }
        }
    }
}
