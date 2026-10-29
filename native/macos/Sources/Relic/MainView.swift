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
        GeometryReader { geometry in
        VStack(spacing: 0) {
            AppToolbar().measuredRegion("header").zIndex(50)
            if !m.error.isEmpty { HStack { Text(m.error).textSelection(.enabled); Spacer(); Button(m.t("common.close")) { m.error = "" } }.padding(8).background(.red.opacity(0.12)) }
            if !m.notice.isEmpty { HStack { Text(m.notice); Spacer(); Button(m.t("common.close")) { m.notice = "" } }.padding(8) }
            if !m.ready { ProgressView().padding(); Button(m.t("appmenu.reload")) { Task { await m.start() } } }
            HSplitView {
                if m.sidebarOpen { Sidebar().frame(minWidth: 276, idealWidth: 276, maxWidth: 340).measuredRegion("sidebar") }
                ChatView().frame(minWidth: 320, maxWidth: .infinity).background(SplitPersistence())
                if m.panelOpen { RightPane().frame(minWidth: m.pane == "files" ? min(460, max(320, m.windowSize.width - (m.sidebarOpen ? 276 : 0) - 322)) : 320, idealWidth: m.pane == "files" ? 520 : 340, maxWidth: 740).measuredRegion("right-pane") }
            }.frame(maxHeight: .infinity)
        }.frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading).modifier(RecordedSurface(background: RelicStyle.background, kind: "region")).foregroundStyle(RelicStyle.ink)
        .onAppear { m.windowSize = geometry.size }.onChange(of: geometry.size) { m.windowSize = geometry.size }
        .onChange(of: m.sidebarOpen) { m.defaults.set(m.sidebarOpen, forKey: "sidebar") }
        .onChange(of: m.panelOpen) { m.defaults.set(m.panelOpen, forKey: "panel") }
        .onChange(of: m.sheet) { m.activeSpeech?.stop() }
        .sheet(item: $m.sheet) { sheet in SheetContent(sheet: sheet).environmentObject(m) }
        .preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil)
        .font(.system(size: m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14))
        .tint(accent(m.preferences["accent"].text))
        .environment(\.locale, Locale(identifier: m.words.language))
        .accessibilityIdentifier("relic-root")
        }
    }
}

struct AppToolbar: View {
    @EnvironmentObject var m: Model
    @State private var anchors: [String: CGRect] = [:]
    private let menus = [("file", "common.file"), ("edit", "appmenu.edit"), ("view", "appmenu.view"), ("help", "appmenu.help")]
    var body: some View {
        ZStack {
            HStack(spacing: 2) {
                RelicLogo().padding(.leading, 6).padding(.trailing, 8)
                IconButton(title: m.t(m.sidebarOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar"), icon: "sidebar", size: 16, height: 28) { m.sidebarOpen.toggle() }
                IconButton(title: m.t("appbar.back"), icon: "back", size: 16, height: 28) { m.navigate(-1) }.disabled(!m.history.canBack)
                IconButton(title: m.t("appbar.forward"), icon: "fwd", size: 16, height: 28) { m.navigate(1) }.disabled(!m.history.canForward)
                HStack(spacing: 0) {
                    ForEach(menus, id: \.0) { key, label in
                        Button { m.appMenu = m.appMenu == key ? nil : key } label: { Text(m.t(label)).font(.system(size: 13)).padding(.horizontal, 9).frame(height: 28) }
                            .buttonStyle(QuietButtonStyle(selected: m.appMenu == key))
                            .background(GeometryReader { proxy in Color.clear.preference(key: MenuAnchors.self, value: [key: proxy.frame(in: .named("appbar"))]) })
                            .onHover { over in if over && m.appMenu != nil { m.appMenu = key } }
                    }
                }.padding(.leading, 4).accessibilityElement(children: .contain).accessibilityLabel(m.t("appbar.menus"))
                Spacer(minLength: 10)
                IconButton(title: m.snapshot["decisions"].rows.isEmpty ? m.t("appbar.no_decisions") : m.t("appbar.decisions", ["n": String(m.snapshot["decisions"].rows.count)]), icon: "bell", badge: m.snapshot["decisions"].rows.count, size: 16, height: 28) { m.setPane("overview") }
                IconButton(title: m.t(m.copies.contains { !$0["read"].flag } ? "appbar.cc" : "appbar.cc_none", ["n": String(m.copies.filter { !$0["read"].flag }.count)]), icon: "cc", badge: m.copies.filter { !$0["read"].flag }.count, size: 16, height: 28) { m.sheet = .copies }
                RelicStyle.border.frame(width: 1, height: 16).padding(.horizontal, 4)
                ForEach(Array(Choices.panes.enumerated()), id: \.offset) { index, pane in
                    IconButton(title: m.t("appbar.pane_shortcut", ["pane": m.t(pane.1), "key": "⌥" + String(index + 1)]), icon: ["org", "work", "file"][index], selected: m.panelOpen && m.pane == pane.0, size: 16, height: 28) {
                        if m.panelOpen && m.pane == pane.0 { m.panelOpen = false } else { m.setPane(pane.0) }
                    }
                }
            }
            let title = m.organization.isEmpty ? "Relic" : m.snapshot["org"]["name"].text + " · " + (m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("common.secretary") : m.name(m.member))
            Text(title).font(.system(size: 12.5)).foregroundStyle(RelicStyle.muted).lineLimit(1).frame(maxWidth: m.windowSize.width * 0.4).help(title).allowsHitTesting(false)
        }.padding(.leading, 6).padding(.trailing, 8).frame(height: 40)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
            .coordinateSpace(name: "appbar").onPreferenceChange(MenuAnchors.self) { anchors = $0 }
            .overlay(alignment: .topLeading) {
                if let key = m.appMenu, let anchor = anchors[key] {
                    ActionMenu().environmentObject(m).measuredRegion("menu").offset(x: max(4, min(anchor.minX, m.windowSize.width - 270)), y: anchor.maxY + 4)
                }
            }
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.titlebar"))
    }
}

private struct MenuAnchors: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) { value.merge(nextValue(), uniquingKeysWith: { _, new in new }) }
}

