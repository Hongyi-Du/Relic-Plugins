import AppKit
import SwiftUI
import QuartzCore
import RelicCore

// CI-only capture of the real application window and native controls. The shared
// harness owns fixture creation, reference captures and side-by-side composition.
@MainActor enum VisualCapture {
    private static var started = false
    private static var captureWindow: NSWindow?
    static var enabled: Bool { ProcessInfo.processInfo.environment["RELIC_VISUAL_MANIFEST"] != nil }
    static func run(_ model: Model) async {
        guard !started else { return }; started = true
        let env = ProcessInfo.processInfo.environment
        guard let manifestPath = env["RELIC_VISUAL_MANIFEST"] else { return }
        let manifestURL = URL(fileURLWithPath: manifestPath)
        var results: [[String: Any]] = []
        do {
            guard env["GITHUB_ACTIONS"] == "true" else { throw RelicError.message("Visual capture is restricted to GitHub Actions") }
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)))
            let output = URL(fileURLWithPath: manifest["output"].text, isDirectory: true)
            let fixture = manifest["fixture"], language = Words.normalize(manifest["lang"].text), theme = manifest["theme"].text
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            model.client = try Client(port: fixture["port"].integer, token: fixture["token"].text)
            await model.start()
            guard model.ready else { throw RelicError.message(model.error) }
            // Standard NSWindow clamps oversized windows to the runner display.
            // This CI window renders the production view at the requested bounds.
            for old in NSApp.windows { old.orderOut(nil); old.contentView = nil }
            let window = CaptureWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            let hosting = NSHostingView(rootView: MainView().environmentObject(model))
            hosting.sizingOptions = []; window.contentView = hosting; captureWindow = window
            window.isReleasedWhenClosed = false
            try await model.savePreferences(["lang": language, "theme": theme, "font": "medium", "density": "comfortable", "accent": "clay", "notify": false])
            NSApp.appearance = NSAppearance(named: theme == "dark" ? .darkAqua : .aqua)
            for item in manifest["cases"].rows {
                let scene = item["scene"].text, width = item["width"].integer, height = item["height"].integer
                for editor in textEditors(window.contentView) { editor.closeMentions() }
                model.sheet = nil; model.error = ""; model.notice = ""; model.search = ""
                model.sidebarOpen = true; model.panelOpen = width > 1180; model.folded = []
                model.digestOpen = false; model.plainMode = false; model.quote = ""; model.draft = ""
                model.detailTask = ""; model.detailFilter = "open"; model.editMember = ""
                model.newSecretary = false; model.memberMode = "app"; model.expandRules = false
                model.appMenu = nil; model.recipientPicker = false
                model.defaults.set(276.0, forKey: "width.sidebar"); model.defaults.set(320.0, forKey: "width.panel"); model.defaults.set(520.0, forKey: "width.files")
                try await model.select(fixture["org"].text)
                model.pane = "overview"; model.detailMember = fixture["member"].text; model.cardMember = fixture["member"].text
                model.windowSize = CGSize(width: CGFloat(width), height: CGFloat(height))
                window.setContentSize(model.windowSize)
                hosting.setFrameSize(model.windowSize)
                window.setFrameOrigin(NSPoint(x: 0, y: 0)); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
                try await Task.sleep(for: .milliseconds(400))
                if scene.hasPrefix("settings-") { model.settingsSection = String(scene.dropFirst(9)); model.sheet = .settings }
                else if scene.hasPrefix("file-") { try await model.openFile(fixture["files"][String(scene.dropFirst(5))].text, line: scene == "file-code" ? 2 : 0) }
                else if scene.hasPrefix("menu-") { model.appMenu = String(scene.dropFirst(5)) }
                else {
                    switch scene {
                    case "group": break
                    case "private": try await model.select(fixture["org"].text, fixture["member"].text)
                    case "overview": model.setPane("overview")
                    case "workspace": model.setPane("workspace")
                    case "thread": try await model.openThread(fixture["thread"].text)
                    case "copies", "copy-rules": model.expandRules = scene == "copy-rules"; model.sheet = .copies
                    case "chart": model.sheet = .chart
                    case "new-org": model.sheet = .create
                    case "member-app", "member-host", "member-existing": model.openMemberForm(mode: String(scene.dropFirst(7)))
                    case "member-card": model.openCard(fixture["member"].text)
                    case "member-edit": model.editMember = fixture["member"].text; model.memberMode = "host"; model.sheet = .member
                    case "forward": model.cardMember = "advisor"; model.sheet = .forward
                    case "secretary": model.sheet = .secretary
                    case "tasks", "task-report": model.openDetails("tasks", task: scene == "task-report" ? fixture["task"].text : ""); if scene == "task-report" { model.detailFilter = "all" }
                    case "protocols": model.openDetails("protocols")
                    case "documents": model.openDetails("docs")
                    case "trajectory": model.openDetails("trace", member: fixture["member"].text)
                    case "shortcuts": model.sheet = .shortcuts
                    case "quote": model.setQuote(fixture["quote"].text, from: fixture["member"].text)
                    case "recipients": model.recipientPicker = true
                    case "mention": model.draft = "@"
                    case "digest": model.digest = fixture["digest"]; model.digestOpen = true
                    case "plain": model.plain = Dictionary(uniqueKeysWithValues: model.messages.map { ($0["id"].text, Node(["text": fixture["plain"].text])) }); model.plainMode = true
                    case "quick-start": model.organizations = []; model.organization = ""; model.snapshot = Node(); model.messages = []
                    default: throw RelicError.message("Unimplemented native scene: " + scene)
                    }
                }
                try await Task.sleep(for: .milliseconds(1100))
                if scene == "mention", let editor = textEditors(window.contentView).first {
                    window.makeFirstResponder(editor); editor.setSelectedRange(NSRange(location: 1, length: 0)); editor.showMentionSuggestions()
                    try await Task.sleep(for: .milliseconds(350))
                    guard editor.mentionSuggestionsVisible else { throw RelicError.message("Mention scene did not present the native member picker") }
                }
                guard model.error.isEmpty else { throw RelicError.message(scene + ": " + model.error) }
                try capture(window, to: output.appendingPathComponent(item["file"].text), width: width, height: height)
                try ElementCapture.write(window: window, png: output.appendingPathComponent(item["file"].text), item: item, language: language, theme: theme)
                results.append(["id": item["id"].text, "file": item["file"].text, "status": "captured"])
                print("Relic visual capture: " + item["file"].text); fflush(stdout)
            }
            try receipt([], count: results.count, beside: manifestURL)
            model.stop(); NSApp.terminate(nil)
        } catch {
            try? receipt([error.localizedDescription], count: results.count, beside: manifestURL)
            fputs("Relic visual capture failed: " + error.localizedDescription + "\n", stderr)
            model.stop(); exit(1)
        }
    }
    private static func textEditors(_ view: NSView?) -> [ComposerTextView] {
        guard let view else { return [] }; return (view as? ComposerTextView).map { [$0] } ?? view.subviews.flatMap { textEditors($0) }
    }
    private static func receipt(_ errors: [String], count: Int, beside manifest: URL) throws {
        try JSONSerialization.data(withJSONObject: ["errors": errors, "count": count], options: [.prettyPrinted, .sortedKeys]).write(to: manifest.deletingLastPathComponent().appendingPathComponent("complete.json"))
    }
    private static func capture(_ window: NSWindow, to path: URL, width: Int, height: Int) throws {
        // Cache the actual NSHostingView/AppKit tree (including NSTextView), which
        // ImageRenderer alone omits. Sheet windows are composited in native bounds.
        guard let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw RelicError.message("Cannot allocate native capture") }
        view.layoutSubtreeIfNeeded(); view.displayIfNeeded(); CATransaction.flush()
        print("Capture geometry: window=\(window.frame), view=\(view.bounds), bitmap=\(bitmap.pixelsWide)x\(bitmap.pixelsHigh)")
        guard abs(view.bounds.width - CGFloat(width)) < 1 && abs(view.bounds.height - CGFloat(height)) < 1 else { throw RelicError.message("Native view size differs from capture matrix: \(view.bounds)") }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let result = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: width * 4, bitsPerPixel: 32), let context = NSGraphicsContext(bitmapImageRep: result) else { throw RelicError.message("Cannot allocate PNG canvas") }
        NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = context
        let canvas = NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height))
        NSColor.windowBackgroundColor.setFill(); canvas.fill(); bitmap.draw(in: canvas)
        let contentRect = window.convertToScreen(view.bounds)
        for child in NSApp.windows where child !== window && child.isVisible && child.contentView != nil {
            guard let content = child.contentView, let childBitmap = content.bitmapImageRepForCachingDisplay(in: content.bounds) else { continue }
            content.layoutSubtreeIfNeeded(); content.displayIfNeeded(); content.cacheDisplay(in: content.bounds, to: childBitmap)
            if child === window.attachedSheet { NSColor.black.withAlphaComponent(0.18).setFill(); canvas.fill() }
            let childRect = child.convertToScreen(content.bounds)
            let rect = NSRect(x: childRect.minX - contentRect.minX, y: childRect.minY - contentRect.minY, width: childRect.width, height: childRect.height)
            NSGraphicsContext.saveGraphicsState()
            // cacheDisplay may flatten a transparent hosting view against black;
            // retain the native rounded window boundary for sheets/popovers.
            let radius: CGFloat = child === window.attachedSheet ? 16 : 12
            NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).addClip()
            childBitmap.draw(in: rect)
            NSGraphicsContext.restoreGraphicsState()
        }
        NSGraphicsContext.restoreGraphicsState()
        guard let png = result.representation(using: .png, properties: [:]) else { throw RelicError.message("Cannot encode native PNG") }
        try png.write(to: path)
    }
}

private final class CaptureWindow: NSWindow {
    override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect { frameRect }
}
