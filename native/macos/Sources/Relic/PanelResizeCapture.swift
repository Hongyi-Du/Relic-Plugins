import AppKit
import SwiftUI
import RelicCore

// These receipts observe the production SwiftUI gesture. The capture driver
// sends native input; it never assigns a pane width or synthesizes hover state.
@MainActor final class PanelResizeTrace: ObservableObject {
    var hovered = false
    var dragging = false
    var events: [[String: Any]] = []
    func hover(_ value: Bool) { hovered = value }
    func gesture(_ value: DragGesture.Value, ended: Bool) {
        dragging = !ended
        guard VisualCapture.enabled else { return }
        events.append(["phase": ended ? "ended" : "changed", "time": value.time.timeIntervalSince1970,
            "start": ["x": value.startLocation.x, "y": value.startLocation.y],
            "location": ["x": value.location.x, "y": value.location.y],
            "translation": ["x": value.translation.width, "y": value.translation.height]])
    }
}

struct PanelResizeProbe: NSViewRepresentable {
    let part: String
    let trace: PanelResizeTrace
    private static let live = NSHashTable<Probe>.weakObjects()
    func makeNSView(context: Context) -> Probe { let view = Probe(); Self.live.add(view); updateNSView(view, context: context); return view }
    func updateNSView(_ view: Probe, context: Context) { view.part = part; view.trace = trace }
    static func parts(window: NSWindow) -> [Probe] { live.allObjects.filter { $0.window === window && NativeVisibility.screenClip($0) != nil } }
    final class Probe: NSView {
        var part = ""
        var trace: PanelResizeTrace?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        var screenBounds: NSRect { window.map { $0.convertToScreen(convert(bounds, to: nil)) } ?? .null }
        func observation() -> [String: Any] {
            ["identity": String(describing: ObjectIdentifier(self)), "part": part,
             "screen_bounds": ElementCapture.box(screenBounds), "local_bounds": ElementCapture.box(bounds)]
        }
    }
}

@MainActor final class PanelResizeCaptureSession {
    private let pane: PanelResizeProbe.Probe
    private let handle: PanelResizeProbe.Probe
    private let trace: PanelResizeTrace
    private let path: URL
    private var receipt: [String: Any] = ["provider": "actual SwiftUI panel gesture and mounted native geometry"]
    private var baseline: Data?
    init(window: NSWindow, path: URL) throws {
        let parts = PanelResizeProbe.parts(window: window)
        guard parts.filter({ $0.part == "pane" }).count == 1, let pane = parts.first(where: { $0.part == "pane" }),
              parts.filter({ $0.part == "handle" }).count == 1, let handle = parts.first(where: { $0.part == "handle" }),
              let trace = handle.trace, pane.trace === trace else { throw RelicError.message("Panel resize requires the same mounted pane and real handle") }
        self.pane = pane; self.handle = handle; self.trace = trace; self.path = path
    }
    private func state() -> [String: Any] {
        let pointer = NSEvent.mouseLocation
        return ["pane": pane.observation(), "handle": handle.observation(), "hovered": trace.hovered,
            "dragging": trace.dragging, "received_gestures": trace.events,
            "pointer_screen": ["x": pointer.x, "y": pointer.y]]
    }
    func perform(window: NSWindow, drag: Bool) async throws {
        defer { save() }
        let before = pane.screenBounds, target = handle.screenBounds
        guard !before.isEmpty, !target.isEmpty, target.width <= 5.01 else { throw RelicError.message("Panel has no actual 5px resize handle") }
        receipt["before"] = state()
        let start = NSPoint(x: target.midX, y: target.midY)
        try VisualCapture.movePointer(to: start)
        try await Task.sleep(for: .milliseconds(150))
        guard trace.hovered else { throw RelicError.message("Actual panel handle did not receive hover") }
        var requested: [[String: Any]] = []
        func send(_ type: NSEvent.EventType, _ screen: NSPoint) throws {
            try VisualCapture.movePointer(to: screen)
            guard let event = NSEvent.mouseEvent(with: type, location: window.convertPoint(fromScreen: screen), modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil,
                eventNumber: 0, clickCount: 1, pressure: type == .leftMouseUp ? 0 : 1) else { throw RelicError.message("Cannot queue actual panel drag input") }
            requested.append(["type": type.rawValue, "screen_point": ["x": screen.x, "y": screen.y]])
            NSApp.postEvent(event, atStart: false)
        }
        if drag {
            var released = false
            defer { if !released { try? send(.leftMouseUp, NSEvent.mouseLocation) }; receipt["requested_events"] = requested }
            try send(.leftMouseDown, start)
            try await Task.sleep(for: .milliseconds(40))
            for step in 1...8 {
                try send(.leftMouseDragged, NSPoint(x: start.x - CGFloat(step) * 8, y: start.y))
                try await Task.sleep(for: .milliseconds(40))
            }
            try send(.leftMouseUp, NSPoint(x: start.x - 64, y: start.y)); released = true
            try await Task.sleep(for: .milliseconds(250))
        }
        let after = pane.screenBounds, delta = drag ? CGFloat(64) : 0
        receipt["after"] = state()
        receipt["measured_delta"] = ["x": after.minX - before.minX, "y": after.minY - before.minY,
            "width": after.width - before.width, "height": after.height - before.height]
        guard abs(after.width - before.width - delta) < 0.01, abs(after.minX - before.minX + delta) < 0.01,
              abs(after.minY - before.minY) < 0.01, abs(after.height - before.height) < 0.01,
              trace.hovered, !trace.dragging, handle.screenBounds.contains(NSEvent.mouseLocation),
              !drag || (trace.events.last?["phase"] as? String == "ended" && trace.events.contains(where: { $0["phase"] as? String == "changed" })) else {
            throw RelicError.message("Actual panel gesture did not retain its expected width, position, hover and released state")
        }
        try observe("after-action")
    }
    func observe(_ phase: String) throws {
        defer { save() }
        let current = state(), encoded = try JSONSerialization.data(withJSONObject: current, options: [.sortedKeys])
        var phases = receipt["observations"] as? [[String: Any]] ?? []
        phases.append(["phase": phase, "state": current]); receipt["observations"] = phases
        if let baseline, baseline != encoded { throw RelicError.message("Actual panel resize state changed at " + phase) }
        baseline = encoded
    }
    func annotateElements(_ path: URL) throws {
        var document = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
        var evidence = document["capture_evidence"] as? [String: Any] ?? [:]
        evidence["panel_resize_action"] = receipt; document["capture_evidence"] = evidence
        try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys, .prettyPrinted]).write(to: path)
    }
    private func save() { if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys, .prettyPrinted]) { try? data.write(to: path) } }
}
