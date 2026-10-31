import AppKit
import SwiftUI
import RelicCore

/// CI-only WindowServer captures of the same application content and chrome
/// used by the shipped app. This deliberately does not use cacheDisplay.
@MainActor enum TitlebarCapture {
    static var enabled: Bool {
        let env = ProcessInfo.processInfo.environment
        return env["RELIC_TITLEBAR_CAPTURE"] == "1" || env["RELIC_TITLEBAR_MANIFEST"] != nil
    }
    static func run() async {
        let env = ProcessInfo.processInfo.environment
        guard env["GITHUB_ACTIONS"] == "true", let path = env["RELIC_TITLEBAR_MANIFEST"] ?? env["RELIC_VISUAL_MANIFEST"] else {
            fputs("Whole-window capture is restricted to GitHub Actions\n", stderr); NSApp.terminate(nil); return
        }
        var display: CaptureDisplay?
        var model: Model?
        var results: [[String: Any]] = [], errors: [String] = []
        var output = URL(fileURLWithPath: path).deletingLastPathComponent()
        do {
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))))
            output = URL(fileURLWithPath: manifest["output"].text, isDirectory: true)
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            display = try CaptureDisplay(cases: manifest["cases"].rows, output: output)
            try await Task.sleep(for: .milliseconds(250))
            let fixture = manifest["fixture"], language = Words.normalize(manifest["lang"].text), theme = manifest["theme"].text
            let suite = "Relic.TitlebarCapture." + UUID().uuidString
            guard let defaults = UserDefaults(suiteName: suite) else { throw RelicError.message("Cannot create capture preferences") }
            defer { defaults.removePersistentDomain(forName: suite) }
            let current = Model(client: try Client(port: fixture["port"].integer, token: fixture["token"].text), defaults: defaults)
            model = current
            await current.start()
            guard current.ready else { throw RelicError.message(current.error) }
            try await current.savePreferences(["lang": language, "theme": theme, "font": "medium", "density": "comfortable", "accent": "clay", "notify": false])
            NSApp.appearance = NSAppearance(named: theme == "dark" ? .darkAqua : .aqua)
            for old in NSApp.windows { old.orderOut(nil); old.contentView = nil }
            let window = NSWindow(contentRect: NSRect(x: 40, y: 60, width: 1440, height: 900),
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            let host = NSHostingView(rootView: MainView().environmentObject(current))
            host.sizingOptions = []; host.autoresizingMask = [.width, .height]
            window.contentView = host; WindowChrome.apply(to: window)
            let placementName = "Relic.WindowCapture." + UUID().uuidString
            let placement = ApplicationWindowPlacement(window: window, autosaveName: placementName)
            let initialMinimum = window.minSize
            defer { window.setFrameAutosaveName(""); NSWindow.removeFrame(usingName: placementName); window.orderOut(nil); window.contentView = nil; window.close() }
            for item in manifest["cases"].rows {
                let prepared = try await current.post(fixture["scene_endpoint"].text, ["scene": item["scene"].text])
                guard prepared["scene"].text == item["scene"].text else { throw RelicError.message("Fixture scene was not prepared") }
                try await current.select(fixture["org"].text)
                current.sheet = nil; current.appMenu = nil; current.recipientPicker = false
                current.sidebarOpen = true; current.panelOpen = item["width"].integer > 1180; current.pane = "overview"
                let size = NSSize(width: CGFloat(item["width"].integer), height: CGFloat(item["height"].integer))
                window.setFrame(NSRect(x: 40, y: 60, width: size.width, height: size.height), display: true)
                window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
                host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); WindowChrome.positionButtons(in: window)
                try await Task.sleep(for: .milliseconds(750))
                try await PerformanceRendering.waitForContent(current, window: window)
                host.layoutSubtreeIfNeeded(); window.displayIfNeeded(); WindowChrome.positionButtons(in: window)
                let file = output.appendingPathComponent(item["file"].text), number = window.windowNumber
                try await Task.detached {
                    let process = Process(), errorPipe = Pipe()
                    process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                    process.arguments = ["-x", "-o", "-l", String(number), file.path]
                    process.standardError = errorPipe
                    try process.run(); process.waitUntilExit()
                    guard process.terminationStatus == 0 else {
                        throw RelicError.message("screencapture: " + String(decoding: errorPipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self))
                    }
                }.value
                guard FileManager.default.fileExists(atPath: file.path) else { throw RelicError.message("Whole-window screenshot was not created") }
                let buttons: [[String: Any]] = [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton].compactMap { type in
                    guard let button = window.standardWindowButton(type) else { return nil }
                    let rect = window.convertToScreen(button.convert(button.bounds, to: nil))
                    return ["type": type.rawValue, "frame": ElementCapture.box(rect), "hidden": button.isHidden,
                        "enabled": button.isEnabled, "native_action": button.action.map(NSStringFromSelector) as Any? ?? NSNull()]
                }
                let readiness = RenderReadiness.observation(in: window, expectInspector: current.panelOpen)
                guard readiness.ready, readiness.markdown > 0 else { throw RelicError.message("Whole-window capture has no prepared visible conversation") }
                guard let bottomGap = ConversationKeyboardMount.bottomGap(in: window), bottomGap <= 2 else {
                    throw RelicError.message("Whole-window capture clips the latest conversation: bottom gap \(ConversationKeyboardMount.bottomGap(in: window) ?? -1) pt")
                }
                let record: [String: Any] = ["case_id": item["id"].text, "file": file.lastPathComponent,
                    "conversation_bottom_gap_pt": bottomGap,
                    "content_readiness": readiness.record,
                    "provider": "/usr/sbin/screencapture -x -o -l", "window_number": number,
                    "window_frame": ElementCapture.box(window.frame), "content_bounds": ElementCapture.box(host.bounds),
                    "client_screen_frame": ElementCapture.box(window.convertToScreen(host.convert(host.bounds, to: nil))),
                    "backing_scale": window.backingScaleFactor,
                    "initial_window_frame": ElementCapture.box(placement.initialFrame),
                    "visible_screen_frame": ElementCapture.box(placement.initialVisibleFrame),
                    "minimum_window_size": ["width": initialMinimum.width, "height": initialMinimum.height],
                    "inspector_overlay": InspectorGeometry.overlaysConversation(window: host.bounds.width),
                    "sidebar_width_pt": InspectorGeometry.sidebarWidth(window: host.bounds.width),
                    "title_hidden": window.titleVisibility == .hidden, "titlebar_transparent": window.titlebarAppearsTransparent,
                    "full_size_content": window.styleMask.contains(.fullSizeContentView), "traffic_lights": buttons,
                    "theme": theme, "language": language]
                try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
                    .write(to: output.appendingPathComponent(item["id"].text + ".window-chrome.json"))
                results.append(record)
            }
        } catch { errors.append(String(describing: error)) }
        try? JSONSerialization.data(withJSONObject: ["count": results.count, "cases": results, "errors": errors], options: [.prettyPrinted, .sortedKeys])
            .write(to: URL(fileURLWithPath: path).deletingLastPathComponent().appendingPathComponent("complete.json"))
        model?.stop(); display?.restore()
        for error in errors { fputs(error + "\n", stderr) }
        NSApp.terminate(nil)
    }
}
