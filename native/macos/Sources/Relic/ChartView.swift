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
    @State private var fitFocus = ""
    @State private var draggedUntil = Date.distantPast
    @State private var viewport = CGSize(width: 760, height: 360)
    private var layout: OrganizationLayout { OrganizationLayout(chart["orgs"].rows.filter { showEnded || $0["status"].text == "active" }) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                ReferenceLabel(m.t("chart.title"), size: 15.5, weight: 650).frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 2) {
                    IconButton(title: m.t("chart.zoom_out"), icon: "minus", size: 16, height: 28) { zoomAt(zoom / 1.25) }.keyboardShortcut("-", modifiers: [])
                    TextButton(String(Int((zoom * 100).rounded())) + "%", size: 12, weight: 400, color: RelicStyle.secondary, height: 28) { zoomAt(1) }.frame(width: 50).buttonStyle(QuietButtonStyle()).help(m.t("chart.zoom_actual"))
                    IconButton(title: m.t("chart.zoom_in"), icon: "plus", size: 16, height: 28) { zoomAt(zoom * 1.25) }.keyboardShortcut("=", modifiers: [])
                    IconButton(title: m.t("chart.fit"), icon: "fit", size: 16, height: 28) { autoFit = true; fitFocus = ""; fit() }.keyboardShortcut("0", modifiers: [])
                }
                chartToggle("chart.show_closed", value: $showEnded)
                chartToggle("chart.show_links", value: $showShared)
            }.padding(.leading, 16).padding(.trailing, 54).padding(.vertical, 12).padding(.bottom, 1)
                .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
            ChartLegend()
            let graph = layout
            ZStack(alignment: .topLeading) {
                Color.clear.contentShape(Rectangle())
                ZStack(alignment: .topLeading) {
                    ForEach(Array(edges(graph).enumerated()), id: \.offset) { index, edge in
                        ChartEdgeView(edge: edge, plane: graph.size, index: index)
                    }
                    ForEach(Array(graph.nodes.enumerated()), id: \.offset) { _, node in
                        card(node).position(graph.centers[node["id"].text] ?? .zero)
                    }
                }.frame(width: graph.size.width, height: graph.size.height).scaleEffect(zoom, anchor: .topLeading).offset(x: offset.width.rounded(), y: offset.height.rounded())
                if graph.nodes.isEmpty { Text(m.t("chart.empty")).padding(30) }
            }.frame(maxWidth: .infinity, minHeight: 0, maxHeight: .infinity).clipped().modifier(RecordedSurface(background: RelicStyle.sidebar, kind: "region")).background(GeometryReader { proxy in Color.clear.onAppear { viewport = proxy.size; if autoFit { fit() } }.onChange(of: proxy.size) { viewport = proxy.size; if autoFit { fit() } } })
                .background(WheelZoomCapture { delta, point in zoomAt(zoom * exp(-delta * 0.0015), at: point) })
                .focusable().onMoveCommand { direction in
                    switch direction { case .left: offset.width += 60; case .right: offset.width -= 60; case .up: offset.height += 60; case .down: offset.height -= 60; default: break }
                    autoFit = false; clamp(); baseOffset = offset
                }
                .onTapGesture(count: 2) { autoFit = true; fitFocus = ""; fit() }
                .simultaneousGesture(DragGesture(minimumDistance: 4).onChanged { value in
                    autoFit = false; draggedUntil = Date().addingTimeInterval(0.5)
                    offset = CGSize(width: baseOffset.width + value.translation.width, height: baseOffset.height + value.translation.height); clamp()
                }.onEnded { _ in baseOffset = offset })
                .simultaneousGesture(MagnifyGesture().onChanged { zoomAt(lastZoom * $0.magnification, remember: false) }.onEnded { _ in lastZoom = zoom })
        }.task {
            showEnded = m.defaults.object(forKey: "chart.closed") as? Bool ?? true; showShared = m.defaults.object(forKey: "chart.shared") as? Bool ?? true
            do { fitFocus = m.organization; chart = try await m.get("/api/orgchart"); fit() } catch { m.error = m.t("chart.load_failed", ["error": error.localizedDescription]) }
        }.onChange(of: m.revision) { m.run { chart = try await m.get("/api/orgchart"); if autoFit { fit() } } }
            .onChange(of: showEnded) { m.defaults.set(showEnded, forKey: "chart.closed"); fit() }
            .onChange(of: showShared) { m.defaults.set(showShared, forKey: "chart.shared") }
    }
    private func chartToggle(_ key: String, value: Binding<Bool>) -> some View {
        HStack(spacing: 8) {
            ReferenceSwitch(m.t(key), isOn: value)
            ReferenceLabel(m.t(key), size: 12.5, color: RelicStyle.secondary).fixedSize()
        }
    }
    private func card(_ node: Node) -> some View {
        let identity = "relic-chart-node/" + node["id"].text
        let who = node["leader_display"].text.isEmpty ? node["leader"].text : node["leader_display"].text
        let leader = node["governance"].text == "peer" ? m.t("org.gov_peer") : node["leader"].text.isEmpty ? m.t("chart.no_leader") : m.t(node["cabinet"].flag ? "org.secretary_general_chip" : "org.leader_chip", ["name": who])
        return Button {
            guard Date() > draggedUntil else { return }; m.run { try await m.select(node["id"].text); m.sheet = nil }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    OrganizationBadge(node: node)
                    ReferenceLabel(node["name"].text, size: 13, weight: 650, owner: identity).frame(maxWidth: .infinity, alignment: .leading)
                    if node["cabinet"].flag { ChartChip(text: m.t("org.cabinet_chip"), tone: "sec") }
                    if node["kind"].text == "subgroup" { ChartChip(text: m.t("org.kind_subgroup")) }
                    if node["status"].text != "active" { ChartChip(text: m.t(node["status"].text == "closed" ? "org.status_closed" : "org.status_dissolved")) }
                }
                ReferenceLabel(leader, size: 11.5, color: RelicStyle.secondary, owner: identity)
                HStack(spacing: 6) {
                    ReferenceLabel(m.t("common.members", ["n": node["members"].text]), size: 11.5, color: RelicStyle.secondary, owner: identity)
                    ChartChip(text: m.t("chart.decisions", ["n": node["decisions"].text]), tone: node["decisions"].integer > 0 ? "warn" : "")
                    if sharedCount(node) > 0 { ChartChip(text: m.t("chart.shared", ["n": String(sharedCount(node))]), tone: "sec").help(sharedTip(node)) }
                }
            }.padding(.horizontal, 12.5).padding(.vertical, 9.5).frame(width: OrganizationLayout.card.width, height: OrganizationLayout.card.height, alignment: .leading)
                .modifier(RecordedSurface(background: node["cabinet"].flag ? RelicStyle.mix(RelicStyle.violetSoft, RelicStyle.card, fraction: 0.75) : RelicStyle.card,
                    border: hovered == node["id"].text ? RelicStyle.muted : node["cabinet"].flag || node["governance"].text == "peer" ? RelicStyle.violet : RelicStyle.border, borderWidth: 1.5, radius: 12, kind: "chart-node", owner: identity, hovered: hovered == node["id"].text,
                    shadows: node["id"].text == m.organization ? [] : hovered == node["id"].text ? SurfaceShadow.dialog : SurfaceShadow.small,
                    borderDash: node["kind"].text == "subgroup" ? [4,3] : [], current: node["id"].text == m.organization, outerRingWidth: node["id"].text == m.organization ? 3 : 0, outerRingColor: RelicStyle.accent.opacity(0.4)))
        }.buttonStyle(.plain).accessibilityIdentifier(identity)
            .help(([m.t("chart.open_hint", ["name": node["name"].text]), leader, node["purpose"].text, sharedTip(node)]).filter { !$0.isEmpty }.joined(separator: "\n"))
            .recordedOpacity(node["status"].text == "active" ? 1 : 0.5).onHover { hovered = $0 ? node["id"].text : "" }
    }
    private func edges(_ graph: OrganizationLayout) -> [ChartEdge] {
        func n(_ value: CGFloat) -> String { String(format: "%g", Double(value)) }
        var result: [ChartEdge] = []
        for node in graph.nodes {
            let id = node["id"].text
            guard let parent = graph.parents[id], let a = graph.centers[parent], let b = graph.centers[id] else { continue }
            let top = a.y + 40, bottom = b.y - 40, middle = (top + bottom) / 2
            result.append(ChartEdge(path: "M" + n(a.x) + "," + n(top) + "V" + n(middle) + "H" + n(b.x) + "V" + n(bottom), color: RelicStyle.faint, width: 1.4, dash: [], opacity: 1))
        }
        if showShared {
            var pairIndices: [String: Int] = [:]
            for shared in chart["shared"].rows {
                let seats = shared["seats"].rows.filter { graph.centers[$0["org"].text] != nil }
                for first in seats.indices { for next in seats.indices where next > first {
                    let pair = [seats[first], seats[next]].sorted { $0["org"].text < $1["org"].text }
                    let aid = pair[0]["org"].text, bid = pair[1]["org"].text, key = aid + "/" + bid
                    guard aid != bid else { continue }
                    let tip = m.t("chart.link_tip", ["member": pair[0]["member"].text == pair[1]["member"].text ? pair[0]["member"].text : pair[0]["member"].text + " / " + pair[1]["member"].text, "a": orgName(aid), "b": orgName(bid)])
                    if let index = pairIndices[key] { result[index].tip += "\n" + tip; continue }
                    pairIndices[key] = result.count
                    let a = graph.centers[aid]!, b = graph.centers[bid]!
                    let d: String
                    if abs(a.x - b.x) >= OrganizationLayout.card.width {
                        let left = a.x < b.x ? a : b, right = a.x < b.x ? b : a, x1 = left.x + 118, x2 = right.x - 118, middle = (x1 + x2) / 2
                        d = "M" + n(x1) + "," + n(left.y) + "C" + n(middle) + "," + n(left.y) + " " + n(middle) + "," + n(right.y) + " " + n(x2) + "," + n(right.y)
                    } else {
                        let x1 = a.x + 118, x2 = b.x + 118, outside = max(x1,x2) + 32
                        d = "M" + n(x1) + "," + n(a.y) + "C" + n(outside) + "," + n(a.y) + " " + n(outside) + "," + n(b.y) + " " + n(x2) + "," + n(b.y)
                    }
                    let hot = !hovered.isEmpty && [aid,bid].contains(hovered)
                    result.append(ChartEdge(path: d, color: RelicStyle.violet, width: hot ? 2 : 1.2, dash: [4,3], opacity: hovered.isEmpty ? 0.5 : hot ? 1 : 0.12, tip: tip))
                } }
            }
        }
        return result
    }
    private func orgName(_ id: String) -> String { chart["orgs"].rows.first { $0["id"].text == id }?["name"].text ?? id }
    private func sharedCount(_ node: Node) -> Int { chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.count }
    private func sharedTip(_ node: Node) -> String {
        chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.map { shared in
            let seats = shared["seats"].rows
            return m.t("chart.shared_tip", ["member": seats.first { $0["org"].text == node["id"].text }?["member"].text ?? "", "orgs": m.list(seats.filter { $0["org"].text != node["id"].text }.map { orgName($0["org"].text) })])
        }.joined(separator: "\n")
    }
    private func fit() {
        var bounds = layout.bounds(focus: fitFocus); if showShared && !chart["shared"].rows.isEmpty { bounds.size.width += 32 }
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
