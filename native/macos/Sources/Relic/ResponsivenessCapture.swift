import AppKit
import SwiftUI
import RelicCore

/// Measurement-only entry point: baseline and optimized builds exercise the
/// same model actions, actual MainView, native resizing, and mouse event path.
@MainActor enum ResponsivenessCapture {
    static var enabled: Bool { ProcessInfo.processInfo.environment["RELIC_RESPONSIVENESS_CAPTURE"] == "1" }
    static func run() async {
        let env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", let path = env["RELIC_VISUAL_MANIFEST"] else {
            fputs("Responsiveness capture requires GitHub Actions and a manifest\n", stderr); NSApp.terminate(nil); return
        }
        var monitor: ResponsivenessWatchdog?, model: Model?, errors: [String] = []
        var seed: UInt64 = 17
        do {
            let manifestURL = URL(fileURLWithPath: path)
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)))
            let output = URL(fileURLWithPath: manifest["output"].text, isDirectory: true)
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            seed = UInt64(max(1, manifest["seed"].integer == 0 ? 17 : manifest["seed"].integer))
            let watchdog = ResponsivenessWatchdog(output: output.appendingPathComponent("responsiveness-report.json"), completion: manifestURL.deletingLastPathComponent().appendingPathComponent("complete.json"), seed: seed)
            monitor = watchdog
            for old in NSApp.windows { old.orderOut(nil); old.contentView = nil }
            watchdog.begin()
            let fixture = manifest["fixture"]
            let suite = "Relic.Responsiveness." + UUID().uuidString
            let defaults = UserDefaults(suiteName: suite)!
            defer { defaults.removePersistentDomain(forName: suite) }
            let current = Model(client: try Client(port: fixture["port"].integer, token: fixture["token"].text), defaults: defaults)
            model = current
            await current.start()
            guard current.ready else { throw RelicError.message(current.error) }
            let window = NSWindow(contentRect: NSRect(x: 40, y: 60, width: 1440, height: 900),
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            let host = NSHostingView(rootView: MainView().environmentObject(current))
            host.sizingOptions = []; host.autoresizingMask = [.width, .height]
            window.contentView = host; WindowChrome.apply(to: window)
            window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
            defer { window.orderOut(nil); window.contentView = nil; window.close() }
            await settle()
            let orgs = current.organizations.map { $0["id"].text }
            for org in orgs {
                watchdog.action("open-organization")
                try await current.select(org); await settle()
                let members = current.members.map { $0["name"].text }
                for member in members {
                    watchdog.action("open-private-chat")
                    try await current.select(org, member); await settle()
                }
            }
            guard let first = orgs.first else { throw RelicError.message("Large fixture has no organizations") }
            try await current.select(first); await settle()
            // Walk all history through the actual older-page API before the
            // seeded run; scrolling also exercises native text materialization.
            while current.moreChat {
                watchdog.action("scroll-earlier-page")
                scroll(window, toTop: true)
                try await current.loadOlder(); await settle()
            }
            scroll(window, toTop: true); await settle()
            for pane in ["overview", "workspace", "files"] {
                watchdog.action("switch-pane"); current.setPane(pane); await settle()
            }
            for width in [1440, 1024, 1181, 1180, 960, 1440] {
                watchdog.action("resize-breakpoint")
                window.setFrame(NSRect(origin: window.frame.origin, size: NSSize(width: CGFloat(width), height: width < 1181 ? 700 : 900)), display: true)
                await settle()
            }
            for sheet in [Model.Sheet.settings, .shortcuts, .details] {
                watchdog.action("open-dialog"); current.sheet = sheet; await settle(); current.sheet = nil; await settle()
            }
            for name in ["file", "edit", "view", "help"] {
                watchdog.action("open-menu"); current.appMenu = name; await settle(); current.appMenu = nil
            }
            var random = seed
            let until = ProcessInfo.processInfo.systemUptime + Double(max(180, manifest["duration_seconds"].integer))
            while ProcessInfo.processInfo.systemUptime < until {
                random = random &* 6364136223846793005 &+ 1442695040888963407
                let choices: [CGFloat] = [127, 159, 191, 231, 279, 328, 368, window.frame.width - 155, window.frame.width - 125, window.frame.width - 94, window.frame.width - 55, window.frame.width - 24]
                watchdog.action("seeded-mouse-click")
                click(window, point: NSPoint(x: choices[Int(random % UInt64(choices.count))], y: window.frame.height - 20))
                try await Task.sleep(for: .milliseconds(180))
                if random % 7 == 0 { watchdog.action("monkey-scroll"); scroll(window, toTop: random % 2 == 0) }
                if random % 11 == 0 { current.appMenu = nil; current.sheet = nil; current.sidebarOpen = true }
                if random % 17 == 0 {
                    watchdog.action("monkey-resize")
                    let size = random % 2 == 0 ? NSSize(width: 1024, height: 700) : NSSize(width: 1440, height: 900)
                    window.setFrame(NSRect(origin: window.frame.origin, size: size), display: true)
                }
            }
        } catch { errors.append(String(describing: error)) }
        monitor?.finish(errors: errors, seed: seed)
        model?.stop(); NSApp.terminate(nil)
    }

    private static func settle() async { try? await Task.sleep(for: .milliseconds(300)) }
    private static func click(_ window: NSWindow, point: NSPoint) {
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            if let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0) {
                NSApp.postEvent(event, atStart: false)
            }
        }
    }
    private static func scroll(_ window: NSWindow, toTop: Bool) {
        func find(_ view: NSView) -> NSScrollView? {
            if let scroll = view as? NSScrollView, scroll.accessibilityIdentifier() == ConversationKeyboard.identifier { return scroll }
            for child in view.subviews { if let found = find(child) { return found } }
            return nil
        }
        guard let root = window.contentView, let scroll = find(root), let document = scroll.documentView else { return }
        let upper: CGFloat = document.isFlipped ? 0 : max(0, document.frame.height - scroll.contentView.bounds.height)
        let lower: CGFloat = document.isFlipped ? max(0, document.frame.height - scroll.contentView.bounds.height) : 0
        scroll.contentView.scroll(to: NSPoint(x: 0, y: toTop ? upper : lower)); scroll.reflectScrolledClipView(scroll.contentView)
    }
}
