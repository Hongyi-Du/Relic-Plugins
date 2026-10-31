import AppKit
import SwiftUI
import RelicCore

/// Runs the shared deterministic plan against the actual production model,
/// view tree, native window and scroll view, without visual AX instrumentation.
@MainActor enum ResponsivenessCapture {
    static var enabled: Bool { ProcessInfo.processInfo.environment["RELIC_PERF_MANIFEST"] != nil }
    static func run() async {
        let env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", let path = env["RELIC_PERF_MANIFEST"] else {
            fputs("Responsiveness capture requires GitHub Actions and a manifest\n", stderr); NSApp.terminate(nil); return
        }
        var monitor: ResponsivenessWatchdog?, model: Model?
        var errors: [String] = [], receipts: [[String: Any]] = []
        var seed = 0, randomSeconds = 0.0, randomActions = 0
        do {
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))))
            let output = URL(fileURLWithPath: manifest["output"].text, isDirectory: true)
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            seed = manifest["seed"].integer
            let watchdog = ResponsivenessWatchdog(output: output); monitor = watchdog
            for old in NSApp.windows { old.orderOut(nil); old.contentView = nil }
            let fixture = manifest["fixture"]
            let suite = "Relic.Responsiveness." + UUID().uuidString
            let defaults = UserDefaults(suiteName: suite)!
            defer { defaults.removePersistentDomain(forName: suite) }
            let current = Model(client: try Client(port: fixture["port"].integer, token: fixture["token"].text), defaults: defaults)
            model = current
            let window = NSWindow(contentRect: NSRect(x: 40, y: 60, width: 1440, height: 900),
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            let host = NSHostingView(rootView: MainView().environmentObject(current))
            host.sizingOptions = []; host.autoresizingMask = [.width, .height]
            window.contentView = host; WindowChrome.apply(to: window)
            window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
            defer { window.orderOut(nil); window.contentView = nil; window.close() }
            await settle()
            // Framework initialization is complete; all organization loading,
            // layout, parsing and events are included from this point onward.
            watchdog.begin()
            await current.start()
            guard current.ready else { throw RelicError.message(current.error) }
            for action in manifest["plan"].rows {
                watchdog.action(action["id"].text + ":" + action["kind"].text)
                receipts.append(try await perform(action, model: current, window: window))
            }
            let deck = manifest["monkey"].rows
            guard !deck.isEmpty else { throw RelicError.message("Empty monkey action deck") }
            let start = ProcessInfo.processInfo.systemUptime
            repeat {
                let action = deck[randomActions % deck.count]
                watchdog.action("monkey:" + action["kind"].text)
                var receipt = try await perform(action, model: current, window: window)
                receipt["id"] = "monkey-\(randomActions)"; receipts.append(receipt)
                randomActions += 1
                randomSeconds = ProcessInfo.processInfo.systemUptime - start
            } while randomSeconds < Double(max(180, manifest["seconds"].integer))
        } catch { errors.append(String(describing: error)) }
        monitor?.finish(["actions": receipts, "errors": errors, "random_seconds": randomSeconds,
                         "random_actions": randomActions, "seed": seed])
        model?.stop(); NSApp.terminate(nil)
    }

    private static func perform(_ action: Node, model m: Model, window: NSWindow) async throws -> [String: Any] {
        let started = ProcessInfo.processInfo.systemUptime, kind = action["kind"].text
        var result = action.object
        m.appMenu = nil; m.sheet = nil
        switch kind {
        case "group", "private":
            try await m.select(action["org"].text, kind == "private" ? action["member"].text : "")
            await settle()
            guard m.organization == action["org"].text else { throw RelicError.message("Organization navigation did not complete") }
        case "pane": m.setPane(action["pane"].text); await settle()
        case "resize":
            window.setFrame(NSRect(origin: window.frame.origin, size: NSSize(width: CGFloat(action["width"].integer), height: CGFloat(action["height"].integer))), display: true)
            await settle()
        case "menu":
            m.appMenu = action["name"].text; await settle(); m.appMenu = nil; await settle()
        case "dialog":
            switch action["name"].text {
            case "settings": m.sheet = .settings
            case "about": m.settingsSection = "about"; m.sheet = .settings
            case "neworg": m.sheet = .create
            case "member": m.openMemberForm()
            default: throw RelicError.message("Unknown dialog in performance manifest")
            }
            await settle(); m.sheet = nil; await settle()
        case "scroll-history":
            try await m.select(action["org"].text); await settle()
            var pages = 0
            while m.moreChat {
                try scroll(window, toTop: true)
                let before = m.messages.first?["id"].text
                try await m.loadOlder(); pages += 1; await settle()
                if m.moreChat && m.messages.first?["id"].text == before { throw RelicError.message("Older page did not advance") }
            }
            try scroll(window, toTop: true); await settle()
            result["pages_loaded"] = pages
            result["oldest_message_id"] = m.messages.first(where: { Int($0["id"].text) != nil })?["id"].integer ?? 0
            result["history_complete"] = !m.moreChat
            try scroll(window, toTop: false); await settle()
        default: throw RelicError.message("Unknown performance action: " + kind)
        }
        result["passed"] = true
        result["target"] = action["org"].text + action["member"].text + action["name"].text + action["pane"].text
        result["elapsed_ms"] = (ProcessInfo.processInfo.systemUptime - started) * 1000
        return result
    }
    private static func settle() async { try? await Task.sleep(for: .milliseconds(300)) }
    private static func scroll(_ window: NSWindow, toTop: Bool) throws {
        func find(_ view: NSView) -> NSScrollView? {
            if let scroll = view as? NSScrollView, scroll.accessibilityIdentifier() == ConversationKeyboard.identifier { return scroll }
            for child in view.subviews { if let found = find(child) { return found } }
            return nil
        }
        guard let root = window.contentView, let scroll = find(root), let document = scroll.documentView else {
            throw RelicError.message("Production conversation scroll view not found")
        }
        let upper: CGFloat = document.isFlipped ? 0 : max(0, document.frame.height - scroll.contentView.bounds.height)
        let lower: CGFloat = document.isFlipped ? max(0, document.frame.height - scroll.contentView.bounds.height) : 0
        scroll.contentView.scroll(to: NSPoint(x: 0, y: toTop ? upper : lower)); scroll.reflectScrolledClipView(scroll.contentView)
    }
}
