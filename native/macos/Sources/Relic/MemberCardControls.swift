import SwiftUI
import RelicCore

struct MemberTag: View {
    let text: String
    let color: Color
    let background: Color
    @State private var identity = "relic-badge/" + UUID().uuidString
    var body: some View {
        ReferenceLabel(text, size: 10.5, weight: 600, color: color, lineHeight: 18, owner: identity).padding(.horizontal, 6).frame(height: 18)
            .modifier(RecordedSurface(background: background, radius: 5, kind: "badge", owner: identity))
            .accessibilityElement(children: .ignore).accessibilityLabel(text).accessibilityIdentifier(identity)
    }
}

struct MemberNameInput: View {
    @EnvironmentObject var m: Model
    let placeholder: String
    @Binding var text: String
    let save: () -> Void
    let cancel: () -> Void
    @FocusState private var focused: Bool
    private let identity = "relic-input/member-rename"
    var body: some View {
        TextField(placeholder, text: $text).textFieldStyle(.plain).font(RelicStyle.font(14, weight: 400))
            .focused($focused).onSubmit(save)
            .onKeyPress(.escape) { cancel(); return .handled }
            .onChange(of: text) { _, value in text = ReferenceText.inputPrefix(value, utf16Limit: 40) }
            .padding(.leading, 9).padding(.trailing, 35).frame(height: 32.4)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 8, owner: identity))
            .overlay {
                if focused { RoundedRectangle(cornerRadius: 11).strokeBorder(RelicStyle.accent.opacity(0.6), lineWidth: 2).padding(-3).allowsHitTesting(false) }
            }
            .overlay(alignment: .trailing) { VoiceButton(text: $text).padding(.trailing, 4) }
            .accessibilityIdentifier(identity).help(m.t("card.rename_hint"))
            .task { focused = true }
    }
}
