import AppKit
import SwiftUI
import RelicCore

@MainActor final class SettingsNavigationTrace {
    private(set) var events: [[String: Any]] = []
    func receivedHover(_ value: Bool) {
        let pointer = NSEvent.mouseLocation
        events.append(["provider": "production SettingsNavigationButton.onHover", "hovered": value,
            "pointer_screen": ["x": pointer.x, "y": pointer.y], "uptime": ProcessInfo.processInfo.systemUptime])
    }
}

struct SettingsNavigationProbe: NSViewRepresentable {
    let key: String, owner: String
    let selected: Bool, hovered: Bool
    let trace: SettingsNavigationTrace
    private static let live = NSHashTable<Probe>.weakObjects()
    func makeNSView(context: Context) -> Probe { let view = Probe(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: Probe, context: Context) { view.key = key; view.owner = owner; view.selected = selected; view.hovered = hovered; view.trace = trace }
    static func buttons(window: NSWindow) -> [Probe] { live.allObjects.filter { $0.window === window && NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true } }
    final class Probe: NSView {
        var key = "", owner = ""
        var selected = false, hovered = false
        weak var trace: SettingsNavigationTrace?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        var screenBounds: NSRect { window.map { $0.convertToScreen(convert(bounds, to: nil)) } ?? .null }
        func observation() -> [String: Any] {
            ["key": key, "owner": owner, "identity": String(describing: ObjectIdentifier(self)),
             "selected": selected, "hovered": hovered, "screen_bounds": ElementCapture.box(screenBounds),
             "hover_callbacks": trace?.events as Any? ?? NSNull()]
        }
    }
}

/// Passive bounds of the production page. Content is read from the mounted
/// native text/control objects inside this allocation, never from expected text.
struct SettingsContentProbe: NSViewRepresentable {
    private static let live = NSHashTable<Probe>.weakObjects()
    func makeNSView(context: Context) -> Probe { let view = Probe(); Self.live.add(view); return view }
    func updateNSView(_ view: Probe, context: Context) {}
    static func pages(window: NSWindow) -> [Probe] { live.allObjects.filter { $0.window === window && NativeVisibility.screenClip($0).map { !$0.isEmpty && !$0.isNull } == true } }
    final class Probe: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        func observation() -> [String: Any] {
            guard let window, let root = window.contentView, let clip = NativeVisibility.screenClip(self) else { return [:] }
            var content: [[String: Any]] = []
            func walk(_ view: NSView) {
                if let bounds = NativeVisibility.screenClip(view), !bounds.intersection(clip).isEmpty, !bounds.intersection(clip).isNull {
                    var row: [String: Any] = ["identity": String(describing: ObjectIdentifier(view)), "class": String(describing: type(of: view)), "screen_bounds": ElementCapture.box(bounds)]
                    if let text = view as? NSTextView {
                        row["text"] = text.string; row["selected_range"] = [text.selectedRange().location, text.selectedRange().length]; content.append(row)
                    } else if let control = view as? NSControl {
                        row["text"] = control.stringValue; row["enabled"] = control.isEnabled
                        if let button = control as? NSButton { row["selected"] = button.state.rawValue }
                        content.append(row)
                    }
                }
                for child in view.subviews { walk(child) }
            }
            walk(root)
            return ["identity": String(describing: ObjectIdentifier(self)), "screen_bounds": ElementCapture.box(clip), "native_content": content]
        }
    }
}

