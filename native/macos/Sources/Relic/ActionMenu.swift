import AppKit
import SwiftUI

// Compact toolbar access to the same actions as the macOS menu bar.
struct ActionMenu: View {
    @EnvironmentObject var m: Model
    @State private var contentWidth: CGFloat = 250
    var body: some View {
        FittingScroll(maxHeight: m.windowSize.height * 0.6) {
            VStack(alignment: .leading, spacing: 0) {
                switch m.appMenu ?? "file" {
                case "file": file
                case "edit": edit
                case "view": view
                default: help
                }
            }.padding(7)
        }.frame(width: max(250, contentWidth + 14))
            .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 12, kind: "region", shadows: SurfaceShadow.dialog))
            .onPreferenceChange(MenuIntrinsicWidth.self) { contentWidth = $0 }
            .onExitCommand { m.appMenu = nil }
    }
    private var separator: some View {
        Color.clear.frame(height: 1).modifier(RecordedSurface(background: RelicStyle.line, kind: "divider"))
            .padding(.vertical, 4).padding(.horizontal, 6)
    }
    private func row(_ title: String, _ shortcut: String = "", check: Bool = false, action: @escaping () -> Void) -> some View {
        NativeMenuRow(title: title, shortcut: shortcut, checked: check) { m.appMenu = nil; action() }
    }
    private var file: some View {
        Group {
            row(m.t("appmenu.new_org")) { m.sheet = .create }
            row(m.t("appmenu.add_member")) { m.openMemberForm() }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.add_existing")) { m.openMemberForm(mode: "existing") }.disabled(m.organization.isEmpty)
            row(m.t(m.secretary.isEmpty ? "appmenu.set_up_secretary" : "appmenu.open_secretary")) { if m.secretary.isEmpty { m.sheet = .secretary } else { m.run { try await m.select(m.organization, m.secretary) } } }.disabled(m.organization.isEmpty)
            separator
            row(m.t("appmenu.org_details")) { m.openDetails("trace") }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.open_data")) { m.run { try await m.post("/api/open", ["what": "data"]) } }
            row(m.t("appmenu.open_logs")) { m.run { try await m.post("/api/open", ["what": "logs"]) } }
            separator; row(m.t("appmenu.settings"), "Cmd+,") { m.sheet = .settings }
        }
    }
    private var edit: some View {
        Group {
            row(m.t("appmenu.undo"), "Cmd+Z") { NSApp.sendAction(Selector(("undo:")), to: nil, from: nil) }
            row(m.t("appmenu.redo"), "Cmd+Shift+Z") { NSApp.sendAction(Selector(("redo:")), to: nil, from: nil) }
            separator
            row(m.t("appmenu.cut"), "Cmd+X") { NSApp.sendAction(#selector(NSText.cut(_:)), to: nil, from: nil) }
            row(m.t("common.copy"), "Cmd+C") { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: nil) }
            row(m.t("appmenu.paste"), "Cmd+V") { NSApp.sendAction(#selector(NSText.paste(_:)), to: nil, from: nil) }
            row(m.t("appmenu.select_all"), "Cmd+A") { NSApp.sendAction(#selector(NSText.selectAll(_:)), to: nil, from: nil) }
            separator; row(m.t("appmenu.quote_selection")) { m.quoteSelection() }
            row(m.t("page.search"), "Cmd+K") { m.sidebarOpen = true; m.focusSearch = true }
        }
    }
    private var view: some View {
        Group {
            row(m.t("appmenu.sidebar"), "Cmd+B", check: m.sidebarOpen) { m.sidebarOpen.toggle() }
            row(m.t("page.panel"), "Cmd+Option+B", check: m.panelOpen) { m.panelOpen.toggle() }
            separator
            row(m.t("appmenu.pane", ["pane": m.t("panel.overview")]), "Option+1", check: m.panelOpen && m.pane == "overview") { m.setPane("overview") }
            row(m.t("appmenu.pane", ["pane": m.t("panel.workspace")]), "Option+2", check: m.panelOpen && m.pane == "workspace") { m.setPane("workspace") }
            row(m.t("appmenu.pane", ["pane": m.t("common.file")]), "Option+3", check: m.panelOpen && m.pane == "files") { m.setPane("files") }
            separator; row(m.t("appmenu.org_chart")) { m.sheet = .chart }.disabled(m.organizations.isEmpty)
            separator
            row(m.t("appmenu.plain_group"), "Cmd+Shift+L", check: m.plainMode) { m.run { if !m.member.isEmpty { try await m.select(m.organization) }; m.togglePlain() } }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.group_digest"), check: m.digestOpen) { m.run { if !m.member.isEmpty { try await m.select(m.organization) }; m.toggleDigest() } }.disabled(m.organization.isEmpty)
            separator
            ForEach(Choices.themes, id: \.0) { value, key in row(m.t("appmenu.theme", ["theme": m.t(key)]), check: m.preferences["theme"].text == value) { m.run { try await m.savePreferences(["theme": value]) } } }
            ForEach(Choices.fonts, id: \.0) { value, key in row(m.t("appmenu.font_size", ["size": m.t(key)]), check: m.preferences["font"].text == value) { m.run { try await m.savePreferences(["font": value]) } } }
            separator; row(m.t("appmenu.reload"), "Cmd+R") { m.run { try await m.refresh() } }
        }
    }
    private var help: some View {
        Group {
            row(m.t("shortcuts.title")) { m.sheet = .shortcuts }
            row(m.t("common.voice_input")) { m.settingsSection = "voice"; m.sheet = .settings }
            row(m.t("common.harness")) { m.settingsSection = "harness"; m.sheet = .settings }
            separator; row(m.t("appmenu.about")) { m.settingsSection = "about"; m.sheet = .settings }
        }
    }
}

struct RecipientLayer: View {
    @EnvironmentObject var m: Model
    @State private var height: CGFloat = 0
    private var width: CGFloat {
        max(220, m.members.map { who in
            let name = (who.display as NSString).size(withAttributes: [.font: RelicStyle.nativeFont(13, weight: 400), .tracking: 0]).width
            let sub = who.display == who["name"].text ? 0 : (who["name"].text as NSString).size(withAttributes: [.font: RelicStyle.monoFont(11.96), .tracking: 0]).width + 10
            return 14 + 20 + 20 + 20 + 20 + name + sub
        }.max() ?? 220)
    }
    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear.contentShape(Rectangle()).onTapGesture { m.recipientPicker = false }
            FittingScroll(maxHeight: m.windowSize.height * 0.6) {
                RecipientPicker().padding(7)
            }.frame(width: width)
                .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 12, kind: "region", shadows: SurfaceShadow.dialog))
                .background(GeometryReader { proxy in Color.clear.preference(key: RecipientHeight.self, value: proxy.size.height) })
                .onPreferenceChange(RecipientHeight.self) { height = $0 }
                .offset(x: min(m.recipientAnchor.minX, m.windowSize.width - 260), y: m.recipientAnchor.minY - 6 - height)
                .measuredRegion("menu")
        }.onExitCommand { m.recipientPicker = false }
    }
}
private struct RecipientHeight: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

