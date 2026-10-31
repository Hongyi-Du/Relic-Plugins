import SwiftUI
import RelicCore

struct MemberTag: View {
    let text: String
    let color: Color
    let background: Color
    @State private var identity = "relic-badge/" + UUID().uuidString
    var body: some View {
        ReferenceLabel(text, size: 10.5, weight: 600, color: color, lineHeight: 18, owner: identity, truncates: false).fixedSize().padding(.horizontal, 6).frame(height: 18)
            .modifier(RecordedSurface(background: background, radius: 5, kind: "badge", owner: identity))
            .accessibilityElement(children: .ignore).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}

struct MemberNameInput: View {
    @EnvironmentObject var m: Model
    let placeholder: String
    @Binding var text: String
    let save: () -> Void
    let cancel: () -> Void
    @State private var focused = false
    private let identity = "relic-input/member-rename"
    var body: some View {
        MemberRenameField(placeholder: placeholder, identifier: identity, hint: m.t("card.rename_hint"), text: $text, focused: $focused, save: save, cancel: cancel)
            .frame(width: 195, height: 32.4)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 8, owner: identity,
                outline: focused ? SurfaceOutline(width: 2, color: RelicStyle.accent.opacity(0.6), dash: [], offset: 1) : nil))
            .overlay(alignment: .trailing) { VoiceButton(text: $text).padding(.trailing, 4) }
    }
}
