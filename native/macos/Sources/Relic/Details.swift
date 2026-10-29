import SwiftUI
import RelicCore

struct DetailsView: View {
    @EnvironmentObject var m: Model
    private func tasks(_ filter: String) -> [Node] {
        m.snapshot["tasks"].rows.filter { filter == "all" || (filter == "open" ? !["done", "dropped"].contains($0["status"].text) : $0["status"].text == filter) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                ReferenceLabel(m.snapshot["org"]["name"].text, size: 15.5, weight: 650).frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 2) {
                    ForEach([("trace", "common.context_trace"), ("tasks", "common.tasks"), ("protocols", "details.tab_protocols"), ("docs", "details.tab_docs")], id: \.0) { key, title in
                        TextButton(m.t(title), size: 12.5, weight: m.detailTab == key ? 600 : 400, color: m.detailTab == key ? RelicStyle.ink : RelicStyle.secondary, height: 28, padding: 12) { m.detailTab = key }
                            .buttonStyle(QuietButtonStyle(selected: m.detailTab == key)).accessibilityAddTraits(m.detailTab == key ? .isSelected : [])
                    }
                }.padding(2).modifier(RecordedSurface(background: RelicStyle.hover, radius: 9, kind: "region"))
            }.padding(.leading, 16).padding(.trailing, 58).frame(height: 57)
                .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
            switch m.detailTab {
            case "tasks":
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        SettingsSegments(options: [("open", m.t("task.working") + " " + String(tasks("open").count)), ("blocked", m.t("task.blocked") + " " + String(tasks("blocked").count)), ("done", m.t("details.filter_done") + " " + String(tasks("done").count)), ("all", m.t("common.all") + " " + String(tasks("all").count))], selection: $m.detailFilter).padding(.bottom, 12)
                        if tasks(m.detailFilter).isEmpty { ReferenceLabel(m.t("details.no_tasks"), size: 13, color: RelicStyle.muted).padding(22) }
                        Rows(Array(tasks(m.detailFilter).reversed())) { TaskCard(task: $0).padding(.bottom, 8) }
                    }.padding(.vertical, 16).padding(.horizontal, 20).frame(maxWidth: .infinity, alignment: .leading)
                }
            case "protocols": ScrollView { ProtocolList().padding(.vertical, 16).padding(.horizontal, 20) }
            case "docs": DocumentsView()
            default: TraceView()
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("details.dialog"))
    }

}

struct DocumentsView: View {
    @EnvironmentObject var m: Model
    @State private var doc = Node()
    @State private var error = ""
    var body: some View {
        HStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 1) {
                    Rows(m.snapshot["documents"].rows) { item in
                        Button { m.detailDocument = item["key"].text } label: {
                            HStack(spacing: 9) {
                                ReferenceIcon(name: "folder", size: 14).frame(width: 28, height: 28).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "avatar"))
                                VStack(alignment: .leading, spacing: 0) {
                                    ReferenceLabel(item["key"].text, size: 13.3, weight: 550, lineHeight: 17.955)
                                    ReferenceLabel(m.t("details.revision", ["n": item["revision"].text]) + " · " + m.name(item["author"].text), size: 12, color: RelicStyle.muted, lineHeight: 16.2)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }.padding(.horizontal, 8).padding(.vertical, 6)
                        }.buttonStyle(QuietButtonStyle()).help(item["key"].text)
                    }
                }.padding(8)
            }.frame(width: 250).modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 1), kind: "region"))
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if m.snapshot["documents"].rows.isEmpty || doc["missing"].flag { ReferenceLabel(m.t("details.no_docs"), size: 13, color: RelicStyle.muted).padding(22) }
                    if !m.detailDocument.isEmpty, !doc.isNull {
                        ReferenceLabel(m.detailDocument + " · " + m.t("details.revision", ["n": doc["revision"].text]), size: 16.38, weight: 700, lines: 0).padding(.bottom, 4)
                        ReferenceLabel(m.t("details.written", ["name": m.name(doc["author"].text), "when": m.day(doc["at"]) + " " + m.clock(doc["at"])]), size: 12.5, color: RelicStyle.muted, lines: 0).padding(.bottom, 10)
                        SelectableText(value: AttributedString(doc["body"].text.isEmpty ? doc["text"].text : doc["body"].text), pointSize: 12.5, lineHeight: 20.625, monospaced: true)
                            .padding(15).frame(maxWidth: .infinity, alignment: .leading)
                            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 10, kind: "code"))
                    }
                    if !error.isEmpty { Text(error).foregroundStyle(RelicStyle.red) }
                }.padding(.vertical, 16).padding(.horizontal, 20).frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxWidth: .infinity)
        }.task(id: m.detailDocument) {
            guard !m.detailDocument.isEmpty else { doc = Node(); return }; error = ""
            do { let loaded = try await m.get(m.path("/document?key=" + Client.segment(m.detailDocument))); try Task.checkCancellation(); doc = loaded } catch is CancellationError {} catch { self.error = error.localizedDescription }
        }
    }
}