struct RecipientPicker: View {
    @EnvironmentObject var m: Model
    private func select(_ who: String) {
        if who == "all" { m.recipients = ["all"] }
        else {
            let selected = m.recipients.contains(who)
            m.recipients.removeAll { $0 == "all" || $0 == who }
            if !selected { m.recipients.append(who) }
            if m.recipients.isEmpty { m.recipients = ["all"] }
        }
        m.persistDraft(); m.recipientPicker = false
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            row("all", title: m.t("composer.all_members"))
            Rows(m.members) { row($0["name"].text, title: $0.display) }
        }
    }
    private func row(_ who: String, title: String) -> some View {
        Button { select(who) } label: {
            HStack(spacing: 10) {
                NativeCheck(checked: Binding(get: { m.recipients.contains(who) && (who == "all" || !m.recipients.contains("all")) }, set: { _ in select(who) })).frame(width: 20, height: 20).allowsHitTesting(false)
                if who == "all" { ReferenceIcon(name: "hash", size: 17, color: RelicStyle.secondary).frame(width: 20, height: 20).modifier(RecordedSurface(background: RelicStyle.hover, radius: 6, kind: "avatar")) }
                else { Avatar(member: who, size: 20) }
                ReferenceLabel(title, size: 13)
                if who != "all" && who != title { ReferenceLabel(who, size: 11.96, color: RelicStyle.muted, monospaced: true) }
                Spacer(minLength: 0)
            }.padding(.horizontal, 10).frame(height: 34.8)
        }.buttonStyle(MenuItemStyle()).accessibilityIdentifier("relic-menu-item/recipient/" + who)
    }
}

