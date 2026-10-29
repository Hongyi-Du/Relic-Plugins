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
                if m.sidebarOpen { Sidebar().frame(minWidth: 208, idealWidth: 276, maxWidth: 320) }
                ChatView().frame(minWidth: 320, maxWidth: .infinity).background(SplitPersistence())
                if m.panelOpen { RightPane().frame(minWidth: 280, idealWidth: 320, maxWidth: 740) }
            }
        }.background(RelicStyle.background).foregroundStyle(RelicStyle.ink)
        .toolbar {
            ToolbarItemGroup(placement: .navigation) {
                Button { m.sidebarOpen.toggle() } label: { Image(systemName: "sidebar.left") }.help(m.t(m.sidebarOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar"))
                Button { m.navigate(-1) } label: { Image(systemName: "chevron.left") }.disabled(!m.history.canBack).help(m.t("appbar.back"))
                Button { m.navigate(1) } label: { Image(systemName: "chevron.right") }.disabled(!m.history.canForward).help(m.t("appbar.forward"))
            }
            ToolbarItemGroup {
                IconButton(title: m.snapshot["decisions"].rows.isEmpty ? m.t("appbar.no_decisions") : m.t("appbar.decisions", ["n": String(m.snapshot["decisions"].rows.count)]), icon: "tray", badge: m.snapshot["decisions"].rows.count) { m.setPane("overview") }
                IconButton(title: m.t("chart.title"), icon: "point.3.connected.trianglepath.dotted") { m.sheet = .chart }
                IconButton(title: m.t("cc.title") + " · " + m.t(m.copies.contains { !$0["read"].flag } ? "appbar.cc" : "appbar.cc_none", ["n": String(m.copies.filter { !$0["read"].flag }.count)]), icon: "doc.on.doc", badge: m.copies.filter { !$0["read"].flag }.count) { m.sheet = .copies }
                Button { m.panelOpen.toggle() } label: { Image(systemName: "sidebar.right") }.help(m.t(m.panelOpen ? "panel.hide_title" : "page.panel")).accessibilityLabel(m.t(m.panelOpen ? "panel.hide" : "page.panel"))
            }
        }
        .onChange(of: m.sidebarOpen) { m.defaults.set(m.sidebarOpen, forKey: "sidebar") }
        .onChange(of: m.panelOpen) { m.defaults.set(m.panelOpen, forKey: "panel") }
        .onChange(of: m.sheet) { m.activeSpeech?.stop() }
        .sheet(item: $m.sheet) { sheet in SheetContent(sheet: sheet).environmentObject(m) }
        .preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil)
        .font(.system(size: m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14))
        .tint(accent(m.preferences["accent"].text))
        .environment(\.locale, Locale(identifier: m.words.language))
        .accessibilityLabel(m.t("page.titlebar"))
    }
}

func accent(_ name: String) -> Color {
    switch name { case "ink": return RelicStyle.ink; case "indigo": return Color(red: 0.36, green: 0.38, blue: 0.84); case "rose": return .pink; case "amber": return .orange; case "blue": return .blue; default: return RelicStyle.accent }
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
        }.padding(20).frame(minWidth: 560, idealWidth: sheet == .chart ? 850 : 620, maxWidth: 980, minHeight: 280, maxHeight: 620)
            .background(RelicStyle.background).buttonStyle(.bordered).controlSize(.regular)
    }
}

