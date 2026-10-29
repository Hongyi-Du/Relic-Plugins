import AppKit
import SwiftUI

// Compact toolbar access to the same actions as the macOS menu bar.
struct ActionMenu: View {
    @EnvironmentObject var m: Model
    private var height: CGFloat { min(m.windowSize.height * 0.6, m.appMenu == "view" ? 590 : m.appMenu == "help" ? 162.2 : 310.4) }
    var body: some View {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    switch m.appMenu ?? "file" {
                    case "file": file
                    case "edit": edit
                    case "view": view
                    default: help
                    }
                }.padding(6)
            }
        .frame(width: 250, height: height).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(RelicStyle.border, lineWidth: 1))
        .shadow(color: .black.opacity(0.14), radius: 16, y: 10).foregroundStyle(RelicStyle.ink)
        .onExitCommand { m.appMenu = nil }
    }
    private var separator: some View { RelicStyle.line.frame(height: 1).padding(.vertical, 4).padding(.horizontal, 6) }
    private func row(_ title: String, _ shortcut: String = "", check: Bool = false, action: @escaping () -> Void) -> some View {
        Button { m.appMenu = nil; action() } label: {
            HStack(spacing: 10) {
                Group { if check { ReferenceIcon(name: "check", size: 14, color: RelicStyle.accent) } else { Color.clear.frame(width: 14, height: 14) } }
                Text(title).font(RelicStyle.font(13, weight: 400)).frame(maxWidth: .infinity, alignment: .leading)
                if !shortcut.isEmpty { Text(shortcut).font(.system(size: 11, design: .monospaced)).foregroundStyle(RelicStyle.muted) }
            }.padding(.horizontal, 10).frame(height: 34.8).frame(maxWidth: .infinity, alignment: .leading)
        }.buttonStyle(QuietButtonStyle())
    }
    private var file: some View {
        Group {
            row(m.t("appmenu.new_org")) { m.sheet = .create }
            row(m.t("appmenu.add_member")) { m.openMemberForm() }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.add_existing")) { m.openMemberForm(mode: "existing") }.disabled(m.organization.isEmpty)
            row(m.t(m.secretary.isEmpty ? "appmenu.set_up_secretary" : "appmenu.open_secretary")) { if m.secretary.isEmpty { m.sheet = .secretary } else { m.run { try await m.select(m.organization, m.secretary) } } }.disabled(m.organization.isEmpty)
            separator
            row(m.t("appmenu.org_details")) { m.openDetails("trace") }
            row(m.t("appmenu.open_data")) { m.run { try await m.post("/api/open", ["what": "data"]) } }
            row(m.t("appmenu.open_logs")) { m.run { try await m.post("/api/open", ["what": "logs"]) } }
            separator; row(m.t("appmenu.settings"), "⌘,") { m.sheet = .settings }
        }
    }
    private var edit: some View {
        Group {
            row(m.t("appmenu.undo"), "⌘Z") { NSApp.sendAction(Selector(("undo:")), to: nil, from: nil) }
            row(m.t("appmenu.redo"), "⇧⌘Z") { NSApp.sendAction(Selector(("redo:")), to: nil, from: nil) }
            separator
            row(m.t("appmenu.cut"), "⌘X") { NSApp.sendAction(#selector(NSText.cut(_:)), to: nil, from: nil) }
            row(m.t("common.copy"), "⌘C") { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: nil) }
            row(m.t("appmenu.paste"), "⌘V") { NSApp.sendAction(#selector(NSText.paste(_:)), to: nil, from: nil) }
            row(m.t("appmenu.select_all"), "⌘A") { NSApp.sendAction(#selector(NSText.selectAll(_:)), to: nil, from: nil) }
            separator; row(m.t("appmenu.quote_selection")) { m.quoteSelection() }
            row(m.t("page.search"), "⌘K") { m.sidebarOpen = true; m.focusSearch = true }
        }
    }
    private var view: some View {
        Group {
            row(m.t("appmenu.sidebar"), "⌘B", check: m.sidebarOpen) { m.sidebarOpen.toggle() }
            row(m.t("page.panel"), "⌘⌥B", check: m.panelOpen) { m.panelOpen.toggle() }
            separator
            row(m.t("appmenu.pane", ["pane": m.t("panel.overview")]), "⌥1", check: m.panelOpen && m.pane == "overview") { m.setPane("overview") }
            row(m.t("appmenu.pane", ["pane": m.t("panel.workspace")]), "⌥2", check: m.panelOpen && m.pane == "workspace") { m.setPane("workspace") }
            row(m.t("appmenu.pane", ["pane": m.t("common.file")]), "⌥3", check: m.panelOpen && m.pane == "files") { m.setPane("files") }
            separator; row(m.t("appmenu.org_chart")) { m.sheet = .chart }
            separator
            row(m.t("appmenu.plain_group"), "⌘⇧L", check: m.plainMode) { m.togglePlain() }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.group_digest"), check: m.digestOpen) { m.toggleDigest() }.disabled(m.organization.isEmpty)
            separator
            ForEach(Choices.themes, id: \.0) { value, key in row(m.t("appmenu.theme", ["theme": m.t(key)]), check: m.preferences["theme"].text == value) { m.run { try await m.savePreferences(["theme": value]) } } }
            ForEach(Choices.fonts, id: \.0) { value, key in row(m.t("appmenu.font_size", ["size": m.t(key)]), check: m.preferences["font"].text == value) { m.run { try await m.savePreferences(["font": value]) } } }
            separator; row(m.t("appmenu.reload"), "⌘R") { m.run { try await m.refresh() } }
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
            let name = (who.display as NSString).size(withAttributes: [.font: RelicStyle.nativeFont(13, weight: 400)]).width
            let sub = who.display == who["name"].text ? 0 : (who["name"].text as NSString).size(withAttributes: [.font: RelicStyle.monoFont(11.96)]).width + 10
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
        }.buttonStyle(QuietButtonStyle())
    }
}
