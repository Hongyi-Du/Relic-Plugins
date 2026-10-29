import SwiftUI
import RelicCore

struct ConversationBanner: View {
    @EnvironmentObject var m: Model
    private var amber: Bool {
        let card = m.selectedMember
        if card["embedded"].flag { return false }
        let surface = card["config"]["surface"].text.isEmpty ? card["surface"].text : card["config"]["surface"].text
        return card["surface"].text == "subagent" || !Capabilities.automatic(m.platform, harness: card["harness"].text, surface: surface) || card["state"].text == "vacant"
    }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            ReferenceIcon(name: "info", size: 15, color: RelicStyle.secondary)
            ReferenceLabel(m.banner(m.selectedMember), size: 12.5, color: RelicStyle.secondary, lineHeight: 20, lines: 0).frame(maxWidth: .infinity, alignment: .leading)
        }.padding(.horizontal, 13).padding(.vertical, 9)
            .modifier(RecordedSurface(background: amber ? RelicStyle.amberSoft : RelicStyle.sidebar, border: amber ? RelicStyle.amber.opacity(0.3) : RelicStyle.line, borderWidth: 1, radius: 10, kind: "card"))
            .frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 10)
    }
}