struct Sidebar: View {
    @EnvironmentObject var m: Model
    @FocusState private var focused: Bool
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 9) {
                Image(systemName: "r.square.fill").font(.system(size: 25)).foregroundStyle(RelicStyle.accent)
                Text("Relic").font(.system(size: 16, weight: .semibold)); Spacer()
                IconButton(title: m.t("common.new_org"), icon: "square.and.pencil") { m.sheet = .create }
            }.padding(.horizontal, 14).frame(height: 50)
            VStack(spacing: 5) {
                Button { m.sheet = .create } label: { Label(m.t("common.new_org"), systemImage: "plus").frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).frame(height: 34) }.buttonStyle(QuietButtonStyle())
                HStack(spacing: 7) {
                    Image(systemName: "magnifyingglass").foregroundStyle(RelicStyle.muted)
                    TextField(m.t("page.search"), text: $m.search).textFieldStyle(.plain).focused($focused)
                    VoiceButton(text: $m.search).labelStyle(.iconOnly)
                }.padding(.horizontal, 10).frame(height: 34).background(RelicStyle.hover, in: RoundedRectangle(cornerRadius: 8))
            }.padding(.horizontal, 8).padding(.bottom, 5)
            List {
                Text(m.t("page.tree")).font(.system(size: 12)).foregroundStyle(RelicStyle.muted).padding(.horizontal, 10).padding(.top, 9).listRowSeparator(.hidden)
                if m.organizations.isEmpty { Text(m.t("side.no_orgs")).font(.caption).foregroundStyle(RelicStyle.muted) }
                if m.search.isEmpty {
                    Rows(m.organizations.filter { o in o["parent"].text.isEmpty || !m.organizations.contains { $0["id"].text == o["parent"].text } }) { OrgTree(node: $0, ancestors: []).listRowSeparator(.hidden).listRowInsets(EdgeInsets(top: 2, leading: 0, bottom: 2, trailing: 0)) }
                } else {
                    Rows(m.organizations.filter { [$0["name"].text, $0["purpose"].text].joined().localizedCaseInsensitiveContains(m.search) }) { o in
                        Button(o["name"].text) { m.run { try await m.select(o["id"].text) } }.buttonStyle(.plain).lineLimit(2).help(o["name"].text)
                    }
                    Rows(m.members.filter { [$0.display, $0["name"].text, $0["role"].text].joined().localizedCaseInsensitiveContains(m.search) }) { who in MemberRow(who: who) }
                }
                if !m.recent.isEmpty {
                    Text(m.t("page.chat")).font(.system(size: 12)).foregroundStyle(RelicStyle.muted).padding(.horizontal, 10).padding(.top, 12).listRowSeparator(.hidden)
                    ForEach(m.recent, id: \.self) { recent in
                        if let org = m.organizations.first(where: { $0["id"].text == recent.org }) {
                            let title = org["name"].text + " · " + (recent.member.isEmpty ? m.t("common.group_chat") : recent.member)
                            Button { m.run { try await m.select(recent.org, recent.member) } } label: { Label(title, systemImage: "bubble.left").lineLimit(1).padding(7).frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(QuietButtonStyle()).help(title).listRowSeparator(.hidden)
                        }
                    }
                }
            }.listStyle(.sidebar).scrollContentBackground(.hidden).environment(\.defaultMinListRowHeight, 0)
            if m.secretary.isEmpty && !m.organization.isEmpty { Button(m.t("side.set_secretary")) { m.sheet = .secretary }.buttonStyle(.link).font(.caption).padding(8).help(m.t("side.secretary_hint")) }
            Divider().overlay(RelicStyle.line)
            HStack(spacing: 7) {
                Button { m.sheet = .settings } label: {
                    HStack(spacing: 10) { Avatar(member: "human", size: 30); VStack(alignment: .leading, spacing: 2) { Text(m.name("human")).font(.system(size: 13, weight: .semibold)); Text(m.t("side.profile")).font(.system(size: 11)).foregroundStyle(RelicStyle.muted) }; Spacer(minLength: 0) }.padding(6)
                }.buttonStyle(QuietButtonStyle()).help(m.t("page.me"))
                IconButton(title: m.t("common.settings"), icon: "gearshape") { m.sheet = .settings }
            }.padding(8)
        }.background(RelicStyle.sidebar).accessibilityLabel(m.t("page.side"))
            .onChange(of: m.focusSearch) { if m.focusSearch { focused = true; m.focusSearch = false } }
    }
}

struct MemberRow: View {
    @EnvironmentObject var m: Model
    let who: Node
    var body: some View {
        let name = who["name"].text
        let subtitle = who["doing"].text.isEmpty ? (m.lastLine(name).isEmpty ? who["role"].text : m.lastLine(name)) : m.t("side.doing", ["doing": who["doing"].text])
        Button { m.run { try await m.select(m.organization, name) } } label: {
            HStack(spacing: 9) {
                Avatar(member: name, size: 28).overlay(alignment: .bottomTrailing) { Circle().fill(RelicStyle.state(who["state"].text)).frame(width: 8, height: 8).overlay(Circle().stroke(RelicStyle.sidebar, lineWidth: 2)).offset(x: 1, y: 1) }
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 4) { Text(who.display).font(.system(size: 13, weight: .medium)).lineLimit(1); if who["secretary"].flag { SmallBadge(text: m.t("common.secretary"), color: RelicStyle.violet) }; if who["leader"].flag { Image(systemName: "star.fill").font(.system(size: 9)).foregroundStyle(RelicStyle.accent).help(m.t("common.leader")) } }
                    Text(subtitle).font(.system(size: 11.5)).foregroundStyle(RelicStyle.muted).lineLimit(1)
                }.frame(maxWidth: .infinity, alignment: .leading)
                if m.unread(name) > 0 { Text(String(m.unread(name))).font(.system(size: 10, weight: .semibold)).padding(4).foregroundStyle(.white).background(RelicStyle.accent, in: Circle()) }
            }.padding(.horizontal, 7).padding(.vertical, 6)
        }.buttonStyle(QuietButtonStyle(selected: m.member == name)).help(who.display + " · " + m.stateLabel(who["state"].text) + "\n" + subtitle)
            .contextMenu { Button(m.t("chat.card")) { m.openCard(name) }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: name) } }
    }
}

