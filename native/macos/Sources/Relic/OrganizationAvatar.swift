import SwiftUI
import RelicCore

struct OrganizationAvatar: View {
    let node: Node
    @State private var identity = "relic-avatar/" + UUID().uuidString
    private var foreground: Color { RelicStyle.avatar(node["id"].text, background: false, dark: false) }
    static func initial(for node: Node) -> String { String(node["name"].text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(1)).uppercased() }
    private var initial: String { Self.initial(for: node) }
    private var subgroup: Bool { node["kind"].text == "subgroup" }
    private var ended: Bool { !node["status"].text.isEmpty && node["status"].text != "active" }
    var body: some View {
        ReferenceLabel(initial, size: 11, weight: 700, color: foreground, lines: 0, alignment: .center, owner: identity)
            .frame(width: 22, height: 22)
            .modifier(RecordedSurface(background: RelicStyle.avatar(node["id"].text, background: true, dark: false),
                radius: 6, kind: "avatar", owner: identity,
                rings: node["cabinet"].flag ? [SurfaceRing(width: 2, color: RelicStyle.card), SurfaceRing(width: 3.5, color: RelicStyle.violet)] : [],
                outline: subgroup ? SurfaceOutline(width: 1.5, color: foreground, dash: [3, 3]) : nil))
            .saturation(ended ? 0 : 1)
            .accessibilityElement(children: .contain).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}

struct SidebarGroupAvatar: View {
    @State private var identity = "relic-avatar/" + UUID().uuidString
    var body: some View {
        ReferenceIcon(name: "hash", size: 14, owner: identity).frame(width: 28, height: 28)
            .modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "avatar", owner: identity))
            .accessibilityElement(children: .ignore).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}
