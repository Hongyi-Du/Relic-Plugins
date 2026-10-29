import SwiftUI
import RelicCore

struct OrganizationBadge: View {
    let node: Node
    var body: some View {
        ReferenceLabel(String(node["name"].text.trimmingCharacters(in: .whitespaces).prefix(1)).uppercased(), size: 11, weight: 700, color: RelicStyle.avatar(node["id"].text, background: false, dark: false), alignment: .center)
            .frame(width: 22, height: 22)
            .modifier(RecordedSurface(background: RelicStyle.avatar(node["id"].text, background: true, dark: false), border: RelicStyle.avatar(node["id"].text, background: false, dark: false), borderWidth: node["kind"].text == "subgroup" ? 1.5 : 0, radius: 6, kind: "avatar", borderDash: node["kind"].text == "subgroup" ? [3,3] : []))
            .overlay { if node["cabinet"].flag { RoundedRectangle(cornerRadius: 9.5).strokeBorder(RelicStyle.violet, lineWidth: 1.5).padding(-3.5); RoundedRectangle(cornerRadius: 8).strokeBorder(RelicStyle.card, lineWidth: 2).padding(-2) } }
    }
}

struct ChartChip: View {
    let text: String
    var tone = ""
    var body: some View {
        ReferenceLabel(text, size: 10.5, color: tone == "sec" ? RelicStyle.violet : tone == "warn" ? RelicStyle.amber : RelicStyle.secondary)
            .padding(.horizontal, 6).frame(height: 20)
            .modifier(RecordedSurface(background: tone == "sec" ? RelicStyle.violetSoft : tone == "warn" ? RelicStyle.amberSoft : RelicStyle.hover, radius: 10, kind: "chip"))
    }
}

struct ChartLegend: View {
    @EnvironmentObject var m: Model
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { symbols; Spacer(minLength: 0); hint }
            VStack(alignment: .trailing, spacing: 6) { HStack(spacing: 16) { symbols }; hint }
        }.padding(.horizontal, 16).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
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
                Path { p in p.move(to: CGPoint(x: 0, y: 1)); p.addLine(to: CGPoint(x: 18, y: 1)) }.stroke(RelicStyle.violet, style: StrokeStyle(lineWidth: 1.5, dash: [3,3])).frame(width: 18, height: 2)
            } else {
                Color.clear.frame(width: 18, height: 12).modifier(RecordedSurface(background: kind == "cab" ? RelicStyle.violetSoft : kind == "ended" ? RelicStyle.hover : RelicStyle.card, border: kind == "cab" ? RelicStyle.violet : kind == "ended" ? RelicStyle.faint : RelicStyle.muted, borderWidth: 1.5, radius: 4, kind: "badge", borderDash: kind == "sub" ? [3,3] : []))
            }
            ReferenceLabel(m.t(key), size: 12, color: RelicStyle.muted).fixedSize()
        }.fixedSize()
    }
}