func accent(_ name: String) -> Color {
    switch name { case "ink": return RelicStyle.color(0x3A3936, 0xD9D6CF); case "indigo": return RelicStyle.color(0x5B61D6, 0x5B61D6); case "rose": return RelicStyle.color(0xC4456C, 0xC4456C); case "amber": return RelicStyle.color(0xB9821D, 0xB9821D); case "blue": return RelicStyle.color(0x2F6BD8, 0x2F6BD8); default: return RelicStyle.accent }
}

struct SheetContent: View {
    @EnvironmentObject var m: Model
    let sheet: Model.Sheet
    private var width: CGFloat { min(sheet == .chart ? m.windowSize.width - 40 : [Model.Sheet.settings, .details].contains(sheet) ? 920 : sheet == .copies ? 760 : sheet == .forward ? 720 : [Model.Sheet.create, .secretary, .card].contains(sheet) ? 520 : 620, max(480, m.windowSize.width - 40)) }
    private var height: CGFloat { min(sheet == .chart ? m.windowSize.height - 60 : sheet == .create ? 400 : sheet == .secretary ? 440 : sheet == .card ? 600 : sheet == .copies ? CGFloat(min(640, 160 + max(1, m.copies.count) * (m.expandRules ? 320 : 210))) : sheet == .shortcuts ? 480 : 640, max(360, m.windowSize.height - 60)) }
    var body: some View {
        VStack(spacing: 12) {
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
        }.padding(20).frame(width: width, height: height).overlay(alignment: .topTrailing) { IconButton(title: m.t([Model.Sheet.create, .member, .protocolForm, .forward].contains(sheet) ? "common.cancel" : "common.close"), icon: "x") { m.sheet = nil }.keyboardShortcut(.cancelAction).padding(10) }
            .background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 16)).clipShape(RoundedRectangle(cornerRadius: 16)).background(SheetSurface()).buttonStyle(.bordered).controlSize(.regular)
            .tint(accent(m.preferences["accent"].text)).preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil).environment(\.locale, Locale(identifier: m.words.language))
    }
}

struct RightPane: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                ScrollView(.horizontal) {
                    HStack(spacing: 2) {
                        ForEach(Array((Choices.panes + (m.threadID.isEmpty ? [] : [("thread", "panel.thread")])).enumerated()), id: \.offset) { index, pane in
                            Button { m.setPane(pane.0) } label: {
                                HStack(spacing: 5) {
                                    ReferenceIcon(name: ["org", "work", "file", "thread"][index], size: 15, color: m.pane == pane.0 ? RelicStyle.ink : RelicStyle.secondary)
                                    Text(m.t(pane.1)).font(.system(size: 12.5, weight: m.pane == pane.0 ? .semibold : .regular)).lineLimit(1)
                                    if pane.0 == "thread" { Button { m.closeThread() } label: { ReferenceIcon(name: "x", size: 12, color: RelicStyle.muted).frame(width: 16, height: 16) }.buttonStyle(.plain).help(m.t("panel.close_thread")) }
                                }.padding(.horizontal, 9).frame(height: 28)
                            }.buttonStyle(QuietButtonStyle(selected: m.pane == pane.0)).accessibilityIdentifier("relic-tab/" + pane.0).accessibilityAddTraits(m.pane == pane.0 ? [.isSelected] : [])
                        }
                    }
                }.scrollIndicators(.hidden)
                IconButton(title: m.t("panel.hide_title"), icon: "x", size: 16) { m.panelOpen = false }.accessibilityLabel(m.t("panel.hide"))
            }.padding(.leading, 8).padding(.trailing, 6).frame(height: 44)
                .overlay(alignment: .bottom) { RelicStyle.line.frame(height: 1) }
            switch m.pane {
            case "workspace": WorkspaceView()
            case "files": FilePreview().padding(14)
            case "thread": ThreadView()
            default: ScrollView { Overview() }
            }
        }.frame(maxHeight: .infinity, alignment: .top)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 1, bottom: 0, trailing: 0), kind: "region")).help(m.t("panel.resize"))
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}
