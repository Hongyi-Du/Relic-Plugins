import SwiftUI
import AppKit
import RelicCore

struct Rows<Content: View>: View {
    let nodes: [Node]
    @ViewBuilder let content: (Node) -> Content
    init(_ nodes: [Node], @ViewBuilder content: @escaping (Node) -> Content) { self.nodes = nodes; self.content = content }
    var body: some View { ForEach(NodeRow.identify(nodes)) { content($0.node) } }
}

struct MainView: View {
    @EnvironmentObject var m: Model
    @State private var resizingPanel: CGFloat?
    @State private var resizeStart: CGFloat?
    private var panelKey: String { m.pane == "files" ? "width.files" : "width.panel" }
    private var floatingPanel: Bool { InspectorGeometry.overlaysConversation(window: m.windowSize.width) }
    private var panelWidth: CGFloat {
        InspectorGeometry.width(window: m.windowSize.width, saved: resizingPanel ?? CGFloat(m.defaults.double(forKey: panelKey)), files: m.pane == "files")
    }
    var body: some View {
        GeometryReader { geometry in
        VStack(spacing: 0) {
            AppToolbar().measuredRegion("header").zIndex(50)
            if !m.error.isEmpty { HStack { Text(m.error).textSelection(.enabled); Spacer(); Button(m.t("common.close")) { m.error = "" } }.padding(8).background(.red.opacity(0.12)) }
            if !m.notice.isEmpty { HStack { Text(m.notice); Spacer(); Button(m.t("common.close")) { m.notice = "" } }.padding(8) }
            if !m.ready { ProgressView().padding(); Button(m.t("appmenu.reload")) { Task { await m.start() } } }
            HStack(spacing: 0) {
                if m.sidebarOpen { Sidebar().frame(width: 276).measuredRegion("sidebar") }
                ChatView().frame(minWidth: 0, maxWidth: .infinity).measuredRegion("conversation")
                if m.panelOpen && !floatingPanel { inspector }
            }.frame(maxHeight: .infinity).overlay(alignment: .trailing) { if m.panelOpen && floatingPanel { inspector } }
        }.frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading).modifier(RecordedSurface(background: RelicStyle.background, kind: "region")).foregroundStyle(RelicStyle.ink)
        .onAppear { m.windowSize = geometry.size }.onChange(of: geometry.size) { m.windowSize = geometry.size; m.mentionEditor?.closeMentions(); m.inputSuggestions = nil; m.recipientPicker = false; m.appMenu = nil }
        .onChange(of: m.sidebarOpen) { m.defaults.set(m.sidebarOpen, forKey: "sidebar") }
        .onChange(of: m.panelOpen) { m.defaults.set(m.panelOpen, forKey: "panel") }
        .onChange(of: m.sheet) { m.activeSpeech?.stop(); if m.sheet != nil { m.recipientPicker = false; m.mentionEditor?.closeMentions() } }
        .onChange(of: m.focusSearch) { if m.focusSearch { m.mentionEditor?.closeMentions() } }
        .onChange(of: m.appMenu) { if m.appMenu != nil { m.mentionEditor?.closeMentions() } }
        .onChange(of: m.pane) { resizingPanel = nil; resizeStart = nil }
        .overlay { if !m.mentionItems.isEmpty { MentionSuggestions() } }
        .overlay { if m.recipientPicker { RecipientLayer() } }
        .overlay { if let sheet = m.sheet { DialogLayer(sheet: sheet) } }
        .overlay { if m.inputSuggestions != nil { InputSuggestionsLayer() } }
        .preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil)
        .font(RelicStyle.font(m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14, weight: 400))
        .tracking(0)
        .tint(accent(m.preferences["accent"].text))
        .environment(\.locale, Locale(identifier: m.words.language))
        .coordinateSpace(name: "relic-window")
        .background(ScrollAppearance())
        .background(InitialWindowFocus().frame(width: 0, height: 0))
        }
    }
    private var inspector: some View {
        RightPane(floating: floatingPanel).frame(width: min(panelWidth, m.windowSize.width - 48)).measuredRegion("right-pane")
            .overlay(alignment: .leading) {
                Color.clear.frame(width: 6).contentShape(Rectangle())
                    .onHover { hovering in if hovering { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() } }
                    .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                        if resizeStart == nil { resizeStart = panelWidth }
                        resizingPanel = InspectorGeometry.width(window: m.windowSize.width, saved: (resizeStart ?? panelWidth) - value.translation.width, files: m.pane == "files")
                    }.onEnded { _ in m.defaults.set(Double(panelWidth), forKey: panelKey); resizeStart = nil; resizingPanel = nil })
                    .help(m.t("panel.resize"))
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
                        TextButton(m.t(label), size: 13, weight: 400, height: 28, padding: 9) { m.appMenu = m.appMenu == key ? nil : key }
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
                    IconButton(title: m.t("appbar.pane_shortcut", ["pane": m.t(pane.1), "key": "Option+" + String(index + 1)]), icon: ["org", "work", "file"][index], selected: m.panelOpen && m.pane == pane.0, size: 16, height: 28) {
                        if m.panelOpen && m.pane == pane.0 { m.panelOpen = false } else { m.setPane(pane.0) }
                    }
                }
            }
            let title = m.organization.isEmpty ? m.t("common.app_name") : m.snapshot["org"]["name"].text + " · " + (m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("common.secretary") : m.name(m.member))
            Text(title).font(RelicStyle.font(12.5, weight: 400)).foregroundStyle(RelicStyle.muted).lineLimit(1).frame(maxWidth: m.windowSize.width * 0.4).help(title).allowsHitTesting(false)
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
    var body: some View {
        Group {
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
        }.buttonStyle(ReferenceButtonStyle()).controlSize(.regular)
    }
}

