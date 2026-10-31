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
            current.startupStage = { watchdog.action("startup:" + $0) }
            await current.start()
            current.startupStage = nil
            guard current.ready else { throw RelicError.message(current.error) }
            try await settleConversation(current)
            for action in manifest["plan"].rows {
                watchdog.action(action["id"].text + ":" + action["kind"].text)
                receipts.append(try await perform(action, model: current, window: window))
            }
            let deck = manifest["monkey"].rows
            guard !deck.isEmpty else { throw RelicError.message("Empty monkey action deck") }
            let start = ProcessInfo.processInfo.systemUptime
            var random = UInt64(max(0, seed))
            repeat {
                let action = deck[randomActions % deck.count]
                watchdog.action("monkey:" + action["kind"].text)
                var receipt = try await perform(action, model: current, window: window)
                random = random &* 6364136223846793005 &+ 1442695040888963407
                let targets = ["sidebar", "menu:file", "menu:edit", "menu:view", "menu:help", "pane:overview", "pane:workspace", "pane:files"]
                let target = action["kind"].text == "menu" ? "menu:" + action["name"].text
                    : action["kind"].text == "pane" ? "pane:" + action["pane"].text : targets[Int(random % UInt64(targets.count))]
                current.appMenu = nil; current.sheet = nil; await settle()
                receipt["pointer_target"] = target
                let pointerStarted = ProcessInfo.processInfo.systemUptime
                receipt["click_events"] = try await click(window, target: target)
                receipt["elapsed_ms"] = (receipt["elapsed_ms"] as? Double ?? 0) + (ProcessInfo.processInfo.systemUptime - pointerStarted) * 1000
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
            try await settleConversation(m)
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
            case "tasks", "protocols": m.openDetails(action["name"].text)
            default: throw RelicError.message("Unknown dialog in performance manifest")
            }
            await settle(); m.sheet = nil; await settle()
        case "scroll-history":
            try await m.select(action["org"].text); try await settleConversation(m)
            while m.moreChat {
                while m.loadingOlder { try await Task.sleep(for: .milliseconds(20)) }
                guard m.moreChat else { break }
                try scroll(window, toTop: true)
                let before = m.messages.first(where: { Int($0["id"].text) != nil })?["id"].text
                try await m.loadOlder(); try await settleConversation(m)
                while m.loadingOlder { try await Task.sleep(for: .milliseconds(20)) }
                let after = m.messages.first(where: { Int($0["id"].text) != nil })?["id"].text
                if m.moreChat && after == before { throw RelicError.message("Older page did not advance") }
            }
            try scroll(window, toTop: true); try await settleConversation(m)
            result["pages_loaded"] = m.historyPagesLoaded
            result["oldest_message_id"] = m.messages.first(where: { Int($0["id"].text) != nil })?["id"].integer ?? 0
            result["history_complete"] = !m.moreChat
            try scroll(window, toTop: false); try await settleConversation(m)
        default: throw RelicError.message("Unknown performance action: " + kind)
        }
        result["passed"] = true
        result["target"] = action["org"].text + action["member"].text + action["name"].text + action["pane"].text
        result["elapsed_ms"] = (ProcessInfo.processInfo.systemUptime - started) * 1000
        return result
    }
    private static func settle() async { try? await Task.sleep(for: .milliseconds(300)) }
    private static func settleConversation(_ model: Model) async throws {
        // A completed HTTP request does not mean SwiftUI displayed its rows.
        // Wait for projection, the real stream's observation, and visible
        // Markdown tasks, while leaving the main run loop/watchdog running.
        guard let window = NSApp.keyWindow else { throw RelicError.message("The production window is not active") }
        try await PerformanceRendering.waitForContent(model, window: window)
    }
    private static func click(_ window: NSWindow, target: String) async throws -> Int {
        guard let root = window.contentView, let bounds = PerformancePointer.bounds[target], bounds.width > 0, bounds.height > 0 else {
            throw RelicError.message("Native pointer target has no laid-out bounds: " + target)
        }
        let before = PerformancePointer.clicks[target, default: 0]
        let point = root.convert(NSPoint(x: bounds.midX, y: root.isFlipped ? bounds.midY : root.bounds.height - bounds.midY), to: nil)
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            guard let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0) else {
                throw RelicError.message("Could not create native mouse event")
            }
            NSApp.postEvent(event, atStart: false)
        }
        for _ in 0..<100 {
            try await Task.sleep(for: .milliseconds(20))
            let handled = PerformancePointer.clicks[target, default: 0] - before
            if handled > 0 { await settle(); return handled }
        }
        throw RelicError.message("Native control did not handle the pointer click: " + target)
    }
    private static func scroll(_ window: NSWindow, toTop: Bool) throws {
        func find(_ view: NSView) -> NSScrollView? {
            if let scroll = view as? NSScrollView, scroll.accessibilityIdentifier() == ConversationKeyboard.identifier { return scroll }
            for child in view.subviews { if let found = find(child) { return found } }
            return nil
        }
        guard let root = window.contentView, let scroll = find(root), let document = scroll.documentView else {
            throw RelicError.message("Production conversation scroll view not found")
        }
        if let controller = ConversationKeyboardMount.controller(for: scroll), controller.scrollToEdge != nil {
            _ = controller.handle(toTop ? .home : .end, modifiers: []); return
        }
        let upper: CGFloat = document.isFlipped ? 0 : max(0, document.frame.height - scroll.contentView.bounds.height)
        let lower: CGFloat = document.isFlipped ? max(0, document.frame.height - scroll.contentView.bounds.height) : 0
        scroll.contentView.scroll(to: NSPoint(x: 0, y: toTop ? upper : lower)); scroll.reflectScrolledClipView(scroll.contentView)
    }
}
