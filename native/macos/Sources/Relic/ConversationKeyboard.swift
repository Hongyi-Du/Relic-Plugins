import AppKit
import SwiftUI

/// The focusable conversation viewport scrolls its actual native clip view.
/// Editing controls retain their own key handling; no global event monitor is
/// installed and no key is synthesized into a different responder.
@MainActor final class ConversationKeyboard {
    static let identifier = "relic-conversation-scroll"
    weak var scroll: NSScrollView?

    func handle(_ key: KeyEquivalent, modifiers: EventModifiers) -> KeyPress.Result {
        guard modifiers.intersection([.command, .control, .option]).isEmpty,
              let scroll, let document = scroll.documentView else { return .ignored }
        let clip = scroll.contentView
        let direction: CGFloat = document.isFlipped ? 1 : -1
        let page = max(0, clip.bounds.height - scroll.verticalPageScroll)
        var target = clip.bounds
        switch key {
        case .upArrow: target.origin.y -= direction * scroll.verticalLineScroll
        case .downArrow: target.origin.y += direction * scroll.verticalLineScroll
        case .pageUp: target.origin.y -= direction * page
        case .pageDown: target.origin.y += direction * page
        case .space: target.origin.y += direction * page * (modifiers.contains(.shift) ? -1 : 1)
        case .home: target.origin.y = document.isFlipped ? document.frame.minY : document.frame.maxY - clip.bounds.height
        case .end: target.origin.y = document.isFlipped ? document.frame.maxY - clip.bounds.height : document.frame.minY
        default: return .ignored
        }
        let constrained = clip.constrainBoundsRect(target)
        clip.scroll(to: constrained.origin)
        scroll.reflectScrolledClipView(clip)
        return .handled
    }
}

/// Mounted inside the conversation document, this observer resolves only its
/// enclosing native scroll view. It adds no paint or accessibility element.
struct ConversationKeyboardMount: NSViewRepresentable {
    let keyboard: ConversationKeyboard
    func makeNSView(context: Context) -> Mount { Mount(keyboard: keyboard) }
    func updateNSView(_ view: Mount, context: Context) { view.resolveScroll() }

    final class Mount: NSView {
        private weak var keyboard: ConversationKeyboard?
        private weak var attachedScroll: NSScrollView?
        init(keyboard: ConversationKeyboard) { self.keyboard = keyboard; super.init(frame: .zero) }
        required init?(coder: NSCoder) { return nil }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); resolveScroll() }
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); resolveScroll() }
        override func layout() { super.layout(); resolveScroll() }
        func resolveScroll() {
            guard window != nil, let current = enclosingScrollView else {
                if keyboard?.scroll === attachedScroll { keyboard?.scroll = nil }
                attachedScroll = nil; return
            }
            attachedScroll = current; keyboard?.scroll = current
            current.setAccessibilityIdentifier(ConversationKeyboard.identifier)
        }
    }
}
