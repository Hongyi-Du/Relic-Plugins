import SwiftUI
import RelicCore
import AppKit

struct ChartView: View {
    @EnvironmentObject var m: Model
    @State private var chart = Node()
    @State private var zoom: CGFloat = 1
    @State private var lastZoom: CGFloat = 1
    @State private var offset = CGSize.zero
    @State private var baseOffset = CGSize.zero
    @State private var showEnded = true
    @State private var showShared = true
    @State private var hovered = ""
    @State private var autoFit = true
    @State private var draggedUntil = Date.distantPast
    @State private var viewport = CGSize(width: 760, height: 360)
    private var layout: OrganizationLayout { OrganizationLayout(chart["orgs"].rows.filter { showEnded || $0["status"].text == "active" }) }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(m.t("chart.title")).font(.title2)
            HStack {
                Button { zoomAt(zoom / 1.25) } label: { Image(systemName: "minus.magnifyingglass") }.help(m.t("chart.zoom_out")).keyboardShortcut("-", modifiers: [])
                Button(String(Int(zoom * 100)) + "%") { zoomAt(1) }.help(m.t("chart.zoom_actual"))
                Button { zoomAt(zoom * 1.25) } label: { Image(systemName: "plus.magnifyingglass") }.help(m.t("chart.zoom_in")).keyboardShortcut("=", modifiers: [])
                Button(m.t("chart.fit")) { autoFit = true; fit() }.keyboardShortcut("0", modifiers: [])
                Spacer(); Toggle(m.t("chart.show_closed"), isOn: $showEnded); Toggle(m.t("chart.show_links"), isOn: $showShared)
            }
            HStack {
                Label(m.t("org.kind_formal"), systemImage: "rectangle")
                Label(m.t("org.kind_subgroup"), systemImage: "rectangle.dashed")
                Label(m.t("org.cabinet_chip"), systemImage: "star.fill").foregroundStyle(.tint)
                Text(m.t("chart.legend_ended")).foregroundStyle(.secondary)
            }.font(RelicStyle.font(12, weight: 400))
            Text(m.t("chart.pan_hint")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(.secondary)
            let graph = layout
            ZStack(alignment: .topLeading) {
                Color.clear.contentShape(Rectangle())
                ZStack(alignment: .topLeading) {
                    Canvas { context, _ in
                        for (child, parent) in graph.parents {
                            guard let a = graph.centers[parent], let b = graph.centers[child] else { continue }
                            var path = Path(); let start = CGPoint(x: a.x, y: a.y + OrganizationLayout.card.height / 2), end = CGPoint(x: b.x, y: b.y - OrganizationLayout.card.height / 2)
                            path.move(to: start); path.addCurve(to: end, control1: CGPoint(x: a.x, y: (start.y + end.y) / 2), control2: CGPoint(x: b.x, y: (start.y + end.y) / 2))
                            context.stroke(path, with: .color(.secondary), lineWidth: 1.5)
                        }
                        if showShared {
                            for shared in chart["shared"].rows {
                                let seats = shared["seats"].rows.filter { graph.centers[$0["org"].text] != nil }
                                for first in seats.indices { for next in seats.indices where next > first && seats[first]["org"].text != seats[next]["org"].text {
                                    let a = graph.centers[seats[first]["org"].text]!, b = graph.centers[seats[next]["org"].text]!
                                    var path = Path(); let start = CGPoint(x: a.x + OrganizationLayout.card.width / 2, y: a.y), end = CGPoint(x: b.x + OrganizationLayout.card.width / 2, y: b.y); path.move(to: start); let side = max(start.x, end.x) + 80; path.addCurve(to: end, control1: CGPoint(x: side, y: start.y), control2: CGPoint(x: side, y: end.y))
                                    let relevant = hovered.isEmpty || [seats[first]["org"].text, seats[next]["org"].text].contains(hovered)
                                    context.stroke(path, with: .color(RelicStyle.violet.opacity(relevant ? 0.65 : 0.12)), style: StrokeStyle(lineWidth: relevant && !hovered.isEmpty ? 3 : 1.5, dash: [5, 4]))
                                } }
                            }
                        }
                    }
                    ForEach(Array(graph.nodes.enumerated()), id: \.offset) { _, node in
                        card(node).position(graph.centers[node["id"].text] ?? .zero)
                    }
                }.frame(width: graph.size.width + (showShared ? 120 : 0), height: graph.size.height).scaleEffect(zoom, anchor: .topLeading).offset(offset)
                if graph.nodes.isEmpty { Text(m.t("chart.empty")).padding(30) }
            }.frame(maxWidth: .infinity, minHeight: 260, maxHeight: .infinity).clipped().background(GeometryReader { proxy in Color.clear.onAppear { viewport = proxy.size; if autoFit { fit() } }.onChange(of: proxy.size) { viewport = proxy.size; if autoFit { fit() } } })
                .background(WheelZoomCapture { delta, point in zoomAt(zoom * exp(-delta * 0.006), at: point) })
                .focusable().onMoveCommand { direction in
                    switch direction { case .left: offset.width += 60; case .right: offset.width -= 60; case .up: offset.height += 60; case .down: offset.height -= 60; default: break }
                    autoFit = false; clamp(); baseOffset = offset
                }
                .onTapGesture(count: 2) { autoFit = true; fit() }
                .simultaneousGesture(DragGesture(minimumDistance: 4).onChanged { value in
                    autoFit = false; draggedUntil = Date().addingTimeInterval(0.5)
                    offset = CGSize(width: baseOffset.width + value.translation.width, height: baseOffset.height + value.translation.height); clamp()
                }.onEnded { _ in baseOffset = offset })
                .simultaneousGesture(MagnifyGesture().onChanged { zoomAt(lastZoom * $0.magnification, remember: false) }.onEnded { _ in lastZoom = zoom })
            if showShared {
                DisclosureGroup(m.t("chart.legend_shared")) { ScrollView { VStack(alignment: .leading) {
                    Rows(chart["shared"].rows) { shared in Text(m.t("chart.legend_shared") + " · " + shared["seats"].rows.map { orgName($0["org"].text) + "/" + $0["member"].text }.joined(separator: " ↔ "))
                        .help(m.t("chart.link_tip", ["member": shared["seats"].rows.first?["member"].text ?? "", "a": orgName(shared["seats"].rows.first?["org"].text ?? ""), "b": orgName(shared["seats"].rows.last?["org"].text ?? "")])) }
                }.frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 75) }
            }
        }.task {
            showEnded = m.defaults.object(forKey: "chart.closed") as? Bool ?? true; showShared = m.defaults.object(forKey: "chart.shared") as? Bool ?? true
            do { chart = try await m.get("/api/orgchart"); fit() } catch { m.error = m.t("chart.load_failed", ["error": error.localizedDescription]) }
        }.onChange(of: m.revision) { m.run { chart = try await m.get("/api/orgchart"); if autoFit { fit() } } }
            .onChange(of: showEnded) { m.defaults.set(showEnded, forKey: "chart.closed"); fit() }
            .onChange(of: showShared) { m.defaults.set(showShared, forKey: "chart.shared") }
    }
    private func card(_ node: Node) -> some View {
        Button {
            guard Date() > draggedUntil else { return }; m.run { try await m.select(node["id"].text); m.sheet = nil }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack { Text(node["name"].text).font(RelicStyle.font(12.5, weight: 600)).lineLimit(1); if node["cabinet"].flag { Image(systemName: "star.fill").help(m.t("org.cabinet_chip")) } }
                Text(node["leader_display"].text.isEmpty ? m.t("chart.no_leader") : node["leader_display"].text).font(RelicStyle.font(12, weight: 400)).lineLimit(1)
                HStack(spacing: 5) { Text(m.t("common.members", ["n": node["members"].text])).font(RelicStyle.font(10.5, weight: 400)); SmallBadge(text: m.t("chart.decisions", ["n": node["decisions"].text]), color: node["decisions"].integer > 0 ? RelicStyle.amber : RelicStyle.secondary); if sharedCount(node) > 0 { SmallBadge(text: m.t("chart.shared", ["n": String(sharedCount(node))]), color: RelicStyle.violet).help(sharedTip(node)) } }
            }.padding(10).frame(width: OrganizationLayout.card.width, height: OrganizationLayout.card.height, alignment: .leading)
                .background(node["cabinet"].flag ? accent(m.preferences["accent"].text).opacity(0.12) : Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(node["cabinet"].flag || node["id"].text == m.organization ? accent(m.preferences["accent"].text) : RelicStyle.border, style: StrokeStyle(lineWidth: node["id"].text == m.organization ? 2 : 1, dash: node["kind"].text == "subgroup" ? [5, 4] : [])))
        }.buttonStyle(.plain).help(m.t("chart.open_hint", ["name": node["name"].text])).opacity(node["status"].text == "active" ? 1 : 0.5).onHover { hovered = $0 ? node["id"].text : "" }
    }
    private func orgName(_ id: String) -> String { chart["orgs"].rows.first { $0["id"].text == id }?["name"].text ?? id }
    private func sharedCount(_ node: Node) -> Int { chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.count }
    private func sharedTip(_ node: Node) -> String {
        chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.map { shared in
            let seats = shared["seats"].rows
            return m.t("chart.shared_tip", ["member": seats.first { $0["org"].text == node["id"].text }?["member"].text ?? "", "orgs": m.list(seats.filter { $0["org"].text != node["id"].text }.map { orgName($0["org"].text) })])
        }.joined(separator: "\n")
    }
    private func fit(focus: String = "") {
        var bounds = layout.bounds(focus: focus); if showShared { bounds.size.width += 100 }
        zoom = max(0.15, min(1, (viewport.width - 56) / bounds.width, (viewport.height - 56) / bounds.height))
        offset = CGSize(width: (viewport.width - bounds.width * zoom) / 2 - bounds.minX * zoom, height: max(28, (viewport.height - bounds.height * zoom) / 2) - bounds.minY * zoom)
        lastZoom = zoom; baseOffset = offset
    }
    private func zoomAt(_ requested: CGFloat, at point: CGPoint? = nil, remember: Bool = true) {
        let point = point ?? CGPoint(x: viewport.width / 2, y: viewport.height / 2), next = min(2, max(0.15, requested)), ratio = next / zoom
        offset = CGSize(width: point.x - (point.x - offset.width) * ratio, height: point.y - (point.y - offset.height) * ratio)
        zoom = next; autoFit = false; clamp(); if remember { lastZoom = zoom }; baseOffset = offset
    }
    private func clamp() { offset.width = min(viewport.width - 80, max(80 - layout.size.width * zoom, offset.width)); offset.height = min(viewport.height - 80, max(80 - layout.size.height * zoom, offset.height)) }
}

struct WheelZoomCapture: NSViewRepresentable {
    var zoom: (CGFloat, CGPoint) -> Void
    func makeNSView(context: Context) -> CaptureView { let view = CaptureView(); view.zoom = zoom; return view }
    func updateNSView(_ nsView: CaptureView, context: Context) { nsView.zoom = zoom }
    static func dismantleNSView(_ nsView: CaptureView, coordinator: ()) { nsView.removeMonitor() }
    final class CaptureView: NSView {
        var zoom: ((CGFloat, CGPoint) -> Void)?
        var monitor: Any?
        override var isFlipped: Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() {
            removeMonitor(); guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                guard let self, event.window === self.window else { return event }
                let point = self.convert(event.locationInWindow, from: nil)
                guard self.bounds.contains(point) else { return event }; self.zoom?(event.scrollingDeltaY, point); return nil
            }
        }
        func removeMonitor() { if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil }
        deinit { if let monitor { NSEvent.removeMonitor(monitor) } }
    }
}
