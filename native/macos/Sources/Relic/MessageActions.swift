import AppKit
import SwiftUI

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

/// Read-only geometry of the actual message for CI hover/copy actions. It has
/// no paint or accessibility element and is also present during normal use.
struct MessageInteractionAnchor: NSViewRepresentable {
    let messageID: String
    static let live = NSHashTable<AnchorView>.weakObjects()
    func makeNSView(context: Context) -> AnchorView { let view = AnchorView(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: AnchorView, context: Context) { view.messageID = messageID }
    static func visibleBounds(messageID: String) -> [NSRect] {
        live.allObjects.filter { $0.messageID == messageID && $0.window?.isVisible == true }.compactMap { view in
            guard let rect = NativeVisibility.screenClip(view), !rect.isNull, !rect.isEmpty else { return nil }; return rect
        }
    }
    final class AnchorView: NSView {
        var messageID = ""
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}
