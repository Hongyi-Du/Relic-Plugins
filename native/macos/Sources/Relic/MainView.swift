import SwiftUI
import RelicCore

struct Rows<Content: View>: View {
    let nodes: [Node]
    @ViewBuilder let content: (Node) -> Content
    init(_ nodes: [Node], @ViewBuilder content: @escaping (Node) -> Content) { self.nodes = nodes; self.content = content }
    var body: some View { ForEach(Array(nodes.enumerated()), id: \.offset) { _, node in content(node) } }
}

struct MainView: View {
    @EnvironmentObject var m: Model
    @State private var search = ""
    var body: some View {
        VStack(spacing: 0) {
            if !m.error.isEmpty {
                HStack { Text(m.error).textSelection(.enabled); Spacer(); Button(m.t("common.close")) { m.error = "" } }.padding(8).background(.red.opacity(0.12))
            }
            if !m.ready { ProgressView().padding() }
            HSplitView {
                VStack(alignment: .leading, spacing: 12) {
                    Button(m.t("common.new_org")) { m.sheet = .create }
                    TextField(m.t("page.search"), text: $search)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 8) {
                            if search.isEmpty {
                                Rows(m.organizations.filter { o in o["parent"].text.isEmpty || !m.organizations.contains { $0["id"].text == o["parent"].text } }) { o in OrgTree(node: o, ancestors: []) }
                            } else {
                                Rows(m.organizations.filter { $0["name"].text.localizedCaseInsensitiveContains(search) }) { o in
                                    Button(o["name"].text) { m.run { try await m.select(o["id"].text) } }
                                }
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                    Button(m.t("cc.title")) { m.sheet = .copies }
                    Button(m.t("chart.title")) { m.sheet = .chart }
                    Button(m.t("common.settings")) { m.sheet = .settings }
                }.padding(12).frame(minWidth: 220, idealWidth: 260, maxWidth: 340)
                ChatView().frame(minWidth: 350, maxWidth: .infinity)
                VStack {
                    Picker("", selection: $m.pane) {
                        Text(m.t("panel.overview")).tag("overview")
                        Text(m.t("panel.workspace")).tag("workspace")
                        Text(m.t("common.file")).tag("files")
                    }.pickerStyle(.segmented)
                    ScrollView { if m.pane == "overview" { Overview() } else { WorkspaceView() } }
                }.padding(12).frame(minWidth: 320, idealWidth: 370, maxWidth: 500)
            }
        }
        .sheet(item: $m.sheet) { sheet in
            VStack {
                HStack { Spacer(); Button(m.t("common.close")) { m.sheet = nil } }.padding(.bottom, 8)
                switch sheet {
                case .create: CreateOrgView()
                case .member: MemberForm()
                case .settings: SettingsView()
                case .copies: CopiesView()
                case .chart: ChartView()
                case .protocolForm: ProtocolForm()
                }
            }.padding(20).frame(minWidth: 560, minHeight: 260).environmentObject(m)
        }
    }
}

struct OrgTree: View {
    @EnvironmentObject var m: Model
    let node: Node
    let ancestors: Set<String>
    var body: some View {
        let id = node["id"].text
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Button { if m.folded.contains(id) { m.folded.remove(id) } else { m.folded.insert(id) } } label: { Image(systemName: m.folded.contains(id) ? "chevron.right" : "chevron.down") }
                    .buttonStyle(.plain).accessibilityLabel(m.t("common.collapse"))
                Button(node["name"].text) { m.run { try await m.select(id) } }.fontWeight(m.organization == id ? .semibold : .regular)
            }
            if !m.folded.contains(id) {
                if m.organization == id {
                    VStack(alignment: .leading, spacing: 8) {
                        Button("# " + m.t("common.group_chat")) { m.run { try await m.select(id) } }
                        Rows(m.snapshot["members"].rows) { member in
                            Button { m.run { try await m.select(id, member["name"].text) } } label: {
                                VStack(alignment: .leading) {
                                    Text("@ " + member["display"].text)
                                    Text(m.t("state." + member["state"].text)).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        Button("+ " + m.t("common.add_member")) { m.sheet = .member }
                    }.padding(.leading, 20)
                }
                Rows(m.organizations.filter { $0["parent"].text == id && !ancestors.contains($0["id"].text) }) { child in
                    AnyView(OrgTree(node: child, ancestors: ancestors.union([id])).padding(.leading, 14))
                }
            }
        }.buttonStyle(.plain)
    }
}

struct ChatView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(m.snapshot["org"]["name"].text + " · " + (m.member.isEmpty ? m.t("common.group_chat") : m.member)).font(.title3)
                Spacer()
                if !m.member.isEmpty { Button(m.t("common.cancel")) { m.run { try await m.post(m.path("/cancel"), ["member": m.member]); try await m.refresh() } } }
            }
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        Rows(m.messages) { item in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item["from"].text + "  " + item["at"].text).font(.caption).foregroundStyle(.secondary)
                                Text(item["body"].text.isEmpty ? item["text"].text : item["body"].text).textSelection(.enabled)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                        Color.clear.frame(height: 1).id("end")
                    }.padding(.vertical, 8)
                }.onChange(of: m.member) { proxy.scrollTo("end", anchor: .bottom) }
                HStack {
                    if m.member.isEmpty {
                        Picker(m.t("composer.send_to", ["to": ""]), selection: $m.recipient) {
                            Text(m.t("composer.all_members")).tag("all")
                            Rows(m.snapshot["members"].rows) { Text("@" + $0["display"].text).tag($0["name"].text) }
                        }.labelsHidden()
                    }
                    Spacer()
                }
                TextEditor(text: $m.draft).font(.body).frame(minHeight: 70, maxHeight: 140)
                    .overlay(RoundedRectangle(cornerRadius: 5).stroke(.secondary.opacity(0.3)))
                    .accessibilityLabel(m.member.isEmpty ? m.t("composer.group_placeholder") : m.t("composer.dm_placeholder", ["name": m.member]))
                HStack { Spacer(); Button(m.t("common.send")) { m.run { try await m.send(); proxy.scrollTo("end", anchor: .bottom) } }.keyboardShortcut(.return, modifiers: .command).disabled(m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
            }
        }.padding(16)
    }
}

