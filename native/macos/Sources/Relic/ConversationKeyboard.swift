import AppKit
import SwiftUI

/// The focusable conversation viewport scrolls its actual native clip view.
/// Editing controls retain their own key handling; no global event monitor is
/// installed and no key is synthesized into a different responder.
@MainActor final class ConversationKeyboard {
    static let identifier = "relic-conversation-scroll"
    weak var scroll: NSScrollView?
    var enabled = true

    func handle(_ key: KeyEquivalent, modifiers: EventModifiers) -> KeyPress.Result {
        guard enabled, modifiers.intersection([.command, .control, .option]).isEmpty,
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
    var enabled = true
    var focused = false
    private static let live = NSHashTable<Mount>.weakObjects()
    func makeNSView(context: Context) -> Mount {
        let view = Mount(keyboard: keyboard); Self.live.add(view)
        view.update(enabled: enabled, focused: focused); return view
    }
    func updateNSView(_ view: Mount, context: Context) { view.update(enabled: enabled, focused: focused) }
    static func observation(for scroll: NSScrollView) -> [String: Any]? {
        let owners = live.allObjects.filter { $0.attachedScroll === scroll && $0.window === scroll.window && $0.keyboard?.scroll === scroll }
        guard owners.count == 1, let view = owners.first, view.window != nil else { return nil }
        return view.observation()
    }

    final class Mount: NSView {
        fileprivate weak var keyboard: ConversationKeyboard?
        fileprivate weak var attachedScroll: NSScrollView?
        private var enabled = true, focused = false
        init(keyboard: ConversationKeyboard) { self.keyboard = keyboard; super.init(frame: .zero) }
        required init?(coder: NSCoder) { return nil }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); resolveScroll() }
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); resolveScroll() }
        override func layout() { super.layout(); resolveScroll() }
        func update(enabled: Bool, focused: Bool) {
            self.enabled = enabled; self.focused = focused; keyboard?.enabled = enabled; resolveScroll()
        }
        func observation() -> [String: Any] {
            ["source": "mounted production scrollDisabled/focusable/FocusState bindings and actual keyboard controller",
             "mount_identity": String(describing: ObjectIdentifier(self)),
             "scroll_identity": attachedScroll.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "first_responder_identity": window?.firstResponder.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "enabled": enabled, "focused": focused,
             "keyboard_enabled": keyboard?.enabled as Any? ?? NSNull(),
             "controller_bound": keyboard?.scroll != nil && keyboard?.scroll === attachedScroll]
        }
        func resolveScroll() {
            guard window != nil, let current = enclosingScrollView else {
                if keyboard?.scroll === attachedScroll { keyboard?.scroll = nil }
                attachedScroll = nil; return
            }
            attachedScroll = current; keyboard?.scroll = current
            keyboard?.enabled = enabled
            current.setAccessibilityIdentifier(ConversationKeyboard.identifier)
            current.setAccessibilityEnabled(enabled)
        }
    }
}
