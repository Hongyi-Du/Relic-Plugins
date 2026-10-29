import AppKit
import SwiftUI
import QuartzCore
import RelicCore

// CI-only capture of the real application window and native controls. The shared
// harness owns fixture creation, reference captures and side-by-side composition.
@MainActor enum VisualCapture {
    private static var started = false
    static var enabled: Bool { ProcessInfo.processInfo.environment["RELIC_VISUAL_MANIFEST"] != nil }
    static func run(_ model: Model) async {
        guard !started else { return }; started = true
        let env = ProcessInfo.processInfo.environment
        guard let manifestPath = env["RELIC_VISUAL_MANIFEST"], let outputPath = env["RELIC_VISUAL_OUTPUT"] else { return }
        let output = URL(fileURLWithPath: outputPath, isDirectory: true)
        var results: [[String: Any]] = []
        do {
            guard env["CI"] == "true" else { throw RelicError.message("Visual capture is restricted to CI") }
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: manifestPath))))
            model.client = try Client(port: manifest["port"].integer, token: manifest["token"].text)
            await model.start()
            guard model.ready else { throw RelicError.message(model.error) }
            guard let window = NSApp.windows.first(where: { $0.contentView != nil && $0.styleMask.contains(.titled) }) else { throw RelicError.message("No native application window") }
            for scenario in manifest["scenarios"].rows {
                func field(_ key: String) -> String { scenario[key].isNull ? manifest[key].text : scenario[key].text }
                let id = scenario["id"].text, language = Words.normalize(field("lang")), theme = field("theme") == "dark" ? "dark" : "light"
                let width = scenario["width"].integer, height = scenario["height"].integer
                model.sheet = nil; model.error = ""; model.notice = ""; model.search = ""
                model.sidebarOpen = true; model.panelOpen = true; model.folded = []
                model.defaults.set(276.0, forKey: "width.sidebar"); model.defaults.set(320.0, forKey: "width.panel")
                try await model.savePreferences(["lang": language, "theme": theme, "font": "medium", "density": "comfortable", "accent": "clay", "notify": false])
                NSApp.appearance = NSAppearance(named: theme == "dark" ? .darkAqua : .aqua)
                let screen = field("screen")
                try await model.select(field("org"), screen == "private" ? field("member") : "")
                model.pane = field("pane").isEmpty ? "overview" : field("pane")
                if ["workspace", "files"].contains(screen) { model.pane = screen }
                if screen == "thread" { try await model.openThread(field("thread")) }
                if screen == "files" || screen == "file" { try await model.openFile(field("file")) }
                if screen == "plain" { model.togglePlain() }
                if screen == "digest" { model.toggleDigest() }
                model.settingsSection = field("settings_section").isEmpty ? "profile" : field("settings_section")
                model.detailTab = field("detail").isEmpty ? "trace" : field("detail")
                model.detailMember = field("member"); model.cardMember = field("member")
                model.memberMode = field("member_mode").isEmpty ? "app" : field("member_mode")
                model.editMember = ""; model.newSecretary = false
                let sheet = field("sheet").isEmpty ? screen : field("sheet")
                window.setContentSize(NSSize(width: CGFloat(width), height: CGFloat(height)))
                window.setFrameOrigin(NSPoint(x: 0, y: 0)); window.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
                try await Task.sleep(for: .milliseconds(350))
                if let value = Model.Sheet(rawValue: sheet) { model.sheet = value }
                try await Task.sleep(for: .milliseconds(1100))
                guard model.error.isEmpty else { throw RelicError.message(id + ": " + model.error) }
                let filename = id + "--" + language + "--" + theme + "--" + String(width) + "x" + String(height) + ".png"
                try capture(window, to: output.appendingPathComponent(filename), width: width, height: height)
                results.append(["id": id, "file": filename, "lang": language, "theme": theme, "width": width, "height": height, "status": "captured"])
                print("Relic visual capture: " + filename)
            }
            try write(results, to: output)
            model.stop(); NSApp.terminate(nil)
        } catch {
            results.append(["status": "failed", "error": error.localizedDescription]); try? write(results, to: output)
            fputs("Relic visual capture failed: " + error.localizedDescription + "\n", stderr)
            model.stop(); exit(1)
        }
    }
    private static func write(_ results: [[String: Any]], to output: URL) throws {
        try JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("capture-results.json"))
    }
    private static func capture(_ window: NSWindow, to path: URL, width: Int, height: Int) throws {
        // Cache the actual NSHostingView/AppKit tree (including NSTextView), which
        // ImageRenderer alone omits. Sheet windows are composited in native bounds.
        guard let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw RelicError.message("Cannot allocate native capture") }
        view.layoutSubtreeIfNeeded(); view.displayIfNeeded(); CATransaction.flush()
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let image = NSImage(size: NSSize(width: CGFloat(width), height: CGFloat(height)))
        image.lockFocus(); NSColor.windowBackgroundColor.setFill(); NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)).fill()
        bitmap.draw(in: NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
        if let sheet = window.attachedSheet, let content = sheet.contentView, let sheetBitmap = content.bitmapImageRepForCachingDisplay(in: content.bounds) {
            content.layoutSubtreeIfNeeded(); content.displayIfNeeded(); content.cacheDisplay(in: content.bounds, to: sheetBitmap)
            NSColor.black.withAlphaComponent(0.18).setFill(); NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)).fill()
            let rect = NSRect(x: (CGFloat(width) - content.bounds.width) / 2, y: (CGFloat(height) - content.bounds.height) / 2, width: content.bounds.width, height: content.bounds.height)
            sheetBitmap.draw(in: rect)
        }
        image.unlockFocus()
        guard let tiff = image.tiffRepresentation, let result = NSBitmapImageRep(data: tiff), let png = result.representation(using: .png, properties: [:]) else { throw RelicError.message("Cannot encode native PNG") }
        try png.write(to: path)
    }
}
