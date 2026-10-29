import SwiftUI
import RelicCore

struct ChartView: View {
    @EnvironmentObject var m: Model
    @State private var chart = Node()
    @State private var zoom: CGFloat = 1, lastZoom: CGFloat = 1
    @State private var offset = CGSize.zero, baseOffset = CGSize.zero
    private var nodes: [Node] { chart["orgs"].rows }
    private func point(_ node: Node, _ index: Int) -> CGPoint {
        var parent = node["parent"].text, visited: Set<String> = [], depth = 0
        while !parent.isEmpty && !visited.contains(parent) {
            visited.insert(parent); depth += 1; parent = nodes.first { $0["id"].text == parent }?["parent"].text ?? ""
        }
        return CGPoint(x: depth * 240 + 120, y: index * 110 + 65)
    }
    var body: some View {
        VStack(alignment: .leading) {
            Text(m.t("chart.title")).font(.title2)
            HStack {
                Button(m.t("chart.zoom_in")) { zoom = min(3, zoom * 1.2); lastZoom = zoom }
                Button(m.t("chart.zoom_out")) { zoom = max(0.2, zoom / 1.2); lastZoom = zoom }
                Button(m.t("chart.fit")) { zoom = min(1, 480 / CGFloat(max(1, nodes.count) * 110)); lastZoom = zoom; offset = .zero; baseOffset = .zero }
            }
            GeometryReader { geometry in
                ZStack(alignment: .topLeading) {
                    Color.clear.contentShape(Rectangle())
                    ZStack(alignment: .topLeading) {
                        Canvas { context, _ in
                            for (index, node) in nodes.enumerated() {
                                if let parentIndex = nodes.firstIndex(where: { $0["id"].text == node["parent"].text }) {
                                    var path = Path(); path.move(to: point(nodes[parentIndex], parentIndex)); path.addLine(to: point(node, index))
                                    context.stroke(path, with: .color(.secondary), lineWidth: 2)
                                }
                            }
                        }
                        ForEach(Array(nodes.enumerated()), id: \.offset) { index, node in
                            Button { m.run { try await m.select(node["id"].text); m.sheet = nil } } label: {
                                VStack(alignment: .leading) {
                                    Text(node["name"].text).font(.headline)
                                    Text(node["leader_display"].text).font(.caption)
                                    Text(m.t("chart.decisions", ["n": node["decisions"].text])).font(.caption)
                                }.frame(width: 190, height: 70).padding(8)
                            }.buttonStyle(.bordered).position(point(node, index))
                        }
                    }.frame(width: max(800, CGFloat(nodes.count) * 240), height: max(500, CGFloat(nodes.count) * 110))
                        .scaleEffect(zoom, anchor: .topLeading).offset(offset)
                }.clipped()
                    .gesture(DragGesture().onChanged { offset = CGSize(width: baseOffset.width + $0.translation.width, height: baseOffset.height + $0.translation.height) }.onEnded { _ in baseOffset = offset })
                    .simultaneousGesture(MagnifyGesture().onChanged { zoom = min(3, max(0.2, lastZoom * $0.magnification)) }.onEnded { _ in lastZoom = zoom })
            }.frame(width: 820, height: 500)
            ScrollView {
                Rows(chart["shared"].rows) { shared in Text(m.t("chart.legend_shared") + " · " + shared["seats"].rows.map { $0["org"].text + "/" + $0["member"].text }.joined(separator: " ↔ ")) }
            }.frame(maxHeight: 90)
        }.task { m.run { chart = try await m.get("/api/orgchart") } }
    }
}
