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
    @State private var inspectorHandleHovered = false
    @State private var displayedOrganization: String?
    @State private var revealPhase = 0
    @StateObject private var panelResizeTrace = PanelResizeTrace()
    private var panelKey: String { m.pane == "files" ? "width.files" : "width.panel" }
    private var floatingPanel: Bool { InspectorGeometry.overlaysConversation(window: m.windowSize.width) }
    private var loadingOrganization: Bool { !m.ready || !m.organization.isEmpty && m.snapshot["org"].isNull }
    private var organizationKey: String? { loadingOrganization ? nil : m.organization }
    private var contentPhase: Int { displayedOrganization == organizationKey ? revealPhase : 0 }
    private var panelWidth: CGFloat {
        InspectorGeometry.width(window: m.windowSize.width, saved: resizingPanel ?? CGFloat(m.defaults.double(forKey: panelKey)), files: m.pane == "files")
    }
    var body: some View {
        GeometryReader { geometry in
        VStack(spacing: 0) {
            AppToolbar().measuredRegion("header", createsAccessibilityContainer: false).zIndex(50)
            if !m.error.isEmpty && !m.ready { HStack { Text(m.error).textSelection(.enabled); Spacer(); Button(m.t("common.close")) { m.error = "" } }.padding(8).background(.red.opacity(0.12)) }
            if !m.ready && !m.error.isEmpty { Button(m.t("appmenu.reload")) { Task { await m.start() } } }
            HStack(spacing: 0) {
                if m.sidebarOpen { Sidebar(revealMembers: contentPhase >= 1).frame(width: InspectorGeometry.sidebarWidth(window: geometry.size.width)).measuredRegion("sidebar", createsAccessibilityContainer: false) }
                if loadingOrganization || contentPhase < 2 { ProgressView(m.t("common.loading")).frame(maxWidth: .infinity, maxHeight: .infinity) }
                else {
                    ChatView().frame(minWidth: 0, maxWidth: .infinity).measuredRegion("conversation", createsAccessibilityContainer: false)
                }
                if !loadingOrganization && m.panelOpen && !floatingPanel {
                    if contentPhase >= 3 { inspector }
                    else { Color.clear.frame(width: min(panelWidth, m.windowSize.width - 48)) }
                }
            }.frame(maxHeight: .infinity).overlay(alignment: .trailing) { if !loadingOrganization && contentPhase >= 3 && m.panelOpen && floatingPanel { inspector } }
        }.frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading).modifier(RecordedSurface(background: RelicStyle.background, kind: "region", owner: InitialWindowFocus.surfaceIdentity)).foregroundStyle(RelicStyle.ink)
        .onAppear { m.windowSize = geometry.size }.onChange(of: geometry.size) { m.windowSize = geometry.size; m.mentionEditor?.closeMentions(); m.inputSuggestions = nil; m.recipientPicker = false; m.appMenu = nil }
        .task(id: organizationKey) {
            let ticket = PerformanceRendering.beginSurface()
            defer { PerformanceRendering.endSurface(ticket) }
            displayedOrganization = organizationKey; revealPhase = 0
            guard organizationKey != nil else { return }
            // Give the native run loop a frame between materializing each pane.
            // All panes retain their final space, so the chat does not wrap
            // twice. The same progressive mounting runs in the shipped app.
            for phase in 1...3 {
                do { try await Task.sleep(for: .milliseconds(32)) } catch { return }
                revealPhase = phase
            }
        }
        .onChange(of: m.sidebarOpen) { m.defaults.set(m.sidebarOpen, forKey: "sidebar") }
        .onChange(of: m.panelOpen) { if !floatingPanel { m.defaults.set(m.panelOpen, forKey: "panel") } }
        .onChange(of: m.sheet) { m.activeSpeech?.stop(); if m.sheet != nil { m.recipientPicker = false; m.mentionEditor?.closeMentions() } }
        .onChange(of: m.focusSearch) { if m.focusSearch { m.mentionEditor?.closeMentions() } }
        .onChange(of: m.appMenu) { if m.appMenu != nil { m.mentionEditor?.closeMentions(); m.recipientPicker = false } }
        .onChange(of: m.recipientPicker) { if m.recipientPicker { m.appMenu = nil } }
        .onChange(of: m.pane) { resizingPanel = nil; resizeStart = nil }
        .overlay { if !m.mentionItems.isEmpty { MentionSuggestions() } }
        .overlay { if m.recipientPicker { RecipientLayer() } }
        .overlay { if let sheet = m.sheet { DialogLayer(sheet: sheet) } }
        .overlay { if m.inputSuggestions != nil { InputSuggestionsLayer() } }
        .overlay(alignment: .bottom) { NativeToasts() }
        .preferredColorScheme(m.preferences["theme"].text == "dark" ? .dark : m.preferences["theme"].text == "light" ? .light : nil)
        .font(RelicStyle.font(m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14, weight: 400))
        .tracking(0)
        .tint(accent(m.preferences["accent"].text))
        .environment(\.locale, Locale(identifier: m.words.language))
        .coordinateSpace(name: "relic-window")
        .background(ScrollAppearance())
        .background(InitialWindowFocus().frame(width: 0, height: 0))
        }
        .background(WindowChromeMount().frame(width: 0, height: 0))
        .ignoresSafeArea(.container, edges: .top)
    }
    private var inspector: some View {
        RightPane(floating: floatingPanel).frame(width: min(panelWidth, m.windowSize.width - 48)).measuredRegion("right-pane")
            .accessibilityLabel(m.t("page.panel"))
            .background(PanelResizeProbe(part: "pane", trace: panelResizeTrace))
            .overlay(alignment: .leading) {
                Color.clear.frame(width: 5).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: inspectorHandleHovered || resizeStart != nil ? RelicStyle.accent.opacity(0.4) : .clear, kind: "resize-handle", owner: "relic-resize-handle/panel", hovered: inspectorHandleHovered))
                    .background(PanelResizeProbe(part: "handle", trace: panelResizeTrace))
                    .onHover { hovering in inspectorHandleHovered = hovering; panelResizeTrace.hover(hovering); if hovering { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() } }
                    .gesture(DragGesture(minimumDistance: 0, coordinateSpace: .named("relic-window")).onChanged { value in
                        panelResizeTrace.gesture(value, ended: false)
                        if resizeStart == nil { resizeStart = panelWidth }
                        resizingPanel = InspectorGeometry.width(window: m.windowSize.width, saved: (resizeStart ?? panelWidth) - value.translation.width, files: m.pane == "files")
                    }.onEnded { value in panelResizeTrace.gesture(value, ended: true); m.defaults.set(Double(panelWidth), forKey: panelKey); resizeStart = nil; resizingPanel = nil })
                    .accessibilityElement(children: .ignore).accessibilityLabel(m.t("panel.resize"))
                    .accessibilityIdentifier("relic-resize-handle/panel").help(m.t("panel.resize"))
            }
            .environment(\.captureRegion, "right-pane")
    }
}