struct Overview: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(m.snapshot["org"]["purpose"].text).font(.headline)
            Text(m.t("appbar.decisions", ["n": String(m.snapshot["decisions"].rows.count)])).font(.headline)
            Rows(m.snapshot["decisions"].rows) { DecisionView(decision: $0) }
            Text(m.t("org.members")).font(.headline)
            Rows(m.snapshot["members"].rows) { member in
                Button { m.run { try await m.select(m.organization, member["name"].text) } } label: {
                    VStack(alignment: .leading) {
                        Text(member["display"].text + " · " + m.t("state." + member["state"].text))
                        Text(member["role"].text).font(.caption)
                        Text(member["doing"].text).font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain)
            }
            Text(m.t("common.tasks")).font(.headline)
            Rows(m.snapshot["tasks"].rows) { task in
                VStack(alignment: .leading) {
                    Text(task["id"].text + " " + task["title"].text)
                    Text(task["owner"].text + " · " + m.t("task." + task["status"].text)).foregroundStyle(.secondary)
                    Text(task["report"].text).textSelection(.enabled)
                }
            }
            HStack { Text(m.t("org.protocols")).font(.headline); Spacer(); Button(m.t("org.add")) { m.sheet = .protocolForm } }
            ForEach(["protocols", "inherited_protocols", "replaced_protocols"], id: \.self) { key in
                Rows(m.snapshot[key].rows) { p in
                    DisclosureGroup(p["id"].text + " " + p["title"].text + " · " + p["status"].text) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(p["guidance"].text).textSelection(.enabled)
                            Text(p["summary_for_person"].text)
                            if !p["from"].text.isEmpty { Text(m.t("org.inherited_from", ["name": p["from"].text])) }
                            if !p["issued_by"].isNull { Text(p["issued_by"]["person"].flag ? m.t("org.issued_by_person") : m.t("org.issued_by", ["name": p["issued_by"]["name"].text])) }
                            Rows(p["rules"].rows) { rule in Text(pretty(rule)).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 8)
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}

struct DecisionView: View {
    @EnvironmentObject var m: Model
    let decision: Node
    @State private var sending = false
    func act(_ action: @escaping () async throws -> Void) {
        sending = true
        m.run { defer { sending = false }; try await action(); try await m.refresh() }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(["label", "title", "text", "reason", "error"].map { decision[$0].text }.filter { !$0.isEmpty }.joined(separator: "\n")).textSelection(.enabled)
            if decision["kind"].text == "permission" {
                Rows(decision["options"].rows) { option in Button(option["name"].text) { act { try await m.post("/api/permission/" + Client.segment(decision["id"].text), ["option": option["id"].text]) } } }
            } else if ["approval", "trajectory"].contains(decision["kind"].text) {
                HStack {
                    ForEach(["approve", "deny"], id: \.self) { answer in
                        Button(m.t("decision." + answer)) {
                            act {
                                let org = decision["org"].text.isEmpty ? m.organization : decision["org"].text
                                let route = decision["kind"].text == "approval" ? "/request" : "/trajectory_answer"
                                let result = try await m.post(Client.org(org, route), ["request_id": decision["id"].text, "decision": answer])
                                if result["status"].text == "failed" { throw RelicError.message(result["error"].text) }
                            }
                        }
                    }
                }
            } else if !decision["member"].text.isEmpty { Button(m.t("decision.open_chat")) { m.run { try await m.select(m.organization, decision["member"].text) } } }
        }.padding(10).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8)).disabled(sending)
    }
}

struct WorkspaceView: View {
    @EnvironmentObject var m: Model
    @State private var workspace = Node()
    @State private var entries: [Node] = []
    @State private var preview = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(workspace["folder"].text).textSelection(.enabled)
            Rows(entries) { entry in
                Button(entry["name"].text) {
                    m.run {
                        if entry["dir"].flag { entries = try await m.get("/api/fs/list?path=" + Client.segment(entry["path"].text))["entries"].rows }
                        else { preview = try await m.get("/api/fs/read?path=" + Client.segment(entry["path"].text))["text"].text }
                    }
                }
            }
            Text(preview).font(.system(.body, design: .monospaced)).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading)
        .task(id: m.organization + "/" + m.member) {
            m.run {
                workspace = try await m.get(m.path("/workspace?member=" + Client.segment(m.member)))
                if !workspace["folder"].text.isEmpty { entries = try await m.get("/api/fs/list?path=" + Client.segment(workspace["folder"].text))["entries"].rows }
            }
        }
    }
}