/// Receipts from the real pointer and production selection/hover bindings.
/// This observer never selects a tab, supplies colors, or resets a moving state.
@MainActor final class SettingsNavigationCaptureSession {
    private let model: Model
    private weak var window: NSWindow?
    private let path: URL
    private let originalMouseEvents: Bool
    private var monitor: Any?
    private var nativeEvents: [[String: Any]] = []
    private var baseline: Data?
    private var receipt: [String: Any] = ["provider": "actual native settings navigation pointer, production bindings and paint surfaces", "observations": [] as [[String: Any]]]
    init(model: Model, window: NSWindow, path: URL) {
        self.model = model; self.window = window; self.path = path; originalMouseEvents = window.acceptsMouseMovedEvents
        window.acceptsMouseMovedEvents = true
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.mouseMoved, .mouseEntered, .mouseExited, .leftMouseDown, .leftMouseUp, .keyDown]) { [weak self, weak window] event in
            guard let self, let window, event.window === window else { return event }
            self.nativeEvents.append(["type": event.type.rawValue, "timestamp": event.timestamp,
                "location_window": ["x": event.locationInWindow.x, "y": event.locationInWindow.y]])
            return event
        }
    }
    private func state() throws -> [String: Any] {
        guard let window, let root = window.contentView else { throw RelicError.message("Settings hover lost its native window") }
        let buttons = SettingsNavigationProbe.buttons(window: window).sorted { $0.key < $1.key }
        let canvas = window.convertToScreen(root.convert(root.bounds, to: nil))
        let surfaces = SurfacePaintProbe.snapshots(in: canvas)
        let pointer = NSEvent.mouseLocation
        return ["window_identity": String(describing: ObjectIdentifier(window)), "root_identity": String(describing: ObjectIdentifier(root)),
            "current_section": model.settingsSection, "sheet": model.sheet?.rawValue as Any? ?? NSNull(),
            "preferences": model.preferences.raw, "pages": SettingsContentProbe.pages(window: window).map { $0.observation() },
            "buttons": buttons.map { button in
                var row = button.observation()
                row["paint_surfaces"] = surfaces.filter { $0["owner"] as? String == button.owner }.map {
                    ["bounds": $0["bounds"] ?? NSNull(), "style": $0["style"] ?? NSNull(),
                     "identity": ($0["evidence"] as? [String: Any])?["identity"] ?? NSNull()]
                }
                return row
            }, "pointer_screen": ["x": pointer.x, "y": pointer.y], "native_events": nativeEvents]
    }
    func perform() async throws {
        defer { save() }
        guard let window else { throw RelicError.message("Settings hover has no native window") }
        receipt["before_action"] = try state()
        let targets = SettingsNavigationProbe.buttons(window: window).filter { $0.key == "notify" }
        guard model.settingsSection == "appearance", targets.count == 1, let target = targets.first,
              !target.selected, !target.hovered, !target.screenBounds.isEmpty else {
            throw RelicError.message("Settings hover requires the actual unselected Notifications item and Appearance page")
        }
        try VisualCapture.movePointer(to: NSPoint(x: target.screenBounds.midX, y: target.screenBounds.midY))
        try await Task.sleep(for: .milliseconds(250))
        try observe("after-action")
    }
    func observe(_ phase: String) throws {
        defer { save() }
        let actual = try state()
        var row = actual; row["phase"] = phase; row["uptime"] = ProcessInfo.processInfo.systemUptime
        var observations = receipt["observations"] as? [[String: Any]] ?? []; observations.append(row); receipt["observations"] = observations
        guard let window else { throw RelicError.message("Settings hover lost its native window") }
        let buttons = SettingsNavigationProbe.buttons(window: window)
        let target = buttons.filter { $0.key == "notify" }, selected = buttons.filter { $0.selected }
        guard model.sheet == .settings, model.settingsSection == "appearance", selected.count == 1, selected.first?.key == "appearance",
              target.count == 1, target.first?.hovered == true, target.first?.screenBounds.contains(NSEvent.mouseLocation) == true,
              target.first?.trace?.events.last?["hovered"] as? Bool == true else {
            receipt["status"] = "failed"; throw RelicError.message("Settings navigation did not retain its actual hover and Appearance selection")
        }
        let rows = actual["buttons"] as? [[String: Any]] ?? [], pages = actual["pages"] as? [[String: Any]] ?? []
        guard rows.count == 7, rows.allSatisfy({ ($0["paint_surfaces"] as? [[String: Any]])?.count == 1 }),
              pages.count == 1, (pages.first?["native_content"] as? [[String: Any]])?.isEmpty == false else {
            receipt["status"] = "failed"; throw RelicError.message("Settings hover has incomplete actual navigation paint or native page content")
        }
        guard !nativeEvents.contains(where: { [NSEvent.EventType.leftMouseDown.rawValue, NSEvent.EventType.leftMouseUp.rawValue, NSEvent.EventType.keyDown.rawValue].contains($0["type"] as? UInt ?? UInt.max) }) else {
            receipt["status"] = "failed"; throw RelicError.message("Settings hover received a click or key instead of pointer-only interaction")
        }
        let encoded = try JSONSerialization.data(withJSONObject: actual, options: [.sortedKeys])
        if let baseline, baseline != encoded { receipt["status"] = "failed"; throw RelicError.message("Native settings hover selection, geometry, paint or input changed during capture") }
        baseline = encoded; receipt["status"] = "stable"
    }
    func annotateElements(_ file: URL) throws {
        var value = try JSONSerialization.jsonObject(with: Data(contentsOf: file)) as! [String: Any]
        var evidence = value["capture_evidence"] as? [String: Any] ?? [:]
        evidence["settings_navigation_action"] = receipt; value["capture_evidence"] = evidence
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: file)
    }
    private func save() { if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys]) { try? data.write(to: path) } }
    func finish() {
        if let monitor { NSEvent.removeMonitor(monitor); self.monitor = nil }
        window?.acceptsMouseMovedEvents = originalMouseEvents; save()
    }
}