struct AppToolbar: View {
    @EnvironmentObject var m: Model
    @State private var anchors: [String: CGRect] = [:]
    @State private var hoveredMenu: String?
    @State private var controlBounds: [CGRect] = []
    private let menus = [("file", "common.file"), ("edit", "appmenu.edit"), ("view", "appmenu.view"), ("help", "appmenu.help")]
    var body: some View {
        ToolbarLayout {
            HStack(spacing: 2) {
                RelicLogo().padding(.leading, 6).padding(.trailing, 8)
                IconButton(title: m.t(m.sidebarOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar"), icon: "sidebar", size: 16, height: 28) { PerformancePointer.observed("sidebar"); m.sidebarOpen.toggle() }
                    .modifier(PerformancePointerTarget(identity: "sidebar"))
                IconButton(title: m.t("appbar.back"), icon: "back", size: 16, height: 28) { m.navigate(-1) }.disabled(!m.history.canBack)
                IconButton(title: m.t("appbar.forward"), icon: "fwd", size: 16, height: 28) { m.navigate(1) }.disabled(!m.history.canForward)
                HStack(spacing: 0) {
                    ForEach(menus, id: \.0) { key, label in
                        TextButton(m.t(label), size: 13, weight: 400, color: m.appMenu == key || hoveredMenu == key ? RelicStyle.ink : RelicStyle.secondary, height: 28, padding: 9, lines: 0) { PerformancePointer.observed("menu:" + key); m.appMenu = m.appMenu == key ? nil : key }
                            .modifier(PerformancePointerTarget(identity: "menu:" + key))
                            .buttonStyle(QuietButtonStyle(selected: m.appMenu == key, selectionColor: RelicStyle.hover))
                            .background(GeometryReader { proxy in Color.clear.preference(key: MenuAnchors.self, value: [key: proxy.frame(in: .named("appbar"))]) })
                            .onHover { over in
                                if over { hoveredMenu = key; if m.appMenu != nil { m.appMenu = key } }
                                else if hoveredMenu == key { hoveredMenu = nil }
                            }
                    }
                }.modifier(RecordedSurface(background: .clear, kind: "region"))
                    .padding(.leading, 4).accessibilityElement(children: .contain).accessibilityLabel(m.t("appbar.menus"))
            }.background(GeometryReader { proxy in Color.clear.preference(key: ToolbarControlBounds.self, value: [proxy.frame(in: .named("appbar"))]) })
            let title = m.organization.isEmpty ? m.t("common.app_name") : m.snapshot["org"]["name"].text + " · " + (m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("common.secretary") : m.name(m.member))
            if m.windowSize.width > 900 {
                ReferenceLabel(title, size: 12.5, color: RelicStyle.muted, lineHeight: 20).frame(maxWidth: m.windowSize.width * 0.4).help(title).allowsHitTesting(false)
            } else { Color.clear.frame(width: 0, height: 0).accessibilityHidden(true) }
            HStack(spacing: 2) {
                IconButton(title: m.snapshot["decisions"].rows.isEmpty ? m.t("appbar.no_decisions") : m.t("appbar.decisions", ["n": String(m.snapshot["decisions"].rows.count)]), icon: "bell", badge: m.snapshot["decisions"].rows.count, size: 16, height: 28, color: m.snapshot["decisions"].rows.isEmpty ? nil : RelicStyle.amber) { m.setPane("overview") }
                IconButton(title: m.t(m.unreadCopies > 0 ? "appbar.cc" : "appbar.cc_none", ["n": String(m.unreadCopies)]), icon: "cc", badge: m.unreadCopies, size: 16, height: 28) { m.sheet = .copies }
                Color.clear.frame(width: 1, height: 16)
                    .modifier(RecordedSurface(background: RelicStyle.border, kind: "divider", owner: "relic-divider/toolbar"))
                    .accessibilityElement(children: .ignore).accessibilityIdentifier("relic-divider/toolbar").accessibilityLabel("")
                    .padding(.horizontal, 4)
                ForEach(Array(Choices.panes.enumerated()), id: \.offset) { index, pane in
                    IconButton(title: m.t("appbar.pane_shortcut", ["pane": m.t(pane.1), "key": "Option+" + String(index + 1)]), icon: ["org", "work", "file"][index], selected: m.panelOpen && m.pane == pane.0, size: 16, height: 28) {
                        PerformancePointer.observed("pane:" + pane.0)
                        if m.panelOpen && m.pane == pane.0 { m.panelOpen = false } else { m.setPane(pane.0) }
                    }.modifier(PerformancePointerTarget(identity: "pane:" + pane.0))
                }
            }
            .background(GeometryReader { proxy in Color.clear.preference(key: ToolbarControlBounds.self, value: [proxy.frame(in: .named("appbar"))]) })
        }.padding(.leading, WindowChrome.controlsWidth).padding(.trailing, 8).frame(height: WindowChrome.rowHeight)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
            .background(WindowDragRegion(excluded: controlBounds))
            .coordinateSpace(name: "appbar").onPreferenceChange(MenuAnchors.self) { anchors = $0 }
            .onPreferenceChange(ToolbarControlBounds.self) { controlBounds = $0 }
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.titlebar"))
            .accessibilityIdentifier("relic-region/header")
            .overlay(alignment: .topLeading) {
                if let key = m.appMenu, let anchor = anchors[key] {
                    ActionMenu().environmentObject(m).measuredRegion("menu", createsAccessibilityContainer: false).offset(x: max(4, min(anchor.minX, m.windowSize.width - 270)), y: anchor.maxY + 4)
                }
            }
    }
}

/// Keep the title centered in the window while retaining the visible reading
/// order: navigation and menus, title, then the right-hand actions. A title
/// painted as the last ZStack overlay is exposed after all toolbar buttons.
private struct ToolbarLayout: Layout {
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        CGSize(width: proposal.width ?? subviews.reduce(0) { $0 + $1.sizeThatFits(.unspecified).width }, height: proposal.height ?? 40)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard subviews.count == 3 else { return }
        let left = subviews[0].sizeThatFits(.unspecified), right = subviews[2].sizeThatFits(.unspecified)
        let centerX = bounds.midX - (WindowChrome.controlsWidth - 8) / 2
        let available = max(0, 2 * min(centerX - bounds.minX - left.width - 12, bounds.maxX - right.width - centerX - 12))
        let center = subviews[1].sizeThatFits(ProposedViewSize(width: available, height: bounds.height))
        subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.midY - left.height / 2), proposal: ProposedViewSize(left))
        subviews[1].place(at: CGPoint(x: centerX - center.width / 2, y: bounds.midY - center.height / 2), proposal: ProposedViewSize(width: min(available, center.width), height: center.height))
        subviews[2].place(at: CGPoint(x: bounds.maxX - right.width, y: bounds.midY - right.height / 2), proposal: ProposedViewSize(right))
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
                                    ReferenceIcon(name: ["org", "work", "file", "thread"][index], size: 15, color: m.pane == pane.0 ? RelicStyle.ink : RelicStyle.secondary, owner: "relic-tab/" + pane.0)
                                    ReferenceLabel(m.t(pane.1), size: 12.5, weight: m.pane == pane.0 ? 600 : 400, color: m.pane == pane.0 ? RelicStyle.ink : RelicStyle.secondary, owner: "relic-tab/" + pane.0)
                                    if pane.0 == "thread" { Button { m.closeThread() } label: { ReferenceIcon(name: "x", size: 12, color: RelicStyle.muted, owner: "relic-icon-button/thread-close").frame(width: 16, height: 16) }.buttonStyle(.plain).help(m.t("panel.close_thread")).accessibilityLabel(m.t("panel.close_thread")).accessibilityIdentifier("relic-icon-button/thread-close") }
                                }.padding(.horizontal, 9).frame(height: 28)
                            }.buttonStyle(QuietButtonStyle(selected: m.pane == pane.0, selectionApplicable: true)).accessibilityIdentifier("relic-tab/" + pane.0).accessibilityLabel(m.t(pane.1)).accessibilityAddTraits(m.pane == pane.0 ? [.isSelected] : [])
                                .environment(\.nativeElementParent, "relic-tab/" + pane.0)
                        }
                    }
                }.scrollIndicators(.hidden).frame(height: 28)
                IconButton(title: m.t("panel.hide_title"), icon: "x", size: 16) { m.panelOpen = false }.accessibilityLabel(m.t("panel.hide"))
            }.padding(.leading, 8).padding(.trailing, 6).frame(height: 44)
                .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card", owner: "relic-card/right-pane-header"))
                .accessibilityElement(children: .contain).accessibilityIdentifier("relic-card/right-pane-header").accessibilityLabel("")
            switch m.pane {
            case "workspace": WorkspaceView()
            case "files": FilePreview()
            case "thread": ThreadView()
            default: ScrollView { if !m.snapshot["org"].isNull { Overview() } }.defaultScrollAnchor(.top)
            }
        }.frame(maxHeight: .infinity, alignment: .top).padding(.leading, 1)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 1, bottom: 0, trailing: 0), kind: "region", shadows: floating ? SurfaceShadow.dialog : [])).help(m.t("panel.resize"))
    }
}

func pretty(_ node: Node) -> String {
    guard JSONSerialization.isValidJSONObject(node.raw), let data = try? JSONSerialization.data(withJSONObject: node.raw, options: [.prettyPrinted, .sortedKeys]) else { return node.text }
    return String(data: data, encoding: .utf8) ?? ""
}
