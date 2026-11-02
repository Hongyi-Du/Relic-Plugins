import AppKit
import SwiftUI

/// The focusable conversation viewport scrolls its actual native clip view.
/// Editing controls retain their own key handling; no global event monitor is
/// installed and no key is synthesized into a different responder.
@MainActor final class ConversationKeyboard {
    static let identifier = "relic-conversation-scroll"
    weak var scroll: NSScrollView?
    var enabled = true
    var scrollToEdge: ((Bool) -> Void)?
    var didUserScroll: ((Bool) -> Void)?
    var positionObservation: (() -> [String: Any])?
    struct Geometry: Equatable {
        let height: CGFloat, viewportHeight: CGFloat, width: CGFloat, topGap: CGFloat
    }
    var geometryChanged: ((Geometry) -> Void)?
    var observedHeight: CGFloat = 0
    private var geometryQueued = false
    private var lastGeometry: Geometry?
    private var scrollObservers: [NSObjectProtocol] = []
    private let mounts = NSHashTable<NSView>.weakObjects()
    private var disclosureOrigin: NSPoint?
    private var disclosureHeight: CGFloat = 0
    private var disclosureGeneration = 0

    /// Each visible List cell can resolve its enclosing viewport. Its controller
    /// owns one observer set, so recycling a cell never detaches the live list
    /// and hundreds of history rows never create hundreds of scroll listeners.
    func attach(_ current: NSScrollView, owner: NSView) {
        if scroll === current, !scrollObservers.isEmpty { mounts.add(owner); return }
        for observer in scrollObservers { NotificationCenter.default.removeObserver(observer) }
        mounts.removeAllObjects(); mounts.add(owner)
        scrollObservers = []; scroll = current; lastGeometry = nil
        current.contentView.postsBoundsChangedNotifications = true
        current.documentView?.postsFrameChangedNotifications = true
        for (name, object) in [(NSView.boundsDidChangeNotification, current.contentView as NSView?),
                               (NSView.frameDidChangeNotification, current.documentView)] {
            guard let object else { continue }
            scrollObservers.append(NotificationCenter.default.addObserver(forName: name, object: object, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.queueGeometry() }
            })
        }
        scrollObservers.append(NotificationCenter.default.addObserver(forName: NSScrollView.didLiveScrollNotification, object: current, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.userScrolled() }
        })
        queueGeometry()
    }
    func detach(_ owner: NSView) {
        mounts.remove(owner)
        guard mounts.allObjects.isEmpty else { return }
        for observer in scrollObservers { NotificationCenter.default.removeObserver(observer) }
        scrollObservers = []; scroll = nil; lastGeometry = nil
    }
    private func queueGeometry() {
        guard !geometryQueued else { return }; geometryQueued = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }; self.geometryQueued = false
            guard let scroll = self.scroll, let document = scroll.documentView else { return }
            let clip = scroll.contentView.bounds
            let top = document.isFlipped ? clip.minY - document.bounds.minY : document.bounds.maxY - clip.maxY
            let value = Geometry(height: document.bounds.height, viewportHeight: clip.height, width: clip.width, topGap: max(0, top))
            guard value != self.lastGeometry else { return }
            self.lastGeometry = value; self.geometryChanged?(value)
        }
    }
    deinit { for observer in scrollObservers { NotificationCenter.default.removeObserver(observer) } }

    func userScrolled() {
        guard enabled, let scroll, let document = scroll.documentView else { return }
        let clip = scroll.contentView.bounds
        let gap = document.isFlipped ? document.bounds.maxY - clip.maxY : clip.minY - document.bounds.minY
        didUserScroll?(gap < 120)
    }

    /// ScrollViewReader realizes the actual last row before this completion.
    /// A lazy stack can retain a small extent beyond that row after history
    /// measurement. Finish against AppKit's current range only while the real
    /// target intersects the viewport, never by jumping to an unrealized estimate.
    /// Its lower edge may still be clipped after the preceding long row settles.
    @discardableResult func finishRealizedEnd(bottom: CGFloat, height: CGFloat, viewportHeight: CGFloat) -> Bool {
        guard enabled, bottom.isFinite, height.isFinite, viewportHeight.isFinite,
              height > 0, viewportHeight > 0, bottom > 0, bottom - height < viewportHeight,
              let scroll, let document = scroll.documentView else { return false }
        let clip = scroll.contentView, bounds = clip.bounds
        let gap = document.isFlipped ? document.bounds.maxY - bounds.maxY : bounds.minY - document.bounds.minY
        guard gap > 1 else { return true }
        // The completion must keep the realized target in view. A large stale
        // estimate still belongs to the framework's row-positioning path.
        guard gap < bottom else { return false }
        var target = bounds
        target.origin.y = document.isFlipped ? document.bounds.maxY - bounds.height : document.bounds.minY
        clip.scroll(to: clip.constrainBoundsRect(target).origin)
        scroll.reflectScrolledClipView(clip)
        return true
    }

    func preserveDisclosurePosition() {
        discardDisclosurePosition()
        guard let scroll, let document = scroll.documentView else { return }
        disclosureOrigin = scroll.contentView.bounds.origin
        disclosureHeight = document.frame.height
    }

    func discardDisclosurePosition() {
        disclosureGeneration += 1; disclosureOrigin = nil
    }

    func finishDisclosureLayout() {
        guard let origin = disclosureOrigin, let scroll, let document = scroll.documentView,
              document.frame.height != disclosureHeight else { return }
        let generation = disclosureGeneration
        // SwiftUI can preserve the bottom edge while laying out a disclosure.
        // Restore the real pre-click reading offset after that layout transaction,
        // once only. This is production interaction behavior, not capture setup.
        DispatchQueue.main.async { [weak self, weak scroll] in
            guard let self, let scroll, self.scroll === scroll,
                  self.disclosureGeneration == generation, self.disclosureOrigin != nil else { return }
            self.discardDisclosurePosition()
            let clip = scroll.contentView
            var target = clip.bounds; target.origin = origin
            clip.scroll(to: clip.constrainBoundsRect(target).origin)
            scroll.reflectScrolledClipView(clip)
        }
    }

    func handle(_ key: KeyEquivalent, modifiers: EventModifiers) -> KeyPress.Result {
        guard enabled, modifiers.intersection([.command, .control, .option]).isEmpty,
              let scroll, let document = scroll.documentView else { return .ignored }
        if let scrollToEdge, key == .home || key == .end {
            discardDisclosurePosition(); scrollToEdge(key == .home); return .handled
        }
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
        discardDisclosurePosition()
        let constrained = clip.constrainBoundsRect(target)
        clip.scroll(to: constrained.origin)
        scroll.reflectScrolledClipView(clip)
        userScrolled()
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
    static func controller(for scroll: NSScrollView) -> ConversationKeyboard? {
        live.allObjects.first { $0.attachedScroll === scroll && $0.window === scroll.window }?.keyboard
    }
    static func bottomGap(in window: NSWindow) -> CGFloat? {
        edgeGap(in: window, atTop: false)
    }
    static func position(in window: NSWindow) -> [String: Any] {
        live.allObjects.first { $0.window === window }?.keyboard?.positionObservation?() ?? [:]
    }
    static func edgeGap(in window: NSWindow, atTop: Bool) -> CGFloat? {
        guard let scroll = live.allObjects.first(where: { $0.window === window })?.attachedScroll,
              let document = scroll.documentView else { return nil }
        let clip = scroll.contentView.bounds
        let top = max(0, clip.minY - document.bounds.minY)
        let bottom = max(0, document.bounds.maxY - clip.maxY)
        return atTop == document.isFlipped ? top : bottom
    }
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
            ["source": "mounted production scrollDisabled binding, actual scroll AX focus getter and keyboard controller",
             "mount_identity": String(describing: ObjectIdentifier(self)),
             "scroll_identity": attachedScroll.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "first_responder_identity": window?.firstResponder.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
             "enabled": enabled,
             // SwiftUI's surrounding focus binding can stay true when a child
             // disclosure owns focus. Preserve that binding separately; the
             // exact scroll element has its own native AX focus observation.
             "focus_scope_binding": focused,
             "focused": attachedScroll.map { $0.isAccessibilityFocused() } as Any? ?? NSNull(),
             "keyboard_enabled": keyboard?.enabled as Any? ?? NSNull(),
             "controller_bound": keyboard?.scroll != nil && keyboard?.scroll === attachedScroll]
        }
        func resolveScroll() {
            guard window != nil, let current = enclosingScrollView else {
                keyboard?.detach(self); attachedScroll = nil; return
            }
            attachedScroll = current; keyboard?.attach(current, owner: self)
            keyboard?.enabled = enabled
            if current.accessibilityIdentifier() != ConversationKeyboard.identifier { current.setAccessibilityIdentifier(ConversationKeyboard.identifier) }
            if current.isAccessibilityEnabled() != enabled { current.setAccessibilityEnabled(enabled) }
        }
    }
}
