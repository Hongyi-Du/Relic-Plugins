import SwiftUI
import RelicCore

struct DetailsView: View {
    @EnvironmentObject var m: Model
    @State private var filter = "open"
    var body: some View {
        VStack(alignment: .leading) {
            Text(m.snapshot["org"]["name"].text).font(.title2)
            Picker(m.t("details.dialog"), selection: $m.detailTab) {
                Text(m.t("common.context_trace")).tag("trace"); Text(m.t("common.tasks")).tag("tasks"); Text(m.t("details.tab_protocols")).tag("protocols"); Text(m.t("details.tab_docs")).tag("docs")
            }.pickerStyle(.segmented)
            switch m.detailTab {
            case "tasks":
                Picker(m.t("common.tasks"), selection: $filter) { Text(m.t("task.working")).tag("open"); Text(m.t("task.blocked")).tag("blocked"); Text(m.t("details.filter_done")).tag("done"); Text(m.t("common.all")).tag("all") }.pickerStyle(.segmented)
                ScrollView { VStack(alignment: .leading, spacing: 12) {
                    Rows(Array(m.snapshot["tasks"].rows.filter { filter == "all" || (filter == "open" ? !["done", "dropped"].contains($0["status"].text) : $0["status"].text == filter) }.reversed())) { TaskCard(task: $0) }
                } }.onAppear { if !m.detailTask.isEmpty { filter = "all" } }
            case "protocols": ScrollView { ProtocolList() }
            case "docs": DocumentsView()
            default: TraceView()
            }
        }.frame(width: 900, height: 640)
    }
}

struct DocumentsView: View {
    @EnvironmentObject var m: Model
    @State private var key = ""
    @State private var doc = Node()
    @State private var error = ""
    var body: some View {
        HSplitView {
            ScrollView { VStack(alignment: .leading, spacing: 12) {
                Rows(m.snapshot["documents"].rows) { item in Button { key = item["key"].text } label: { VStack(alignment: .leading) { Text(item["key"].text); Text(m.t("details.revision", ["n": item["revision"].text]) + " · " + m.name(item["author"].text)).font(.caption) } } }
            }.padding(8) }.frame(width: 220)
            ScrollView { VStack(alignment: .leading, spacing: 10) {
                if m.snapshot["documents"].rows.isEmpty || doc["missing"].flag { Text(m.t("details.no_docs")) }
                Text(key + " · " + m.t("details.revision", ["n": doc["revision"].text])).font(.headline)
                Text(m.t("details.written", ["name": m.name(doc["author"].text), "when": doc["at"].text])).font(.caption)
                RichText(doc["body"].text.isEmpty ? doc["text"].text : doc["body"].text)
                if !error.isEmpty { Text(error).foregroundStyle(.red) }
            }.padding(8).frame(maxWidth: .infinity, alignment: .leading) }
        }.task(id: key) {
            guard !key.isEmpty else { return }; error = ""
            do { let loaded = try await m.get(m.path("/document?key=" + Client.segment(key))); try Task.checkCancellation(); doc = loaded } catch is CancellationError {} catch { self.error = error.localizedDescription }
        }.onAppear { key = m.snapshot["documents"].rows.first?["key"].text ?? "" }
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
            ScrollView { VStack(alignment: .leading, spacing: 12) { Rows(m.members) { who in Button(who.display) { m.detailMember = who["name"].text } } }.padding(8) }.frame(width: 180)
            VStack(alignment: .leading) {
                Text(m.t("trace.title", ["name": m.name(m.detailMember)])).font(.headline)
                Picker("", selection: $filter) { Text(m.t("common.all")).tag("all"); Text(m.t("trace.filter_talk")).tag("talk"); Text(m.t("trace.filter_actions")).tag("tools") }.pickerStyle(.segmented)
                TextField(m.t("trace.search"), text: $query)
                if data["start"].integer > 0 { Button(m.t("trace.load_older")) { m.run { try await load(older: true) } }.disabled(loading) }
                ScrollView { LazyVStack(alignment: .leading, spacing: 12) {
                    if data["missing"].flag { Text(m.t("trace.no_session")) }
                    else if steps.isEmpty { Text(m.t("trace.no_steps")) }
                    Rows(steps) { StepView(step: $0, member: m.detailMember) }
                    Text(m.t("trace.total", ["n": data["total"].text]) + " · " + data["path"].text).font(.caption).textSelection(.enabled)
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