private struct MenuIntrinsicWidth: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

struct NativeMenuRow: View {
    let title: String
    var shortcut = ""
    var checked = false
    let action: () -> Void
    @Environment(\.isEnabled) private var enabled
    @State private var identity = "relic-menu-item/" + UUID().uuidString
    private var intrinsicWidth: CGFloat {
        let label = (title as NSString).size(withAttributes: [.font: RelicStyle.nativeFont(13, weight: 400), .tracking: 0]).width
        let key = shortcut.isEmpty ? 0 : (shortcut as NSString).size(withAttributes: [.font: RelicStyle.monoFont(11), .tracking: 0]).width + 10
        return 20 + 14 + 10 + label + key
    }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Group {
                    if checked { ReferenceIcon(name: "check", size: 14, color: RelicStyle.accent) }
                    else { Color.clear.frame(width: 14, height: 14).accessibilityHidden(true) }
                }
                ReferenceLabel(title, size: 13, color: enabled ? RelicStyle.ink : RelicStyle.faint, owner: identity).frame(maxWidth: .infinity, alignment: .leading)
                if !shortcut.isEmpty { Keycap(shortcut, menu: true) }
            }.padding(.horizontal, 10).frame(height: 34.8)
        }.buttonStyle(MenuItemStyle()).accessibilityIdentifier(identity)
            .preference(key: MenuIntrinsicWidth.self, value: intrinsicWidth)
    }
}

struct MenuItemStyle: ButtonStyle {
    var selected = false
    func makeBody(configuration: Configuration) -> some View { StyledContent(configuration: configuration, selected: selected) }
    private struct StyledContent: View {
        let configuration: Configuration
        let selected: Bool
        @Environment(\.isEnabled) private var enabled
        @State private var hovered = false
        var body: some View {
            configuration.label.contentShape(RoundedRectangle(cornerRadius: 8))
                .modifier(RecordedSurface(background: enabled && (selected || hovered || configuration.isPressed) ? RelicStyle.hover : .clear, radius: 8, hovered: hovered))
                .onHover { hovered = $0 }
        }
    }
}

struct Keycap: View {
    let value: String
    var menu = false
    @State private var identity = "relic-chip/keycap/" + UUID().uuidString
    init(_ value: String, menu: Bool = false) { self.value = value; self.menu = menu }
    var body: some View {
        ReferenceLabel(value, size: menu ? 11 : 11.5, color: menu ? RelicStyle.muted : RelicStyle.ink, lineHeight: menu ? 13 : 14, owner: identity, monospaced: true)
            .fixedSize().padding(.horizontal, menu ? 0 : 7).padding(.top, menu ? 0 : 2).padding(.bottom, menu ? 0 : 3)
            .modifier(RecordedSurface(background: menu ? .clear : RelicStyle.hover, border: menu ? .clear : RelicStyle.border,
                borderWidth: menu ? 0 : 1, radius: 5, edges: menu ? nil : EdgeInsets(top: 1, leading: 1, bottom: 2, trailing: 1), kind: "chip", owner: identity))
            .accessibilityElement(children: .contain).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}
