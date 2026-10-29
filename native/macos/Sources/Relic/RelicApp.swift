import SwiftUI
import AppKit

final class Delegate: NSObject, NSApplicationDelegate {
    var onQuit: (() -> Void)?
    func applicationWillTerminate(_ notification: Notification) { onQuit?() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main struct RelicApp: App {
    @NSApplicationDelegateAdaptor(Delegate.self) var delegate
    @StateObject private var model = Model()
    var body: some Scene {
        Window("Relic", id: "main") {
            MainView().environmentObject(model)
                .task { delegate.onQuit = { model.stop() }; await model.start() }
                .frame(minWidth: 1050, minHeight: 650)
        }
        .defaultSize(width: 1480, height: 940)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button(model.t("common.new_org")) { model.sheet = .create }.keyboardShortcut("n")
                Button(model.t("common.add_member")) { model.sheet = .member }.disabled(model.organization.isEmpty)
            }
            CommandGroup(after: .sidebar) {
                Button(model.t("chart.title")) { model.sheet = .chart }
                Button(model.t("cc.title")) { model.sheet = .copies }
            }
            CommandGroup(replacing: .appSettings) {
                Button(model.t("common.settings")) { model.sheet = .settings }.keyboardShortcut(",")
            }
        }
    }
}