struct RightPane: View {
    @EnvironmentObject var m: Model
    var floating = false
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                ScrollView(.horizontal) {
                    HStack(spacing: 2) {
                        ForEach(Array((Choices.panes + (m.threadID.isEmpty ? [] : [("thread", "panel.thread")])).enumerated()), id: \.offset) { index, pane in
                            Button { m.setPane(pane.0) } label: {
                                HStack(spacing: 5) {
                                    ReferenceIcon(name: ["org", "work", "file", "thread"][index], size: 15, color: m.pane == pane.0 ? RelicStyle.ink : RelicStyle.secondary)
                                    ReferenceLabel(m.t(pane.1), size: 12.5, weight: m.pane == pane.0 ? 600 : 400)
                                    if pane.0 == "thread" { Button { m.closeThread() } label: { ReferenceIcon(name: "x", size: 12, color: RelicStyle.muted).frame(width: 16, height: 16) }.buttonStyle(.plain).help(m.t("panel.close_thread")) }
                                }.padding(.horizontal, 9).frame(height: 28)
                            }.buttonStyle(QuietButtonStyle(selected: m.pane == pane.0, selectionApplicable: true)).accessibilityIdentifier("relic-tab/" + pane.0).accessibilityAddTraits(m.pane == pane.0 ? [.isSelected] : [])
                        }
                    }
                }.scrollIndicators(.hidden)
                IconButton(title: m.t("panel.hide_title"), icon: "x", size: 16) { m.panelOpen = false }.accessibilityLabel(m.t("panel.hide"))
            }.padding(.leading, 8).padding(.trailing, 6).frame(height: 44)
                .overlay(alignment: .bottom) { RelicStyle.line.frame(height: 1) }
            switch m.pane {
            case "workspace": WorkspaceView()
            case "files": FilePreview()
            case "thread": ThreadView()
            default: ScrollView { if !m.snapshot["org"].isNull { Overview() } }
            }
        }.frame(maxHeight: .infinity, alignment: .top)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 1, bottom: 0, trailing: 0), kind: "region", shadows: floating ? SurfaceShadow.dialog : [])).help(m.t("panel.resize"))
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}
