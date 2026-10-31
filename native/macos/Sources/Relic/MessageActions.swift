import AppKit
import SwiftUI
import RelicCore
import RelicAX

struct MessageActionButton: View {
    let title: String
    let hint: String
    let icon: String
    var controlID = ""
    let action: () -> Void
    @State private var unique = UUID().uuidString
    @State private var hovered = false
    private var identity: String { (title.isEmpty ? "relic-icon-button/" : "relic-text-button/") + (controlID.isEmpty ? unique : controlID) }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                ReferenceIcon(name: icon, size: 14, color: hovered ? RelicStyle.ink : RelicStyle.secondary, owner: identity)
                if !title.isEmpty { ReferenceLabel(title, size: 12, color: hovered ? RelicStyle.ink : RelicStyle.secondary, owner: identity) }
            }.padding(.horizontal, 8).frame(height: 26).contentShape(Rectangle())
                .modifier(RecordedSurface(background: hovered ? RelicStyle.hover : .clear, radius: 6, owner: identity, hovered: hovered))
        }.buttonStyle(.plain).onHover { hovered = $0 }.help(hint)
            .accessibilityLabel(title.isEmpty ? hint : title).accessibilityIdentifier(identity)
    }
}

/// Mount for message geometry and the actual VoiceOver navigation order. It
/// has no paint or accessible element and is present during normal use.
struct MessageInteractionAnchor: NSViewRepresentable {
    let messageID: String
    var avatarNavigationID: String? = nil
    var metadataNavigationID: String? = nil
    static let live = NSHashTable<AnchorView>.weakObjects()
    func makeNSView(context: Context) -> AnchorView { let view = AnchorView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: AnchorView, context: Context) {
        view.messageID = messageID
        view.avatarNavigationID = avatarNavigationID; view.metadataNavigationID = metadataNavigationID
        view.scheduleNavigationOrder()
    }
    static func visibleBounds(messageID: String) -> [NSRect] {
        live.allObjects.filter { $0.messageID == messageID && $0.window?.isVisible == true }.compactMap { view in
            guard let rect = NativeVisibility.screenClip(view), !rect.isNull, !rect.isEmpty else { return nil }; return rect
        }
    }
    static func revealAction(_ screen: NSRect, messageID: String, window: NSWindow) throws -> [String: Any] {
        let matches = live.allObjects.filter { $0.messageID == messageID && $0.window === window && NativeVisibility.screenClip($0) != nil }
        guard matches.count == 1, let anchor = matches.first, let scroll = anchor.enclosingScrollView,
              let document = scroll.documentView else { throw RelicError.message("Message action lost its actual native scroll container") }
        let clip = scroll.contentView, before = clip.bounds
        let requested = document.convert(window.convertFromScreen(screen), from: nil)
        let moved = document.scrollToVisible(requested)
        scroll.reflectScrolledClipView(clip)
        return ["provider": "NSView.scrollToVisible on the actual message document", "requested_screen_bounds": ElementCapture.box(screen),
            "requested_document_bounds": ElementCapture.box(requested), "document_identity": String(describing: ObjectIdentifier(document)),
            "clip_before": ElementCapture.box(before), "clip_after": ElementCapture.box(clip.bounds), "scrolled": moved]
    }
    final class AnchorView: NSView {
        var messageID = ""
        var avatarNavigationID: String?, metadataNavigationID: String?
        private var navigationPending = false
        private(set) var navigationAttempts = 0
        private(set) var navigationSucceeded: Bool?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); scheduleNavigationOrder() }
        override func viewDidMoveToSuperview() { super.viewDidMoveToSuperview(); scheduleNavigationOrder() }
        override func layout() { super.layout(); scheduleNavigationOrder() }
        func scheduleNavigationOrder(retry: Int = 0) {
            guard !navigationPending, avatarNavigationID != nil else { return }
            navigationPending = true
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }; self.navigationPending = false
                guard self.window != nil, let scroll = self.enclosingScrollView,
                      let avatar = self.avatarNavigationID, let metadata = self.metadataNavigationID else { return }
                // Outgoing avatars are visually on the right, but VoiceOver
                // should introduce the author before the message metadata.
                // Move the existing native object; never create a proxy or
                // replace the scroll area's accessible child inventory.
                self.navigationAttempts += 1
                self.navigationSucceeded = RelicAXPlaceChildBefore(scroll, avatar, metadata)
                // SwiftUI may materialize its virtual children on the first AX
                // query after layout. Give that real tree another main-loop
                // turn; never retry indefinitely or reorder capture output.
                if self.navigationSucceeded == false && retry < 3 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(16)) { [weak self] in
                        self?.scheduleNavigationOrder(retry: retry + 1)
                    }
                }
            }
        }
    }
}
