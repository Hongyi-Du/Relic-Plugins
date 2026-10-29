import SwiftUI
import RelicCore

struct Rows<Content: View>: View {
    let nodes: [Node]
    @ViewBuilder let content: (Node) -> Content
    init(_ nodes: [Node], @ViewBuilder content: @escaping (Node) -> Content) { self.nodes = nodes; self.content = content }
    var body: some View { ForEach(NodeRow.identify(nodes)) { content($0.node) } }
}

struct MainView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(spacing: 0) {
            if !m.error.isEmpty { HStack { Text(m.error).textSelection(.enabled); Spacer(); Button(m.t("common.close")) { m.error = "" } }.padding(8).background(.red.opacity(0.12)) }
            if !m.notice.isEmpty { HStack { Text(m.notice); Spacer(); Button(m.t("common.close")) { m.notice = "" } }.padding(8) }
            if !m.ready { ProgressView().padding(); Button(m.t("appmenu.reload")) { Task { await m.start() } } }
            HSplitView {
                if m.sidebarOpen { Sidebar().frame(minWidth: 220, idealWidth: 260, maxWidth: 340) }
                ChatView().frame(minWidth: 350, maxWidth: .infinity).background(SplitPersistence())
                if m.panelOpen { RightPane().frame(minWidth: 320, idealWidth: 380, maxWidth: 740) }
            }
        }
        .toolbar {
            ToolbarItemGroup(placement: .navigation) {
                Button { m.sidebarOpen.toggle() } label: { Image(systemName: "sidebar.left") }.help(m.t(m.sidebarOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar"))
                Button { m.navigate(-1) } label: { Image(systemName: "chevron.left") }.disabled(!m.history.canBack).help(m.t("appbar.back"))
                Button { m.navigate(1) } label: { Image(systemName: "chevron.right") }.disabled(!m.history.canForward).help(m.t("appbar.forward"))
            }
            ToolbarItemGroup {
                Button(m.snapshot["decisions"].rows.isEmpty ? m.t("appbar.no_decisions") : m.t("appbar.decisions", ["n": String(m.snapshot["decisions"].rows.count)])) { m.setPane("overview") }.labelStyle(.titleOnly)
                Button(m.t("chart.title")) { m.sheet = .chart }
                Button(m.t("cc.title") + (m.copies.contains { !$0["read"].flag } ? " •" : "")) { m.sheet = .copies }.help(m.t(m.copies.contains { !$0["read"].flag } ? "appbar.cc" : "appbar.cc_none", ["n": String(m.copies.filter { !$0["read"].flag }.count)]))
                Button { m.panelOpen.toggle() } label: { Image(systemName: "sidebar.right") }.help(m.t(m.panelOpen ? "panel.hide_title" : "page.panel")).accessibilityLabel(m.t(m.panelOpen ? "panel.hide" : "page.panel"))
            }
        }
        .onChange(of: m.sidebarOpen) { m.defaults.set(m.sidebarOpen, forKey: "sidebar") }
        .onChange(of: m.panelOpen) { m.defaults.set(m.panelOpen, forKey: "panel") }
        .onChange(of: m.sheet) { m.activeSpeech?.stop() }
        .sheet(item: $m.sheet) { sheet in SheetContent(sheet: sheet).environmentObject(m) }
        .preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil)
        .font(.system(size: m.preferences["font"].text == "large" ? 16 : m.preferences["font"].text == "small" ? 12 : 14))
        .tint(accent(m.preferences["accent"].text))
        .environment(\.locale, Locale(identifier: m.words.language))
        .accessibilityLabel(m.t("page.titlebar"))
    }
}

func accent(_ name: String) -> Color {
    switch name { case "clay": return Color(red: 0.78, green: 0.39, blue: 0.25); case "ink": return .primary; case "indigo": return .indigo; case "rose": return .pink; case "amber": return .orange; default: return .blue }
}

struct SheetContent: View {
    @EnvironmentObject var m: Model
    let sheet: Model.Sheet
    var body: some View {
        VStack {
            HStack { Spacer(); Button(m.t([Model.Sheet.create, .member, .protocolForm, .forward].contains(sheet) ? "common.cancel" : "common.close")) { m.sheet = nil }.keyboardShortcut(.cancelAction) }
            switch sheet {
            case .create: CreateOrgView()
            case .member: MemberForm()
            case .settings: SettingsView()
            case .copies: CopiesView()
            case .chart: ChartView()
            case .protocolForm: ProtocolForm()
            case .card: MemberCard()
            case .secretary: SecretarySetup()
            case .forward: ForwardForm()
            case .details: DetailsView()
            case .shortcuts: ShortcutsView()
            }
        }.padding(20).frame(minWidth: 580, minHeight: 280).frame(maxHeight: 820)
    }
}

