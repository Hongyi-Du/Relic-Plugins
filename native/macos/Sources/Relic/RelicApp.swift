import SwiftUI
import AppKit
import UserNotifications

final class Delegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var onQuit: (() -> Void)?
    var onNotification: ((String, String) -> Void)?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        if TitlebarCapture.enabled {
            Task { @MainActor in await TitlebarCapture.run() }
        } else if VisualCapture.enabled {
            // A subsequent viewport process can restore the ordinary window
            // as closed. Capture owns its own window and must start from the
            // actual application lifecycle, independent of a Window view task.
            Task { @MainActor in await VisualCapture.run(Model()) }
        } else { UNUserNotificationCenter.current().delegate = self }
    }
    func applicationWillTerminate(_ notification: Notification) { onQuit?() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { if !flag { sender.windows.first?.makeKeyAndOrderFront(nil) }; return true }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let info = response.notification.request.content.userInfo
        Task { @MainActor in self.onNotification?(info["org"] as? String ?? "", info["member"] as? String ?? ""); NSApp.activate(ignoringOtherApps: true); NSApp.windows.first?.makeKeyAndOrderFront(nil); completionHandler() }
    }
}

@main struct RelicApp: App {
    @NSApplicationDelegateAdaptor(Delegate.self) var delegate
    @StateObject private var model = Model()
    var body: some Scene {
        Window("Relic", id: "main") {
            MainView().environmentObject(model)
                .task { delegate.onQuit = { model.stop() }; delegate.onNotification = { org, member in model.run { try await model.select(org, member) } }; if !VisualCapture.enabled && !TitlebarCapture.enabled { await model.start() } }
                .frame(minWidth: 920, minHeight: 620)
        }
        .defaultSize(width: 1440, height: 900)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button(model.t("appmenu.new_org")) { model.sheet = .create }.keyboardShortcut("n")
                Button(model.t("appmenu.add_member")) { model.openMemberForm() }.disabled(model.organization.isEmpty)
                Button(model.t("appmenu.add_existing")) { model.openMemberForm(mode: "existing") }.disabled(model.organization.isEmpty)
                Button(model.t(model.secretary.isEmpty ? "appmenu.set_up_secretary" : "appmenu.open_secretary")) { if model.secretary.isEmpty { model.sheet = .secretary } else { model.run { try await model.select(model.organization, model.secretary) } } }.disabled(model.organization.isEmpty)
                Button(model.t("appmenu.org_details")) { model.openDetails("trace") }.disabled(model.organization.isEmpty)
                Divider()
                Button(model.t("appmenu.open_data")) { model.run { try await model.post("/api/open", ["what": "data"]) } }
                Button(model.t("appmenu.open_logs")) { model.run { try await model.post("/api/open", ["what": "logs"]) } }
            }
            CommandGroup(after: .sidebar) {
                Button(model.t("appmenu.sidebar")) { model.sidebarOpen.toggle() }.keyboardShortcut("b")
                Button(model.t("page.panel")) { model.panelOpen.toggle() }.keyboardShortcut("b", modifiers: [.command, .option])
                Button(model.t("appmenu.pane", ["pane": model.t("panel.overview")])) { model.togglePane("overview") }.keyboardShortcut("1", modifiers: .option)
                Button(model.t("appmenu.pane", ["pane": model.t("panel.workspace")])) { model.togglePane("workspace") }.keyboardShortcut("2", modifiers: .option)
                Button(model.t("appmenu.pane", ["pane": model.t("common.file")])) { model.togglePane("files") }.keyboardShortcut("3", modifiers: .option)
                Divider()
                Button(model.t("appmenu.org_chart")) { model.sheet = .chart }
                Button(model.t("cc.title")) { model.sheet = .copies }
                Button(model.t("appmenu.plain_group")) { model.run { if !model.member.isEmpty { try await model.select(model.organization) }; model.togglePlain() } }.keyboardShortcut("l", modifiers: [.command, .shift])
                Button(model.t("appmenu.group_digest")) { model.run { if !model.member.isEmpty { try await model.select(model.organization) }; model.toggleDigest() } }
                Divider()
                ForEach(["system", "light", "dark"], id: \.self) { value in Button(model.t("appmenu.theme", ["theme": model.t("common.theme_" + value)])) { model.run { try await model.savePreferences(["theme": value]) } } }
                ForEach(["small", "medium", "large"], id: \.self) { value in Button(model.t("appmenu.font_size", ["size": model.t("common.size_" + value)])) { model.run { try await model.savePreferences(["font": value]) } } }
                Button(model.t("appmenu.reload")) { model.run { try await model.refresh() } }.keyboardShortcut("r")
            }
            CommandGroup(after: .pasteboard) {
                Button(model.t("appmenu.quote_selection")) { model.quoteSelection() }
                Button(model.t("page.search")) { model.sidebarOpen = true; model.focusSearch = true }.keyboardShortcut("k")
                Button(model.t("appbar.back")) { model.navigate(-1) }.keyboardShortcut(.leftArrow, modifiers: .option).disabled(!model.history.canBack)
                Button(model.t("appbar.forward")) { model.navigate(1) }.keyboardShortcut(.rightArrow, modifiers: .option).disabled(!model.history.canForward)
            }
            CommandGroup(replacing: .help) {
                Button(model.t("shortcuts.title")) { model.sheet = .shortcuts }
                Button(model.t("common.voice_input")) { model.settingsSection = "voice"; model.sheet = .settings }
                Button(model.t("common.harness")) { model.settingsSection = "harness"; model.sheet = .settings }
                Button(model.t("appmenu.about")) { model.settingsSection = "about"; model.sheet = .settings }
            }
            CommandGroup(replacing: .appInfo) {
                Button(model.t("appmenu.about")) { model.settingsSection = "about"; model.sheet = .settings }
            }
            CommandGroup(replacing: .appSettings) {
                Button(model.t("appmenu.settings")) { model.sheet = .settings }.keyboardShortcut(",")
            }
        }
    }
}

struct ShortcutsView: View {
    @EnvironmentObject var m: Model
    private let rows = [("Cmd+B", "shortcuts.toggle_sidebar"), ("Cmd+Option+B", "shortcuts.toggle_panel"), ("Option+1 / 2 / 3", "shortcuts.panes"), ("Option+← / Option+→", "shortcuts.back_forward"), ("Cmd+K", "page.search"), ("Cmd+Shift+L", "appmenu.plain_group"), ("Cmd+,", "common.settings"), ("Enter / Shift+Enter", "shortcuts.send_newline"), ("@", "shortcuts.mention"), ("Esc", "shortcuts.close")]
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ReferenceLabel(m.t("shortcuts.title"), size: 17, weight: 650)
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 9) {
                ForEach(rows, id: \.0) { key, label in
                    GridRow {
                        Keycap(key).gridColumnAlignment(.trailing)
                        ReferenceLabel(m.t(label), size: 13, color: RelicStyle.secondary, lines: 0).frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(minHeight: 20.8)
                }
            }.padding(.top, 4)
            HStack { Spacer(); TextButton(m.t("shortcuts.ok"), size: 13, color: RelicStyle.background) { m.sheet = nil }.buttonStyle(ReferenceButtonStyle(primary: true)) }
        }
    }
}
