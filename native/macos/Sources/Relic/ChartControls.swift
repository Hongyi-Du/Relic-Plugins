import SwiftUI
import RelicCore

struct OrganizationBadge: View {
    let node: Node
    var body: some View {
        OrganizationAvatar(node: node, desaturateEnded: false)
    }
}

struct ChartChip: View {
    let text: String
    var tone = ""
    var weight = 400
    @State private var identity = "relic-chip/chart/" + UUID().uuidString
    var body: some View {
        ReferenceLabel(text, size: 10.5, weight: weight, color: tone == "sec" ? RelicStyle.violet : tone == "warn" ? RelicStyle.amber : RelicStyle.secondary, owner: identity)
            .padding(.horizontal, 6).frame(height: 20)
            .modifier(RecordedSurface(background: tone == "sec" ? RelicStyle.violetSoft : tone == "warn" ? RelicStyle.amberSoft : RelicStyle.hover, radius: 10, kind: "chip", owner: identity))
            .accessibilityElement(children: .contain).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}

struct ChartLegend: View {
    @EnvironmentObject var m: Model
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { symbols; Spacer(minLength: 0); hint }
            VStack(alignment: .trailing, spacing: 6) { HStack(spacing: 16) { symbols }; hint }
        }.padding(.horizontal, 16).padding(.vertical, 8).padding(.bottom, 1).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card"))
    }
    private var hint: some View { ReferenceLabel(m.t("chart.pan_hint"), size: 12, color: RelicStyle.faint).fixedSize() }
    @ViewBuilder private var symbols: some View {
        item("org.kind_formal", kind: "")
        item("org.kind_subgroup", kind: "sub")
        item("org.cabinet_chip", kind: "cab")
        item("chart.legend_ended", kind: "ended")
        item("chart.legend_shared", kind: "link")
    }
    private func item(_ key: String, kind: String) -> some View {
        HStack(spacing: 6) {
            if kind == "link" {
                Color.clear.frame(width: 18, height: 1)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.violet,
                        edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "divider", borderDash: [3,3]))
            } else {
                Color.clear.frame(width: 18, height: 12).modifier(RecordedSurface(background: kind == "cab" ? RelicStyle.violetSoft : kind == "ended" ? RelicStyle.hover : RelicStyle.card, border: kind == "cab" ? RelicStyle.violet : kind == "ended" ? RelicStyle.faint : RelicStyle.muted, borderWidth: 1, radius: 4, kind: "card", borderDash: kind == "sub" ? [3,3] : []))
            }
            ReferenceLabel(m.t(key), size: 12, color: RelicStyle.muted).fixedSize()
        }.fixedSize()
    }
}
