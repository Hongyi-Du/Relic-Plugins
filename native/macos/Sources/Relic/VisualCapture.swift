import AppKit
import SwiftUI
import QuartzCore
import ApplicationServices
import RelicCore
import RelicAX

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
            NSTimeZone.default = TimeZone(secondsFromGMT: 0)!
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
            hosting.sizingOptions = []; hosting.autoresizingMask = [.width, .height]
            window.contentView = hosting; captureWindow = window
            window.isReleasedWhenClosed = false
            // Ask the public AX client API for our own application's windows.
            // The main actor remains available to service the accessibility IPC.
            // No trust prompt is requested, and any AX error remains in the log.
            let axResult = await Task.detached {
                let application = AXUIElementCreateApplication(getpid())
                AXUIElementSetMessagingTimeout(application, 2)
                var windows: CFTypeRef?
                return AXUIElementCopyAttributeValue(application, kAXWindowsAttribute as CFString, &windows).rawValue
            }.value
            print("AX client initialization: \(axResult)")
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
                model.defaults.set(276.0, forKey: "width.sidebar"); model.defaults.set(340.0, forKey: "width.panel"); model.defaults.set(520.0, forKey: "width.files")
                try await model.select(fixture["org"].text)
                model.pane = "overview"; model.detailMember = fixture["member"].text; model.cardMember = fixture["member"].text
                // A resize synchronously invokes GeometryReader callbacks. They
                // publish the previous/transitional size back into the model;
                // never read that mutable value to size the next native view.
                let targetSize = CGSize(width: CGFloat(width), height: CGFloat(height))
                window.setContentSize(targetSize)
                hosting.setFrameSize(targetSize)
                model.windowSize = targetSize
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
                    case "workspace": model.workspaceMember = fixture["member"].text; model.setPane("workspace")
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
                    case "documents": model.openDetails("docs"); model.detailDocument = model.snapshot["documents"].rows.first?["key"].text ?? ""
                    case "trajectory": model.openDetails("trace", member: fixture["member"].text)
                    case "shortcuts": model.sheet = .shortcuts
                    case "quote": model.setQuote(fixture["quote"].text, from: fixture["member"].text)
                    case "recipients": model.recipientPicker = true
                    case "mention": model.draft = ""
                    case "digest": model.digest = fixture["digest"]; model.digestOpen = true
                    case "plain": model.plain = Dictionary(uniqueKeysWithValues: model.messages.map { ($0["id"].text, Node(["text": fixture["plain"].text])) }); model.plainMode = true
                    case "quick-start": model.setSelection(ChatSelection(), record: false); model.organizations = []
                    default: throw RelicError.message("Unimplemented native scene: " + scene)
                    }
                }
                try await Task.sleep(for: .milliseconds(1100))
                if scene == "mention" {
                    let candidates = textEditors(window.contentView).filter { $0.composerID == "main" && !$0.isHiddenOrHasHiddenAncestor && !$0.visibleRect.isEmpty }
                    guard candidates.count == 1, let editor = candidates.first else { throw RelicError.message("Mention scene requires one visible main composer, found " + String(candidates.count)) }
                    // Type into the same production editor that owns the popup.
                    // A stale cached thread editor must never receive this action.
                    window.makeFirstResponder(editor)
                    editor.insertText("@", replacementRange: NSRange(location: 0, length: (editor.string as NSString).length))
                    editor.setSelectedRange(NSRange(location: 1, length: 0)); editor.showMentionSuggestions()
                    try await Task.sleep(for: .milliseconds(350))
                    guard editor.mentionSuggestionsVisible else { throw RelicError.message("Mention scene did not present the native member picker: text=\(editor.string), selection=\(editor.selectedRange()), candidates=\(editor.mentionCandidates().count), frame=\(editor.frame), anchor=\(editor.mentionAnchorRect()), attached=\(editor.window != nil)") }
                }
                guard model.error.isEmpty else { throw RelicError.message(scene + ": " + model.error) }
                if scene == "quick-start" {
                    guard model.organizations.isEmpty && model.organization.isEmpty && model.snapshot["org"].isNull else { throw RelicError.message("Quick-start state was replaced before capture") }
                }
                try capture(window, to: output.appendingPathComponent(item["file"].text), width: width, height: height)
                try ElementCapture.write(window: window, png: output.appendingPathComponent(item["file"].text), item: item, language: language, theme: theme)
                results.append(["id": item["id"].text, "file": item["file"].text, "status": "captured"])
                print("Relic visual capture: " + item["file"].text); fflush(stdout)
            }
            // AX IPC needs a launched app. XCTest's command-line host returns
            // kAXErrorNotImplemented; this integration assertion runs in the real
            // bundle and still fails the visual job after preserving all captures.
            try await verifyCompoundAccessibilityLabels()
            try receipt([], count: results.count, beside: manifestURL)
            model.stop(); NSApp.terminate(nil)
        } catch {
            try? receipt([error.localizedDescription], count: results.count, beside: manifestURL)
            fputs("Relic visual capture failed: " + error.localizedDescription + "\n", stderr)
            model.stop(); exit(1)
        }
    }
    private static func verifyCompoundAccessibilityLabels() async throws {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 320, height: 100), styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let content = NSHostingView(rootView: Button {} label: {
            HStack { ReferenceLabel("Visible title"); ReferenceLabel("Visible subtitle", size: 12) }.accessibilityElement(children: .contain)
        }.buttonStyle(.plain))
        window.contentView = content; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let result = await Task.detached {
            let application = AXUIElementCreateApplication(getpid())
            AXUIElementSetMessagingTimeout(application, 2)
            var windows: CFTypeRef?
            return AXUIElementCopyAttributeValue(application, kAXWindowsAttribute as CFString, &windows).rawValue
        }.value
        guard result == 0 else { throw RelicError.message("Compound-label AX initialization failed: \(result)") }
        try await Task.sleep(for: .milliseconds(100))
        var labels: [String] = [], seen = Set<ObjectIdentifier>()
        func walk(_ object: AnyObject) {
            guard seen.insert(ObjectIdentifier(object)).inserted else { return }
            let attributes = RelicAXRead(object)
            for key in ["label", "title", "value"] { if let text = attributes[key] as? String { labels.append(text) } }
            for child in RelicAXChildren(object) { walk(child as AnyObject) }
            if let view = object as? NSView { for child in view.subviews { walk(child) } }
        }
        walk(content)
        guard labels.contains("Visible title"), labels.contains("Visible subtitle") else {
            throw RelicError.message("Compound native button lost independently visible labels: " + labels.description)
        }
        print("Compound-label accessibility integration check passed")
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
        guard let view = window.contentView else { throw RelicError.message("Cannot allocate native capture") }
        view.layoutSubtreeIfNeeded(); view.displayIfNeeded(); CATransaction.flush()
        guard abs(view.bounds.width - CGFloat(width)) < 1 && abs(view.bounds.height - CGFloat(height)) < 1 else { throw RelicError.message("Native view size differs from capture matrix: \(view.bounds)") }
        guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw RelicError.message("Cannot allocate native capture") }
        print("Capture geometry: window=\(window.frame), view=\(view.bounds), bitmap=\(bitmap.pixelsWide)x\(bitmap.pixelsHigh)")
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
