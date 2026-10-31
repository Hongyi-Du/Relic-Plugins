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
    static func run(_ initialModel: Model) async {
        guard !started else { return }; started = true
        var model = initialModel
        let env = ProcessInfo.processInfo.environment
        guard let manifestPath = env["RELIC_VISUAL_MANIFEST"] else { return }
        let manifestURL = URL(fileURLWithPath: manifestPath)
        var results: [[String: Any]] = []
        var caseErrors: [String] = []
        var display: CaptureDisplay?
        do {
            guard env["GITHUB_ACTIONS"] == "true" else { throw RelicError.message("Visual capture is restricted to GitHub Actions") }
            try "startup: initializing native capture".write(to: manifestURL.deletingLastPathComponent().appendingPathComponent("current-case.txt"), atomically: true, encoding: .utf8)
            print("Native capture bootstrap: \(manifestURL.path)"); fflush(stdout)
            NSTimeZone.default = TimeZone(secondsFromGMT: 0)!
            let manifest = Node(try JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)))
            let output = URL(fileURLWithPath: manifest["output"].text, isDirectory: true)
            let fixture = manifest["fixture"], language = Words.normalize(manifest["lang"].text), theme = manifest["theme"].text
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            display = try CaptureDisplay(cases: manifest["cases"].rows, output: output)
            try await Task.sleep(for: .milliseconds(250))
            model.client = try Client(port: fixture["port"].integer, token: fixture["token"].text)
            await model.start()
            guard model.ready else { throw RelicError.message(model.error) }
            // Standard NSWindow clamps oversized windows to the runner display.
            // This CI window renders the production view at the requested bounds.
            for old in NSApp.windows { old.orderOut(nil); old.contentView = nil }
            let window = CaptureWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            let hosting = NSHostingView(rootView: MainView().environmentObject(model).id("bootstrap"))
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
                let phases = CapturePhaseTrace(caseID: item["id"].text, output: output)
                var sceneMounted = false
                var caseDefaults: (UserDefaults, String)?
                var messageCapture: MessageCaptureSession?
                var resizeCapture: ResizeCaptureSession?
                var panelResizeCapture: PanelResizeCaptureSession?
                var settingsNavigationCapture: SettingsNavigationCaptureSession?
                defer { messageCapture?.finish(); settingsNavigationCapture?.finish(); model.stop(); if let (defaults, suite) = caseDefaults { defaults.removePersistentDomain(forName: suite) } }
                do {
                try phases.record("begin-case")
                let scene = item["scene"].text, width = item["width"].integer, height = item["height"].integer
                for editor in textEditors(window.contentView) { editor.closeMentions() }
                model.stop()
                // Reference capture creates a fresh page and clears both stores
                // for every case. Recreate our production model/view identity too,
                // so prior private-chat reads, focus and disclosure state cannot leak.
                let suite = "Relic.VisualCapture." + UUID().uuidString
                guard let defaults = UserDefaults(suiteName: suite) else { throw RelicError.message("Cannot create isolated native preferences") }
                caseDefaults = (defaults, suite)
                model = Model(client: try Client(port: fixture["port"].integer, token: fixture["token"].text), defaults: defaults)
                guard !fixture["scene_endpoint"].text.isEmpty else { throw RelicError.message("Visual fixture is missing its scene reset endpoint") }
                let prepared = try await model.post(fixture["scene_endpoint"].text, ["scene": scene])
                let isLive = ["live-busy", "live-tool-output", "live-typing"].contains(scene)
                guard prepared["scene"].text == scene, prepared["live"].flag == isLive,
                      !prepared["org"].text.isEmpty, !prepared["member"].text.isEmpty else {
                    throw RelicError.message("Visual fixture did not prepare the requested scene: " + scene)
                }
                try evidence(prepared.raw, suffix: ".scene-fixture.json", item: item, output: output)
                try item["id"].text.write(to: manifestURL.deletingLastPathComponent().appendingPathComponent("current-case.txt"), atomically: true, encoding: .utf8)
                await model.start()
                guard model.ready else { throw RelicError.message(model.error) }
                ScrollGeometryTrace.reset()
                hosting.rootView = MainView().environmentObject(model).id(item["id"].text)
                sceneMounted = true
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
                // Leave a physical margin for the real pointer even when the
                // content exceeds the runner display. PNG coordinates remain
                // relative to the unchanged requested content size.
                window.setFrameOrigin(NSPoint(x: 20, y: 20)); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
                try movePointer(to: NSPoint(x: 10, y: 10))
                try await Task.sleep(for: .milliseconds(400))
                // Finish the initial production layout and queued scroll before
                // invoking the next scene action. Otherwise an initial bottom
                // request can coalesce with opening the wider File pane, while
                // the reference has already rendered its original conversation.
                try phases.record("before-initial-scroll-layout")
                let initialLayout = try await settledScrollLayout(hosting)
                try phases.record("after-initial-scroll-layout")
                try evidence(initialLayout, suffix: ".initial-layout.json", item: item, output: output)
                guard initialLayout["settled"] as? Bool == true else {
                    throw RelicError.message("Initial native scroll layout did not settle before the scene action")
                }
                if scene.hasPrefix("settings-") { model.settingsSection = scene == "settings-navigation-hover" ? "appearance" : String(scene.dropFirst(9)); model.sheet = .settings }
                else if scene.hasPrefix("file-") { try await model.openFile(fixture["files"][String(scene.dropFirst(5))].text, line: scene == "file-code" ? 2 : 0) }
                else if scene.hasPrefix("menu-") { model.appMenu = String(scene.dropFirst(5)) }
                else {
                    switch scene {
                case "group", "panel-resize-hover", "panel-resized", "empty-group", "long-conversation": break
                    case "message-hover", "message-copy-toast": break
                    case "live-busy", "live-tool-output", "live-typing":
                        // select reloads the real organization snapshot before
                        // loading the returned member's Hub turn and transcript.
                        try await model.select(prepared["org"].text, prepared["member"].text)
                        guard model.selectedMember["embedded"].flag, model.liveStatus["state"].text == prepared["state"].text,
                              !model.displayLiveItems.isEmpty else { throw RelicError.message("Prepared live state was not loaded: " + scene) }
                case "private", "empty-private": try await model.select(fixture["org"].text, fixture["member"].text)
                    case "overview": model.setPane("overview")
                    case "workspace": model.workspaceMember = fixture["member"].text; model.setPane("workspace")
                    case "thread": try await model.openThread(fixture["thread"].text)
                    case "copies", "copy-rules": model.expandRules = scene == "copy-rules"; model.sheet = .copies
                    case "chart": model.sheet = .chart
                    case "new-org", "new-org-textarea-resized": model.sheet = .create
                    case "member-app", "member-host", "member-existing": model.openMemberForm(mode: String(scene.dropFirst(7)))
                    case "member-host-model-suggestions": model.openMemberForm(mode: "host")
                    case "member-existing-seat-suggestions": model.openMemberForm(mode: "existing")
                    case "member-card", "member-card-rename", "member-card-model", "member-card-avatar-hover": model.openCard(fixture["member"].text)
                    case "member-edit": model.editMember = fixture["member"].text; model.memberMode = "host"; model.sheet = .member
                    case "forward": model.cardMember = "advisor"; model.sheet = .forward
                    case "secretary": model.sheet = .secretary
                    case "tasks", "task-report": model.openDetails("tasks", task: scene == "task-report" ? fixture["task"].text : ""); if scene == "task-report" { model.detailFilter = "all" }
                    case "protocols": model.openDetails("protocols")
                    case "documents": model.openDetails("docs"); model.detailDocument = model.snapshot["documents"].rows.first?["key"].text ?? ""
                    case "trajectory": model.openDetails("trace", member: fixture["member"].text)
                    case "shortcuts": model.sheet = .shortcuts
                    case "quote": model.setQuote(fixture["quote"].text, from: fixture["member"].text)
                    case "recipients":
                        guard let screen = accessibilityFrame(identifier: "relic-text-button/recipients", root: hosting) else {
                            throw RelicError.message("Recipients scene has no mounted native composer button")
                        }
                        try click(screen, window: window)
                        try await Task.sleep(for: .milliseconds(350))
                        guard model.recipientPicker, !model.recipientAnchor.isEmpty else {
                            throw RelicError.message("Native recipient button did not open its anchored menu")
                        }
                        try evidence(["provider": "native mouse gesture on mounted composer button", "button_screen_bounds": ElementCapture.box(screen),
                            "production_content_anchor": ElementCapture.box(model.recipientAnchor)], suffix: ".scene-action.json", item: item, output: output)
                    case "mention": model.draft = ""
                    case "digest": model.digest = fixture["digest"]; model.digestOpen = true
                    case "plain": model.plain = Dictionary(uniqueKeysWithValues: model.messages.map { ($0["id"].text, Node(["text": fixture["plain"].text])) }); model.plainMode = true
                    case "quick-start": model.setSelection(ChatSelection(), record: false); model.organizations = []
                    default: throw RelicError.message("Unimplemented native scene: " + scene)
                    }
                }
                try await Task.sleep(for: .milliseconds(1100))
                if scene == "settings-navigation-hover" {
                    settingsNavigationCapture = SettingsNavigationCaptureSession(model: model, window: window, path: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    try await settingsNavigationCapture?.perform()
                }
                if ["member-app", "member-host", "member-existing", "member-edit", "member-host-model-suggestions", "member-existing-seat-suggestions"].contains(scene) {
                    let key = scene == "member-app" ? "member.create_member" : scene == "member-edit" ? "common.save" : scene.hasPrefix("member-existing") ? "member.bind" : "member.create_start"
                    let deadline = ContinuousClock.now.advanced(by: .seconds(20))
                    while accessibilityFrame(root: hosting, matches: { attributes in
                        attributes["role"] as? String == "AXButton" && attributes["enabled"] as? Bool == true &&
                        ["label", "title", "value"].contains { attributes[$0] as? String == model.t(key) }
                    }) == nil {
                        guard model.error.isEmpty, ContinuousClock.now < deadline else { throw RelicError.message("Native member form did not finish loading its real options: " + scene + ": " + model.error) }
                        try await Task.sleep(for: .milliseconds(100))
                    }
                }
                if scene == "member-card" || scene.hasPrefix("member-card-") {
                    let readiness = try await waitForMemberCard(model.cardMember, window: window)
                    try evidence(readiness, suffix: ".card-readiness.json", item: item, output: output)
                }
                if scene.hasPrefix("member-card-") {
                    try phases.record("before-member-card-action")
                    let action = try await openMemberCardState(scene, model: model, window: window,
                        evidencePath: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    try phases.record("after-member-card-action")
                    try evidence(action, suffix: ".scene-action.json", item: item, output: output)
                }
                if scene == "message-hover" || scene == "message-copy-toast" {
                    let action = try await openMessageAction(scene, messageID: fixture["thread"].text, model: model, window: window,
                        evidencePath: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    messageCapture = MessageCaptureSession(model: model, messageID: fixture["thread"].text, copying: scene == "message-copy-toast", action: action, path: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    try await messageCapture?.begin(window: window)
                }
                if scene == "live-tool-output" {
                    let action = try await openLiveOutput(prepared, model: model, window: window)
                    try evidence(action, suffix: ".scene-action.json", item: item, output: output)
                }
                if scene == "member-host-model-suggestions" || scene == "member-existing-seat-suggestions" {
                    try await openInputSuggestions(scene == "member-host-model-suggestions" ? "member-model" : "member-seat-name", window: window)
                }
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
                if scene == "new-org-textarea-resized" {
                    resizeCapture = try ResizeCaptureSession(window: window, path: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    try await resizeCapture?.perform(window: window)
                }
                if scene == "panel-resize-hover" || scene == "panel-resized" {
                    if !model.panelOpen {
                        let title = model.t("appbar.pane_shortcut", ["pane": model.t(Choices.panes[0].1), "key": "Option+1"])
                        guard let control = accessibilityFrame(root: hosting, matches: { $0["role"] as? String == "AXButton" && $0["label"] as? String == title }) else {
                            throw RelicError.message("Cannot find the actual toolbar Overview control")
                        }
                        try click(control, window: window)
                        try await Task.sleep(for: .milliseconds(250))
                    }
                    guard model.panelOpen, model.pane == "overview" else { throw RelicError.message("Real toolbar click did not open Overview for resizing") }
                    panelResizeCapture = try PanelResizeCaptureSession(window: window, path: output.appendingPathComponent(item["id"].text + ".scene-action.json"))
                    try await panelResizeCapture?.perform(window: window, drag: scene == "panel-resized")
                }
                try phases.record("after-scene-actions")
                guard model.error.isEmpty else { throw RelicError.message(scene + ": " + model.error) }
                if scene == "quick-start" {
                    guard model.organizations.isEmpty && model.organization.isEmpty && model.snapshot["org"].isNull else { throw RelicError.message("Quick-start state was replaced before capture") }
                }
                if !["settings-navigation-hover", "member-card-avatar-hover", "message-hover", "message-copy-toast", "new-org-textarea-resized", "panel-resize-hover", "panel-resized"].contains(scene) {
                    try phases.record("before-pointer-leave")
                    try movePointer(to: NSPoint(x: 10, y: 10))
                    try phases.record("before-pointer-settle")
                    try await Task.sleep(for: .milliseconds(80))
                    try phases.record("after-pointer-settle")
                    let screen = window.convertToScreen(hosting.convert(hosting.bounds, to: nil))
                    guard !screen.contains(NSEvent.mouseLocation) else { throw RelicError.message("Native pointer remained inside a non-hover capture") }
                }
                if isLive {
                    let clocks = TypingIndicatorView.pauseVisibleClocks()
                    if scene == "live-typing" {
                        guard clocks.count == 1, (clocks[0]["drawn"] as? [[String: Any]])?.count == 3,
                              (clocks[0]["after"] as? [String: Any])?["is_animating"] as? Bool == false,
                              (clocks[0]["after"] as? [String: Any])?["current_progress"] as? Double == 0 else {
                            throw RelicError.message("Live typing animation was not measured after pausing its real AppKit clock")
                        }
                    }
                    try evidence(["provider": "production NSAnimation clocks", "clocks": clocks], suffix: ".animations.json", item: item, output: output)
                }
                try phases.record("before-final-layout")
                hosting.layoutSubtreeIfNeeded()
                try phases.record("before-final-display")
                hosting.displayIfNeeded(); CATransaction.flush()
                try phases.record("after-final-display")
                let geometry = GeometryCaptureSession(path: output.appendingPathComponent(item["id"].text + ".native-geometry.json"))
                try geometry.observe("before-screenshot", window: window)
                try resizeCapture?.observe("before-screenshot")
                try panelResizeCapture?.observe("before-screenshot")
                try messageCapture?.observe("before-screenshot", window: window)
                try settingsNavigationCapture?.observe("before-screenshot")
                try phases.record("before-screenshot")
                try capture(window, to: output.appendingPathComponent(item["file"].text), width: width, height: height)
                try phases.record("after-screenshot")
                try messageCapture?.observe("after-screenshot", window: window)
                try settingsNavigationCapture?.observe("after-screenshot")
                try geometry.observe("after-screenshot", window: window)
                try resizeCapture?.observe("after-screenshot")
                try panelResizeCapture?.observe("after-screenshot")
                try phases.record("before-element-extraction")
                try ElementCapture.write(window: window, png: output.appendingPathComponent(item["file"].text), item: item, language: language, theme: theme)
                try phases.record("after-element-extraction")
                try messageCapture?.observe("after-native-source-and-element-extraction", window: window)
                try settingsNavigationCapture?.observe("after-native-source-and-element-extraction")
                try geometry.observe("after-native-source-and-element-extraction", window: window)
                try resizeCapture?.observe("after-native-source-and-element-extraction")
                try panelResizeCapture?.observe("after-native-source-and-element-extraction")
                try messageCapture?.annotateElements(output.appendingPathComponent(item["id"].text + ".elements.json"))
                try resizeCapture?.annotateElements(output.appendingPathComponent(item["id"].text + ".elements.json"))
                try panelResizeCapture?.annotateElements(output.appendingPathComponent(item["id"].text + ".elements.json"))
                try settingsNavigationCapture?.annotateElements(output.appendingPathComponent(item["id"].text + ".elements.json"))
                results.append(["id": item["id"].text, "file": item["file"].text, "status": "captured"])
                print("Relic visual capture: " + item["file"].text); fflush(stdout)
                } catch {
                    try? phases.record("caught-case-error")
                    let detail = item["id"].text + ": " + error.localizedDescription
                    caseErrors.append(detail)
                    try? evidence(["error": detail, "scene_mounted": sceneMounted], suffix: ".capture-error.json", item: item, output: output)
                    fputs("Relic visual case failed: " + detail + "\n", stderr)
                    // Preserve the actual failed state for diagnosis, never the
                    // prior case's window. Mark it as a capture failure in both
                    // the receipt and canonical extraction; then attempt every
                    // remaining case with the existing fresh Model/view reset.
                    if sceneMounted {
                        do {
                            let png = output.appendingPathComponent(item["file"].text)
                            if FileManager.default.fileExists(atPath: png.path) {
                                let diagnostics = output.appendingPathComponent("diagnostics", isDirectory: true)
                                try FileManager.default.createDirectory(at: diagnostics, withIntermediateDirectories: true)
                                try FileManager.default.copyItem(at: png, to: diagnostics.appendingPathComponent(item["id"].text + ".before-capture-error.png"))
                            }
                            try capture(window, to: png, width: item["width"].integer, height: item["height"].integer)
                            try ElementCapture.write(window: window, png: png, item: item, language: language, theme: theme, captureErrors: [detail])
                            results.append(["id": item["id"].text, "file": item["file"].text, "status": "failed-state-captured", "error": detail])
                        } catch { caseErrors.append(item["id"].text + ": failed-state evidence could not be captured: " + error.localizedDescription) }
                    }
                    fflush(stdout); fflush(stderr)
                }
            }
            // AX IPC needs a launched app. XCTest's command-line host returns
            // kAXErrorNotImplemented; this integration assertion runs in the real
            // bundle and still fails the visual job after preserving all captures.
            try await verifyCompoundAccessibilityLabels()
            try receipt(caseErrors, count: results.count, cases: results, beside: manifestURL)
            model.stop(); display?.restore()
            if !caseErrors.isEmpty { exit(1) }
            NSApp.terminate(nil)
        } catch {
            try? receipt(caseErrors + [error.localizedDescription], count: results.count, cases: results, beside: manifestURL)
            fputs("Relic visual capture failed: " + error.localizedDescription + "\n", stderr)
            model.stop(); display?.restore(); exit(1)
        }
    }
    private static func settledScrollLayout(_ root: NSView) async throws -> [String: Any] {
        func snapshot() -> [[String: Any]] {
            var rows: [[String: Any]] = []
            func visit(_ view: NSView) {
                if let scroll = view as? NSScrollView {
                    rows.append(["identity": String(describing: ObjectIdentifier(scroll)),
                        "frame": ElementCapture.box(scroll.frame), "clip": ElementCapture.box(scroll.contentView.bounds),
                        "document": scroll.documentView.map { ElementCapture.box($0.frame) } as Any? ?? NSNull(),
                        "needs_layout": scroll.needsLayout, "document_needs_layout": scroll.documentView?.needsLayout as Any? ?? NSNull()])
                }
                view.subviews.forEach(visit)
            }
            visit(root)
            return rows
        }
        var observations: [[String: Any]] = [], previous: Data?, stable = 0
        for _ in 0..<100 {
            root.layoutSubtreeIfNeeded(); root.displayIfNeeded(); CATransaction.flush()
            // Give callbacks scheduled by that actual layout their normal turn.
            try await Task.sleep(for: .milliseconds(50))
            let rows = snapshot()
            let data = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
            let ready = !rows.isEmpty && !root.needsLayout && rows.allSatisfy {
                $0["needs_layout"] as? Bool == false && $0["document_needs_layout"] as? Bool == false
            }
            stable = ready && data == previous ? stable + 1 : 0
            previous = data
            observations.append(["uptime": ProcessInfo.processInfo.systemUptime, "root_needs_layout": root.needsLayout,
                "scroll_views": rows, "stable_intervals": stable])
            if stable >= 3 {
                return ["provider": "actual native layout/display and queued-scroll readiness before scene action",
                    "settled": true, "observations": observations]
            }
        }
        return ["provider": "actual native layout/display and queued-scroll readiness before scene action",
            "settled": false, "observations": observations]
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
    private static func evidence(_ value: Any, suffix: String, item: Node, output: URL) throws {
        try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent(item["id"].text + suffix))
    }
    private static func waitForMemberCard(_ member: String, window: NSWindow) async throws -> [String: Any] {
        guard let content = window.contentView else { throw RelicError.message("Member card has no native content") }
        let identifier = "relic-member-card/" + member
        let start = ProcessInfo.processInfo.systemUptime
        let deadline = ContinuousClock.now.advanced(by: .seconds(20))
        while true {
            content.layoutSubtreeIfNeeded()
            if let frame = accessibilityFrame(identifier: identifier, root: content) {
                return ["source": "actual production card AX identity from the loaded server member name",
                    "member": member, "identifier": identifier, "bounds": ElementCapture.box(frame),
                    "elapsed_seconds": ProcessInfo.processInfo.systemUptime - start, "status": "loaded-and-laid-out"]
            }
            guard ContinuousClock.now < deadline else { throw RelicError.message("Native member card did not finish loading: " + member) }
            try await Task.sleep(for: .milliseconds(100))
        }
    }
    private static func openMemberCardState(_ scene: String, model: Model, window: NSWindow, evidencePath: URL) async throws -> [String: Any] {
        var receipt: [String: Any] = ["scene": scene, "status": "started", "completed": false]
        defer {
            if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]) { try? data.write(to: evidencePath) }
        }
        guard let content = window.contentView else { throw RelicError.message("Member card has no native content") }
        let target: NSRect?, expected: String
        if scene == "member-card-avatar-hover" {
            target = accessibilityFrame(identifier: "relic-row/member-avatar", root: content)
            expected = "relic-member-avatar-hover"
        } else {
            let label = model.t(scene == "member-card-rename" ? "card.rename_hint" : "common.change")
            target = accessibilityFrame(root: content) { attributes in
                attributes["role"] as? String == "AXButton" && ["label", "title", "value"].contains { attributes[$0] as? String == label }
            }
            expected = scene == "member-card-rename" ? "relic-input/member-rename" : "relic-dropdown/" + model.t("common.model")
        }
        guard let target else { throw RelicError.message("Member card action is not visible: " + scene) }
        receipt["target_screen_bounds"] = ElementCapture.box(target)
        receipt["expected_result_identifier"] = expected
        receipt["window_identity"] = String(describing: ObjectIdentifier(window))
        if scene == "member-card-avatar-hover" {
            try movePointer(to: NSPoint(x: target.midX, y: target.midY))
        } else { try click(target, window: window) }
        receipt["status"] = "dispatched-once"
        try await Task.sleep(for: .milliseconds(300))
        receipt["result_screen_bounds"] = accessibilityFrame(identifier: expected, root: content).map(ElementCapture.box) as Any? ?? NSNull()
        if scene == "member-card-avatar-hover" {
            let canvas = window.convertToScreen(content.convert(content.bounds, to: nil))
            let surfaces = SurfacePaintProbe.snapshots(in: canvas).filter { $0["owner"] as? String == expected }
            let labels = textViews(content).compactMap { $0 as? ReferenceLabelView }.filter {
                $0.productionOwner == expected && NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true
            }
            guard surfaces.count == 1, surfaces[0]["hovered"] as? Bool == true,
                  labels.count == 1, labels[0].string == model.t("card.change_avatar"), target.contains(NSEvent.mouseLocation) else {
                throw RelicError.message("Actual avatar hover did not retain its visible surface, text and pointer")
            }
            receipt.merge(["action": "native pointer motion at measured avatar", "target_screen_bounds": ElementCapture.box(target),
                "visible_overlay_text": labels[0].string, "overlay_text_bounds": ElementCapture.box(NativeVisibility.screenClip(labels[0])!),
                "overlay_surface_bounds": surfaces[0]["bounds"]!, "overlay_surface_style": surfaces[0]["style"]!,
                "overlay_surface_evidence": surfaces[0]["evidence"]!,
                "wrapper_AX_bounds": accessibilityFrame(identifier: expected, root: content).map(ElementCapture.box) as Any? ?? NSNull()], uniquingKeysWith: { _, actual in actual })
            receipt["status"] = "presented"; receipt["completed"] = true
            return receipt
        }
        guard accessibilityFrame(identifier: expected, root: content) != nil else { throw RelicError.message("Member card action did not present its real state: " + scene) }
        receipt["action"] = "native mouse down/up on measured card control"
        receipt["visible_result_identifier"] = expected; receipt["status"] = "presented"; receipt["completed"] = true
        return receipt
    }
    private static func openMessageAction(_ scene: String, messageID: String, model: Model, window: NSWindow, evidencePath: URL) async throws -> [String: Any] {
        var result: [String: Any] = ["action": "native pointer motion at measured production message", "message_id": messageID, "status": "started"]
        defer { if let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys, .prettyPrinted]) { try? data.write(to: evidencePath) } }
        let bounds = MessageInteractionAnchor.visibleBounds(messageID: messageID)
        guard bounds.count == 1, let target = bounds.first, let content = window.contentView else { throw RelicError.message("Expected one visible production message: " + messageID) }
        try movePointer(to: NSPoint(x: target.midX, y: target.midY))
        try await Task.sleep(for: .milliseconds(200))
        let identifier = "relic-icon-button/message-copy/" + messageID
        guard var control = accessibilityFrame(identifier: identifier, root: content) else { throw RelicError.message("Actual message hover did not expose its copy action") }
        result["message_screen_bounds"] = ElementCapture.box(target)
        result["copy_screen_bounds"] = ElementCapture.box(control)
        if scene == "message-copy-toast" {
            // Like the reference driver's real locator click, reveal the actual
            // control before dispatch. Its negative toolbar offset can leave
            // the button above the clipped stream at 1024x700.
            result["reveal_action"] = try MessageInteractionAnchor.revealAction(control, messageID: messageID, window: window)
            try await Task.sleep(for: .milliseconds(100))
            guard let updated = accessibilityFrame(identifier: identifier, root: content) else { throw RelicError.message("Copy control disappeared while revealing its scroll area") }
            control = updated; result["copy_screen_bounds_after_reveal"] = ElementCapture.box(control)
            result["clipboard_before"] = NSPasteboard.general.string(forType: .string) as Any? ?? NSNull()
            try click(control, window: window)
            let deadline = ContinuousClock.now.advanced(by: .seconds(1))
            while !model.toasts.contains(where: { $0.text == model.t("msg.copied") }) && ContinuousClock.now < deadline {
                try await Task.sleep(for: .milliseconds(20))
            }
            result["clipboard_after"] = NSPasteboard.general.string(forType: .string) as Any? ?? NSNull()
            result["toast_texts_after"] = model.toasts.map(\.text)
            guard let message = model.messages.first(where: { $0["id"].text == messageID }),
                  NSPasteboard.general.string(forType: .string) == message["body"].text,
                  model.toasts.contains(where: { $0.text == model.t("msg.copied") }) else { throw RelicError.message("Real message copy did not produce the expected clipboard content and toast") }
            result["action"] = "native hover then mouse down/up on the actual copy button"
            result["clipboard"] = NSPasteboard.general.string(forType: .string)
            result["toast_ids"] = model.toasts.map { $0.id.uuidString }
        }
        result["status"] = "completed"
        return result
    }
    private static func openLiveOutput(_ prepared: Node, model: Model, window: NSWindow) async throws -> [String: Any] {
        let matches = model.displayLiveItems.filter { $0["type"].text == "tool" && $0["title"].text == prepared["tool"]["title"].text }
        guard matches.count == 1, let tool = matches.first, let content = window.contentView,
              let frame = accessibilityFrame(identifier: "relic-row/live-tool/" + tool["id"].text, root: content) else {
            throw RelicError.message("Expected one actual live tool disclosure: " + prepared["tool"]["title"].text)
        }
        try click(frame, window: window)
        try await Task.sleep(for: .milliseconds(250))
        // Read the row's current bounds after the actual disclosure layout.
        // Production scrolling preserves the person's reading position; this
        // driver must not force a scroll offset to match the reference.
        guard let expandedFrame = accessibilityFrame(identifier: "relic-row/live-tool/" + tool["id"].text, root: content) else {
            throw RelicError.message("Expanded live tool row disappeared after its click")
        }
        let contentScreen = window.convertToScreen(content.convert(content.bounds, to: nil))
        let probes = SurfacePaintProbe.snapshots(in: contentScreen).filter { $0["owner"] as? String == "relic-row/live-tool/" + tool["id"].text }
        let outputFrame = accessibilityFrame(identifier: "relic-live-output/" + tool["id"].text, root: content)
        // An inert SwiftUI wrapper need not have an AX node. Require the actual
        // visible TextKit output below this expanded disclosure, retaining any
        // wrapper AX bounds independently rather than using an identifier as
        // evidence that text was painted.
        let outputs = textViews(content).filter { view in
            guard !view.isEditable, view.string == tool["text"].text,
                  let clip = NativeVisibility.screenClip(view), !clip.isNull, !clip.isEmpty else { return false }
            return clip.maxY <= expandedFrame.minY + 1 && clip.minX >= expandedFrame.minX - 1 && clip.maxX <= expandedFrame.maxX + 1
        }
        guard probes.count == 1, probes[0]["expanded"] as? Bool == true, outputs.count == 1, let output = outputs.first else {
            throw RelicError.message("Actual live tool disclosure did not remain open: tool=\(tool["id"].text), clicked=\(frame), probes=\(probes.count), expanded=\(probes.map { String(describing: $0["expanded"]) }), visible_text_outputs=\(outputs.count), wrapper_AX=\(String(describing: outputFrame))")
        }
        return ["action": "native mouse down/up on measured production tool disclosure", "tool_title": tool["title"].text, "tool_id": tool["id"].text,
                "open": true, "clicked_screen_bounds": ElementCapture.box(frame), "control_screen_bounds": ElementCapture.box(expandedFrame), "expanded_surface_evidence": probes[0]["evidence"]!,
                "visible_output": output.string, "output_screen_bounds": ElementCapture.box(NativeVisibility.screenClip(output)!), "wrapper_AX_bounds": outputFrame.map { ElementCapture.box($0) } as Any? ?? NSNull()]
    }
    private static func textViews(_ root: NSView) -> [NSTextView] { (root as? NSTextView).map { [$0] } ?? root.subviews.flatMap { textViews($0) } }
    private static func click(_ screen: NSRect, window: NSWindow) throws {
        try movePointer(to: NSPoint(x: screen.midX, y: screen.midY))
        let point = window.convertPoint(fromScreen: NSPoint(x: screen.midX, y: screen.midY))
        var events: [NSEvent] = []
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            guard let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0) else {
                throw RelicError.message("Cannot create native mouse event")
            }
            events.append(event)
        }
        // AppKit text fields/buttons may enter an event-tracking loop during
        // mouseDown. Queue the complete gesture before dispatch starts, so the
        // tracking loop can consume its mouseUp instead of waiting forever on
        // a synchronous sendEvent call that prevents the next line running.
        for event in events { NSApp.postEvent(event, atStart: false) }
        print("Queued native mouse gesture: window=\(window.windowNumber), point=\(point)"); fflush(stdout)
    }
    static func movePointer(to screen: NSPoint) throws {
        guard let primary = NSScreen.screens.first else { throw RelicError.message("No display for native pointer movement") }
        let point = CGPoint(x: screen.x, y: primary.frame.maxY - screen.y)
        guard CGWarpMouseCursorPosition(point) == .success,
              let event = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left) else { throw RelicError.message("Cannot dispatch actual native pointer movement") }
        event.post(tap: .cghidEventTap)
    }
    private static func accessibilityFrame(identifier: String, root: AnyObject) -> NSRect? {
        accessibilityFrame(root: root) { $0["identifier"] as? String == identifier }
    }
    private static func accessibilityFrame(root: AnyObject, matches: ([String: Any]) -> Bool) -> NSRect? {
        var seen = Set<ObjectIdentifier>()
        func walk(_ object: AnyObject) -> NSRect? {
            guard seen.insert(ObjectIdentifier(object)).inserted else { return nil }
            let attributes = RelicAXRead(object)
            if matches(attributes),
               attributes["hidden"] as? Bool != true,
               let frame = (attributes["frame"] as? NSValue)?.rectValue, !frame.isEmpty { return frame }
            for child in RelicAXChildren(object) { if let frame = walk(child as AnyObject) { return frame } }
            if let view = object as? NSView { for child in view.subviews { if let frame = walk(child) { return frame } } }
            return nil
        }
        return walk(root)
    }
    private static func openInputSuggestions(_ identifier: String, window: NSWindow) async throws {
        guard let content = window.contentView,
              let screen = accessibilityFrame(identifier: "relic-input/" + identifier, root: content) else {
            throw RelicError.message("Suggestion scene has no visible input: " + identifier)
        }
        // Exercise the real control through its measured location and native
        // event dispatch. The capture never constructs a substitute popup.
        try click(screen, window: window)
        try await Task.sleep(for: .milliseconds(100))
        for type in [NSEvent.EventType.keyDown, .keyUp] {
            guard let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil, characters: "\u{F701}", charactersIgnoringModifiers: "\u{F701}", isARepeat: false, keyCode: 125) else {
                throw RelicError.message("Cannot create Down Arrow event")
            }
            NSApp.postEvent(event, atStart: false)
        }
        print("Queued native Down Arrow: " + identifier); fflush(stdout)
        try await Task.sleep(for: .milliseconds(350))
        guard NSApp.windows.contains(where: { candidate in
            candidate.isVisible && candidate.contentView.map { accessibilityFrame(identifier: "relic-suggestions/" + identifier, root: $0) != nil } == true
        }) else { throw RelicError.message("Down Arrow did not open the native suggestions: " + identifier) }
    }
    private static func receipt(_ errors: [String], count: Int, cases: [[String: Any]], beside manifest: URL) throws {
        try JSONSerialization.data(withJSONObject: ["errors": errors, "count": count, "cases": cases], options: [.prettyPrinted, .sortedKeys]).write(to: manifest.deletingLastPathComponent().appendingPathComponent("complete.json"))
    }
    private static func capture(_ window: NSWindow, to path: URL, width: Int, height: Int) throws {
        // Cache the actual NSHostingView/AppKit tree (including NSTextView), which
        // ImageRenderer alone omits. Sheet windows are composited in native bounds.
        guard let view = window.contentView else { throw RelicError.message("Cannot allocate native capture") }
        view.layoutSubtreeIfNeeded(); view.displayIfNeeded(); CATransaction.flush()
        guard abs(view.bounds.width - CGFloat(width)) < 1 && abs(view.bounds.height - CGFloat(height)) < 1 else { throw RelicError.message("Native view size differs from capture matrix: \(view.bounds)") }
        guard let bitmap = CaptureRaster.forView(view) else { throw RelicError.message("Cannot allocate native capture") }
        print("Capture geometry: window=\(window.frame), view=\(view.bounds), bitmap=\(bitmap.pixelsWide)x\(bitmap.pixelsHigh)")
        let rootRaster = CaptureRaster.cache(view, into: bitmap)
        guard CaptureRaster.sRGBPixel(bitmap, x: bitmap.pixelsWide / 2, y: bitmap.pixelsHigh / 2)?[3] == 255 else {
            throw RelicError.message("Actual native window cache has no opaque center pixel")
        }
        var rasters = [rootRaster]
        guard let result = CaptureRaster.composite(width: width, height: height, draw: { canvas in
        NSColor.windowBackgroundColor.setFill(); canvas.fill(); bitmap.draw(in: canvas)
        let contentRect = window.convertToScreen(view.bounds)
        for child in NSApp.windows where child !== window && child.isVisible && child.contentView != nil {
            guard let content = child.contentView, let childBitmap = CaptureRaster.forView(content) else { continue }
            content.layoutSubtreeIfNeeded(); content.displayIfNeeded()
            rasters.append(CaptureRaster.cache(content, into: childBitmap))
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
        }) else { throw RelicError.message("Cannot composite actual native PNG canvas") }
        rasters.append(CaptureRaster.evidence(result))
        guard CaptureRaster.sRGBPixel(result, x: width / 2, y: height / 2)?[3] == 255 else {
            throw RelicError.message("Actual native window composite has no opaque center pixel")
        }
        guard let png = result.representation(using: .png, properties: [:]) else { throw RelicError.message("Cannot encode native PNG") }
        try png.write(to: path)
        try JSONSerialization.data(withJSONObject: ["provider": "actual native capture destinations", "bitmaps": rasters], options: [.prettyPrinted, .sortedKeys])
            .write(to: path.deletingPathExtension().appendingPathExtension("native-raster.json"))
    }
}

private final class CaptureWindow: NSWindow {
    override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect { frameRect }
}
