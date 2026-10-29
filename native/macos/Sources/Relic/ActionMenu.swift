import AppKit
import SwiftUI

// Compact toolbar access to the same actions as the macOS menu bar.
struct ActionMenu: View {
    @EnvironmentObject var m: Model
    private var selection: Binding<String> { Binding(get: { m.appMenu ?? "file" }, set: { m.appMenu = $0 }) }
    var body: some View {
        VStack(spacing: 8) {
            Picker("", selection: selection) {
                Text(m.t("common.file")).tag("file"); Text(m.t("appmenu.edit")).tag("edit")
                Text(m.t("appmenu.view")).tag("view"); Text(m.t("appmenu.help")).tag("help")
            }.pickerStyle(.segmented)
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    switch m.appMenu ?? "file" {
                    case "file": file
                    case "edit": edit
                    case "view": view
                    default: help
                    }
                }.padding(2)
            }
        }.padding(10).frame(width: 320, height: m.appMenu == "view" ? 540 : m.appMenu == "help" ? 230 : 360)
    }
    private func row(_ title: String, _ shortcut: String = "", action: @escaping () -> Void) -> some View {
        Button { m.appMenu = nil; action() } label: {
            HStack { Text(title).fixedSize(horizontal: false, vertical: true); Spacer(minLength: 8); Text(shortcut).foregroundStyle(RelicStyle.muted) }.font(.system(size: 13)).padding(.horizontal, 9).padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading)
        }.buttonStyle(QuietButtonStyle())
    }
    private var file: some View {
        Group {
            row(m.t("appmenu.new_org"), "⌘N") { m.sheet = .create }
            row(m.t("appmenu.add_member")) { m.openMemberForm() }.disabled(m.organization.isEmpty)
            row(m.t("appmenu.add_existing")) { m.openMemberForm(mode: "existing") }.disabled(m.organization.isEmpty)
            row(m.t(m.secretary.isEmpty ? "appmenu.set_up_secretary" : "appmenu.open_secretary")) { if m.secretary.isEmpty { m.sheet = .secretary } else { m.run { try await m.select(m.organization, m.secretary) } } }.disabled(m.organization.isEmpty)
            Divider()
            row(m.t("appmenu.org_details")) { m.openDetails("trace") }
            row(m.t("appmenu.open_data")) { m.run { try await m.post("/api/open", ["what": "data"]) } }
            row(m.t("appmenu.open_logs")) { m.run { try await m.post("/api/open", ["what": "logs"]) } }
            Divider(); row(m.t("appmenu.settings"), "⌘,") { m.sheet = .settings }
        }
    }
    private var edit: some View {
        Group {
            row(m.t("appmenu.undo"), "⌘Z") { NSApp.sendAction(Selector(("undo:")), to: nil, from: nil) }
            row(m.t("appmenu.redo"), "⇧⌘Z") { NSApp.sendAction(Selector(("redo:")), to: nil, from: nil) }
            Divider()
            row(m.t("appmenu.cut"), "⌘X") { NSApp.sendAction(#selector(NSText.cut(_:)), to: nil, from: nil) }
            row(m.t("common.copy"), "⌘C") { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: nil) }
            row(m.t("appmenu.paste"), "⌘V") { NSApp.sendAction(#selector(NSText.paste(_:)), to: nil, from: nil) }
            row(m.t("appmenu.select_all"), "⌘A") { NSApp.sendAction(#selector(NSText.selectAll(_:)), to: nil, from: nil) }
            Divider(); row(m.t("appmenu.quote_selection")) { m.quoteSelection() }
            row(m.t("page.search"), "⌘K") { m.sidebarOpen = true; m.focusSearch = true }
        }
    }
    private var view: some View {
        Group {
            row(m.t("appmenu.sidebar"), "⌘B") { m.sidebarOpen.toggle() }
            row(m.t("page.panel"), "⌥⌘B") { m.panelOpen.toggle() }
            Divider()
            row(m.t("appmenu.pane", ["pane": m.t("panel.overview")]), "⌥1") { m.setPane("overview") }
            row(m.t("appmenu.pane", ["pane": m.t("panel.workspace")]), "⌥2") { m.setPane("workspace") }
            row(m.t("appmenu.pane", ["pane": m.t("common.file")]), "⌥3") { m.setPane("files") }
            Divider(); row(m.t("appmenu.org_chart")) { m.sheet = .chart }
            row(m.t("appmenu.plain_group"), "⇧⌘L") { m.togglePlain() }
            row(m.t("appmenu.group_digest")) { m.toggleDigest() }
            Divider()
            ForEach(Choices.themes, id: \.0) { value, key in row(m.t("appmenu.theme", ["theme": m.t(key)])) { m.run { try await m.savePreferences(["theme": value]) } } }
            ForEach(Choices.fonts, id: \.0) { value, key in row(m.t("appmenu.font_size", ["size": m.t(key)])) { m.run { try await m.savePreferences(["font": value]) } } }
            Divider(); row(m.t("appmenu.reload"), "⌘R") { m.run { try await m.refresh() } }
        }
    }
    private var help: some View {
        Group {
            row(m.t("shortcuts.title")) { m.sheet = .shortcuts }
            row(m.t("common.voice_input")) { m.settingsSection = "voice"; m.sheet = .settings }
            row(m.t("common.harness")) { m.settingsSection = "harness"; m.sheet = .settings }
            Divider(); row(m.t("appmenu.about")) { m.settingsSection = "about"; m.sheet = .settings }
        }
    }
}

struct RecipientPicker: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(m.t("composer.send_to", ["to": m.recipients.contains("all") ? m.t("msg.everyone") : m.list(m.recipients.map { m.name($0) })])).font(.headline).lineLimit(2)
            Button(m.t("composer.all_members")) { m.recipients = ["all"]; m.persistDraft() }.buttonStyle(.borderless)
            Divider()
            ScrollView { VStack(alignment: .leading, spacing: 10) {
                Rows(m.members) { who in
                    Toggle(isOn: Binding(get: { m.recipients.contains(who["name"].text) }, set: { on in
                        m.recipients.removeAll { $0 == "all" || $0 == who["name"].text }; if on { m.recipients.append(who["name"].text) }; if m.recipients.isEmpty { m.recipients = ["all"] }; m.persistDraft()
                    })) { HStack { Avatar(member: who["name"].text, size: 22); Text(who.display).lineLimit(1).help(who.display) } }.toggleStyle(.checkbox)
                }
            } }
        }.padding(14).frame(width: 270, height: 260)
    }
}
