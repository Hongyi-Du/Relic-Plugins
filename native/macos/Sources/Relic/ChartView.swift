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
    private var nodes: [Node] { chart["orgs"].rows.filter { showEnded || $0["status"].text == "active" } }
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
                Toggle(m.t("chart.show_closed"), isOn: $showEnded)
                Toggle(m.t("chart.show_links"), isOn: $showShared)
                Button(m.t("chart.zoom_in")) { zoom = min(3, zoom * 1.2); lastZoom = zoom }.keyboardShortcut("=", modifiers: [])
                Button(m.t("chart.zoom_out")) { zoom = max(0.2, zoom / 1.2); lastZoom = zoom }.keyboardShortcut("-", modifiers: [])
                Button(m.t("chart.zoom_actual")) { zoom = 1; lastZoom = 1 }.keyboardShortcut("0", modifiers: [])
                Button(m.t("chart.fit")) { zoom = min(1, 480 / CGFloat(max(1, nodes.count) * 110)); lastZoom = zoom; offset = .zero; baseOffset = .zero }
            }
            if nodes.isEmpty { Text(m.t("chart.empty")) }
            Text(m.t("chart.pan_hint")).font(.caption)
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
                            if showShared {
                                for shared in chart["shared"].rows {
                                    let seats = shared["seats"].rows.compactMap { seat in nodes.firstIndex { $0["id"].text == seat["org"].text } }
                                    if let first = seats.first {
                                        for next in seats.dropFirst() where first != next {
                                            var path = Path(); path.move(to: point(nodes[first], first)); path.addLine(to: point(nodes[next], next))
                                            let relevant = hovered.isEmpty || [nodes[first]["id"].text, nodes[next]["id"].text].contains(hovered)
                                            context.stroke(path, with: .color(.accentColor.opacity(relevant ? 1 : 0.15)), style: StrokeStyle(lineWidth: relevant && !hovered.isEmpty ? 3 : 1.5, dash: [5, 4]))
                                        }
                                    }
                                }
                            }
                        }
                        ForEach(Array(nodes.enumerated()), id: \.offset) { index, node in
                            Button { m.run { try await m.select(node["id"].text); m.sheet = nil } } label: {
                                VStack(alignment: .leading) {
                                    Text(node["name"].text).font(.headline)
                                    if node["cabinet"].flag { Text(m.t("org.cabinet_chip")).font(.caption) }
                                    Text(node["leader_display"].text.isEmpty ? m.t("chart.no_leader") : node["leader_display"].text).font(.caption)
                                    Text(m.t("common.members", ["n": node["members"].text])).font(.caption)
                                    Text(m.t("chart.decisions", ["n": node["decisions"].text])).font(.caption)
                                    if sharedCount(node) > 0 { Text(m.t("chart.shared", ["n": String(sharedCount(node))])).font(.caption).help(sharedTip(node)) }
                                }.frame(width: 190, height: 70).padding(8)
                            }.buttonStyle(.bordered).help(m.t("chart.open_hint", ["name": node["name"].text])).opacity(node["status"].text == "active" ? 1 : 0.5).position(point(node, index)).onHover { hovered = $0 ? node["id"].text : "" }
                        }
                    }.frame(width: max(800, CGFloat(nodes.count) * 240), height: max(500, CGFloat(nodes.count) * 110))
                        .scaleEffect(zoom, anchor: .topLeading).offset(offset)
                }.clipped().background(WheelZoomCapture { delta, point in
                    let next = min(3, max(0.2, zoom * exp(-delta * 0.006))), ratio = next / zoom
                    offset = CGSize(width: point.x - (point.x - offset.width) * ratio, height: point.y - (point.y - offset.height) * ratio)
                    zoom = next; lastZoom = next; baseOffset = offset
                }).onTapGesture(count: 2) { zoom = min(1, 480 / CGFloat(max(1, nodes.count) * 110)); lastZoom = zoom; offset = .zero; baseOffset = .zero }
                    .gesture(DragGesture().onChanged { offset = CGSize(width: baseOffset.width + $0.translation.width, height: baseOffset.height + $0.translation.height) }.onEnded { _ in baseOffset = offset })
                    .simultaneousGesture(MagnifyGesture().onChanged { zoom = min(3, max(0.2, lastZoom * $0.magnification)) }.onEnded { _ in lastZoom = zoom })
            }.frame(width: 820, height: 500)
            ScrollView {
                Rows(chart["shared"].rows) { shared in Text(m.t("chart.legend_shared") + " · " + shared["seats"].rows.map { $0["org"].text + "/" + $0["member"].text }.joined(separator: " ↔ ")).help(m.t("chart.link_tip", ["member": shared["seats"].rows.first?["member"].text ?? "", "a": shared["seats"].rows.first?["org"].text ?? "", "b": shared["seats"].rows.last?["org"].text ?? ""])) }
            }.frame(maxHeight: 90)
            Text(m.t("chart.legend_ended")).foregroundStyle(.secondary).font(.caption)
        }.task { m.run { do { chart = try await m.get("/api/orgchart") } catch { throw RelicError.message(m.t("chart.load_failed", ["error": error.localizedDescription])) } } }
        .onChange(of: m.revision) { m.run { chart = try await m.get("/api/orgchart") } }
    }
    func sharedCount(_ node: Node) -> Int { chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.count }
    func sharedTip(_ node: Node) -> String {
        chart["shared"].rows.filter { $0["seats"].rows.contains { $0["org"].text == node["id"].text } }.map { shared in
            let seats = shared["seats"].rows
            return m.t("chart.shared_tip", ["member": seats.first { $0["org"].text == node["id"].text }?["member"].text ?? "", "orgs": seats.filter { $0["org"].text != node["id"].text }.map { $0["org"].text }.joined(separator: ", ")])
        }.joined(separator: "\n")
    }
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