struct OrgTree: View {
    @EnvironmentObject var m: Model
    let node: Node
    let ancestors: Set<String>
    var body: some View {
        let id = node["id"].text
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                Button { m.toggleFold(id) } label: { Image(systemName: m.folded.contains(id) ? "chevron.right" : "chevron.down").font(.system(size: 10, weight: .semibold)).frame(width: 18, height: 28) }.buttonStyle(QuietButtonStyle()).accessibilityLabel(m.t("common.collapse"))
                Button { m.run { try await m.select(id) } } label: {
                    HStack(spacing: 7) {
                        Image(systemName: node["cabinet"].flag ? "building.columns" : "folder").font(.system(size: 12)).frame(width: 22, height: 22).background(RelicStyle.hover, in: RoundedRectangle(cornerRadius: 6))
                        Text(node["name"].text).font(.system(size: 13, weight: .semibold)).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(.vertical, 5).padding(.trailing, 5)
                }.buttonStyle(.plain).help(node["name"].text)
            }.padding(.horizontal, 4).background(m.organization == id ? RelicStyle.selected.opacity(0.5) : .clear, in: RoundedRectangle(cornerRadius: 8))
            if !m.folded.contains(id) {
                if m.organization == id {
                    VStack(alignment: .leading, spacing: 1) {
                        Button { m.run { try await m.select(id) } } label: {
                            HStack(spacing: 9) { Image(systemName: "person.3.fill").font(.system(size: 12)).frame(width: 28, height: 28).background(RelicStyle.hover, in: RoundedRectangle(cornerRadius: 8)); Text(m.t("common.group_chat")).font(.system(size: 13, weight: .medium)); Spacer(minLength: 0); if m.unread() > 0 { SmallBadge(text: String(m.unread()), color: RelicStyle.accent) } }.padding(7)
                        }.buttonStyle(QuietButtonStyle(selected: m.member.isEmpty)).help(m.lastLine())
                        Rows(m.members.sorted { $0["secretary"].flag && !$1["secretary"].flag }) { MemberRow(who: $0) }
                        Button { m.openMemberForm() } label: { Label(m.t("common.add_member"), systemImage: "plus").font(.system(size: 12)).foregroundStyle(RelicStyle.muted).padding(8).frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(QuietButtonStyle())
                    }.padding(.leading, 10)
                }
                Rows(m.organizations.filter { $0["parent"].text == id && !ancestors.union([id]).contains($0["id"].text) }) { child in AnyView(OrgTree(node: child, ancestors: ancestors.union([id])).padding(.leading, 14)) }
            }
        }.opacity(!node["status"].text.isEmpty && node["status"].text != "active" ? 0.6 : 1)
    }
}

struct RightPane: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $m.pane) {
                Text(m.t("panel.overview")).tag("overview").help(m.t("appbar.pane_shortcut", ["pane": m.t("panel.overview"), "key": "⌥1"]))
                Text(m.t("panel.workspace")).tag("workspace").help(m.t("appbar.pane_shortcut", ["pane": m.t("panel.workspace"), "key": "⌥2"]))
                Text(m.t("common.file")).tag("files").help(m.t("appbar.pane_shortcut", ["pane": m.t("common.file"), "key": "⌥3"]))
                if !m.threadID.isEmpty { Text(m.t("panel.thread")).tag("thread") }
            }.pickerStyle(.segmented).padding(.horizontal, 12).padding(.vertical, 10)
            Divider().overlay(RelicStyle.line)
            switch m.pane {
            case "workspace": WorkspaceView()
            case "files": FilePreview()
            case "thread": ThreadView()
            default: ScrollView { Overview().padding(16) }
            }
        }.frame(maxHeight: .infinity, alignment: .top).background(RelicStyle.background).help(m.t("panel.resize"))
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}
