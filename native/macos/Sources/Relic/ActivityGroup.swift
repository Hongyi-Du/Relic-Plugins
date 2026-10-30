import SwiftUI
import RelicCore

struct ActivityGroup: View {
    @EnvironmentObject var m: Model
    let item: Node
    @State private var expanded = false
    @State private var identity = "relic-row/activity-group/" + UUID().uuidString
    private var rows: [ToolActivity] { ToolActivity.pair(item["steps"].rows) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded.toggle() } label: {
                HStack(spacing: 8) {
                    ReferenceIcon(name: "chev", size: 13, color: RelicStyle.muted, owner: identity).rotationEffect(.degrees(expanded ? 90 : 0))
                    ReferenceLabel(m.t("step.actions", ["n": String(rows.count)]), size: 12.5, weight: 600, color: RelicStyle.secondary, owner: identity).fixedSize()
                    ReferenceLabel(ToolActivity.summary(rows), size: 12.5, color: RelicStyle.muted, owner: identity)
                    let failed = rows.filter(\.failed).count
                    if failed > 0 { OverviewChip(text: m.t("step.failed", ["n": String(failed)]), tone: "bad") }
                    Spacer(minLength: 0)
                    ReferenceLabel(m.clock(item["at"]), size: 12.5, color: RelicStyle.muted, owner: identity).fixedSize()
                }.padding(.horizontal, 10).padding(.vertical, 6).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: .clear, owner: identity, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity)
            if expanded {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in ActivityRow(row: row, member: item["member"].text) }
                }.padding(.vertical, 4).padding(.top, 1)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "card"))
            }
        }.padding(1).frame(maxWidth: 720, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.line, borderWidth: 1, radius: 10, kind: "card"))
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ActivityOutput: View {
    let text: String
    private var content: some View {
        SelectableText(value: AttributedString(text), pointSize: 11.5, lineHeight: 17.825, monospaced: true)
            .padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 7, kind: "code"))
    }
    var body: some View {
        ViewThatFits(in: .vertical) { content; ScrollView { content } }.frame(maxHeight: 360, alignment: .topLeading)
    }
}
