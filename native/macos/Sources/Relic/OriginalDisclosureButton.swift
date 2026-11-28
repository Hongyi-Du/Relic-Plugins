import SwiftUI

// The reference summary owns its title, with a separate ::before marker.
// Keep those two painted elements distinct while preserving one real button.
struct OriginalDisclosureButton: View {
    let title: String
    let expanded: Bool
    let action: () -> Void
    @State private var identity = "relic-text-button/original/" + UUID().uuidString
    private var marker: String { expanded ? "▾ " : "▸ " }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 0) {
                ReferenceLabel(marker, size: 11.5, color: RelicStyle.muted, lines: 0,
                    accessibleName: "", stateOwner: identity).fixedSize()
                ReferenceLabel(title, size: 11.5, color: RelicStyle.muted, lines: 0, owner: identity).fixedSize()
            }.padding(.horizontal, 2)
                .modifier(RecordedSurface(background: .clear, owner: identity, expanded: expanded))
                .environment(\.nativeElementParent, identity)
        }.buttonStyle(.plain).accessibilityIdentifier(identity).accessibilityLabel(marker + title)
    }
}