struct TraceView: View {
    @EnvironmentObject var m: Model
    @State private var data = Node()
    @State private var query = ""
    @State private var filter = "all"
    @State private var loading = false
    @State private var error = ""
    private var steps: [Node] { data["steps"].rows.filter { step in
        (filter == "all" || (filter == "talk" ? ["user", "assistant"].contains(step["role"].text) : ["tool_call", "tool_result"].contains(step["role"].text))) && (query.isEmpty || step["text"].text.localizedCaseInsensitiveContains(query))
    } }
    var body: some View {
        HSplitView {
            ScrollView { VStack(alignment: .leading, spacing: 3) { Rows(m.members) { who in Button { m.detailMember = who["name"].text } label: { HStack(spacing: 8) { Avatar(member: who["name"].text, size: 25); Text(who.display).font(RelicStyle.font(13, weight: 400)).lineLimit(2); Spacer(minLength: 0) }.padding(7) }.buttonStyle(QuietButtonStyle(selected: m.detailMember == who["name"].text)).help(who.display) } }.padding(8) }.frame(width: 180).background(RelicStyle.sidebar)
            VStack(alignment: .leading) {
                Text(m.t("trace.title", ["name": m.name(m.detailMember)])).font(.headline)
                Text(m.t("trace.session", ["id": data["session"].text]) + (m.members.first { $0["name"].text == m.detailMember }?["parent"].text.isEmpty == false ? m.t("trace.in_session", ["name": m.name(m.members.first { $0["name"].text == m.detailMember }?["parent"].text ?? "")]) : "")).font(RelicStyle.font(12, weight: 400))
                Picker("", selection: $filter) { Text(m.t("common.all")).tag("all"); Text(m.t("trace.filter_talk")).tag("talk"); Text(m.t("trace.filter_actions")).tag("tools") }.pickerStyle(.segmented)
                TextField(m.t("trace.search"), text: $query)
                if data["start"].integer > 0 { Button(m.t("trace.load_older")) { m.run { try await load(older: true) } }.disabled(loading) }
                ScrollView { LazyVStack(alignment: .leading, spacing: 12) {
                    if data["missing"].flag { Text(m.t("trace.no_session")) }
                    else if steps.isEmpty { Text(m.t("trace.no_steps")) }
                    Rows(steps) { StepView(step: $0, member: m.detailMember) }
                    Text(m.t("trace.total", ["n": data["total"].text]) + " · " + data["path"].text).font(RelicStyle.font(12, weight: 400)).textSelection(.enabled)
                } }
                if !error.isEmpty { Text(error).foregroundStyle(.red) }
            }.padding(8)
        }.onAppear { if m.detailMember.isEmpty { m.detailMember = m.members.first?["name"].text ?? "" } }
        .task(id: m.organization + "/" + m.detailMember) { data = Node(); do { try await load(older: false) } catch is CancellationError {} catch { self.error = error.localizedDescription } }
    }
    func load(older: Bool) async throws {
        let org = m.organization, who = m.detailMember; guard !who.isEmpty else { return }; loading = true; defer { loading = false }
        let result = try await m.get(Client.org(org, "/transcript?member=" + Client.segment(who) + "&limit=400&full=1" + (older ? "&before=" + data["start"].text : "")))
        try Task.checkCancellation(); guard org == m.organization, who == m.detailMember else { return }
        data = older ? Node(result.object.merging(["steps": result["steps"].rows.map(\.raw) + data["steps"].rows.map(\.raw)]) { _, new in new }) : result
    }
}