struct Sidebar: View {
    @EnvironmentObject var m: Model
    @FocusState private var focused: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(m.t("common.new_org")) { m.sheet = .create }
            HStack { TextField(m.t("page.search"), text: $m.search).focused($focused); VoiceButton(text: $m.search).labelStyle(.iconOnly) }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text(m.t("page.tree")).font(.caption).foregroundStyle(.secondary)
                    if m.organizations.isEmpty { Text(m.t("side.no_orgs")) }
                    if m.search.isEmpty {
                        Rows(m.organizations.filter { o in o["parent"].text.isEmpty || !m.organizations.contains { $0["id"].text == o["parent"].text } }) { OrgTree(node: $0, ancestors: []) }
                    } else {
                        Rows(m.organizations.filter { [$0["name"].text, $0["purpose"].text].joined().localizedCaseInsensitiveContains(m.search) }) { o in
                            Button(o["name"].text) { m.run { try await m.select(o["id"].text) } }
                        }
                        Rows(m.members.filter { [$0.display, $0["name"].text, $0["role"].text].joined().localizedCaseInsensitiveContains(m.search) }) { who in
                            Button(who.display) { m.run { try await m.select(m.organization, who["name"].text) } }
                        }
                    }
                    Divider(); Text(m.t("page.chat")).font(.caption).foregroundStyle(.secondary)
                    ForEach(m.recent, id: \.self) { recent in
                        if let org = m.organizations.first(where: { $0["id"].text == recent.org }) {
                            Button(org["name"].text + " · " + (recent.member.isEmpty ? m.t("common.group_chat") : recent.member)) { m.run { try await m.select(recent.org, recent.member) } }.lineLimit(1)
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            if m.secretary.isEmpty && !m.organization.isEmpty { Button(m.t("side.set_secretary")) { m.sheet = .secretary }.help(m.t("side.secretary_hint")) }
            Button(m.t("side.profile")) { m.sheet = .settings }.help(m.t("page.me"))
        }.padding(12).accessibilityLabel(m.t("page.side")).onChange(of: m.focusSearch) { if m.focusSearch { focused = true; m.focusSearch = false } }
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
                Button { m.toggleFold(id) } label: { Image(systemName: m.folded.contains(id) ? "chevron.right" : "chevron.down") }.buttonStyle(.plain).accessibilityLabel(m.t("common.collapse"))
                Button(node["name"].text) { m.run { try await m.select(id) } }.fontWeight(m.organization == id ? .semibold : .regular)
                if node["cabinet"].flag { Image(systemName: "star.fill").help(m.t("org.cabinet_chip")) }
            }
            if !m.folded.contains(id) {
                if m.organization == id {
                    VStack(alignment: .leading, spacing: m.preferences["density"].text == "compact" ? 4 : 10) {
                        Button("# " + m.t("common.group_chat") + (m.unread() > 0 ? " · " + String(m.unread()) : "")) { m.run { try await m.select(id) } }.help(m.lastLine())
                        Rows(m.members.sorted { $0["secretary"].flag && !$1["secretary"].flag }) { who in
                            HStack {
                                Button { m.run { try await m.select(id, who["name"].text) } } label: {
                                    HStack(alignment: .top) {
                                        Avatar(member: who["name"].text, size: 26)
                                        VStack(alignment: .leading) {
                                            Text(who.display).fontWeight(m.member == who["name"].text ? .semibold : .regular)
                                            if who["secretary"].flag { Text(m.t("common.secretary")).font(.caption) }
                                            if who["leader"].flag { Text(m.t("common.leader")).font(.caption) }
                                            Text(m.stateLabel(who["state"].text) + " · " + who["role"].text).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                            if !who["doing"].text.isEmpty { Text(m.t("side.doing", ["doing": who["doing"].text])).font(.caption).lineLimit(1) }
                                            Text(m.lastLine(who["name"].text)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                        }
                                        if m.unread(who["name"].text) > 0 { Text(String(m.unread(who["name"].text))).font(.caption).padding(4).background(.tint.opacity(0.15), in: Capsule()) }
                                    }
                                }
                            }.contextMenu { Button(m.t("chat.card")) { m.openCard(who["name"].text) }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: who["name"].text) } }
                        }
                        Button("+ " + m.t("common.add_member")) { m.openMemberForm() }
                    }.padding(.leading, 20)
                }
                Rows(m.organizations.filter { $0["parent"].text == id && !ancestors.union([id]).contains($0["id"].text) }) { child in
                    AnyView(OrgTree(node: child, ancestors: ancestors.union([id])).padding(.leading, 14))
                }
            }
        }.buttonStyle(.plain).opacity(!node["status"].text.isEmpty && node["status"].text != "active" ? 0.6 : 1)
    }
}

struct RightPane: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack {
            Picker("", selection: $m.pane) {
                Text(m.t("panel.overview")).tag("overview").help(m.t("appbar.pane_shortcut", ["pane": m.t("panel.overview"), "key": "⌥1"]))
                Text(m.t("panel.workspace")).tag("workspace").help(m.t("appbar.pane_shortcut", ["pane": m.t("panel.workspace"), "key": "⌥2"]))
                Text(m.t("common.file")).tag("files").help(m.t("appbar.pane_shortcut", ["pane": m.t("common.file"), "key": "⌥3"]))
                if !m.threadID.isEmpty { Text(m.t("panel.thread")).tag("thread") }
            }.pickerStyle(.segmented)
            switch m.pane {
            case "workspace": WorkspaceView()
            case "files": FilePreview()
            case "thread": ThreadView()
            default: ScrollView { Overview() }
            }
        }.padding(12).help(m.t("panel.resize"))
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}
