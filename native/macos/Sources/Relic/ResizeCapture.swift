import AppKit
import RelicCore

@MainActor final class ResizeCaptureSession {
    private let handle: TextAreaResizeView
    private let editor: ComposerTextView
    private let path: URL
    private var receipt: [String: Any] = ["provider": "real AppKit textarea resize gesture"]
    private var baseline: Data?
    init(window: NSWindow, path: URL) throws {
        func handles(_ root: NSView) -> [TextAreaResizeView] { (root as? TextAreaResizeView).map { [$0] } ?? root.subviews.flatMap(handles) }
        func editors(_ root: NSView) -> [ComposerTextView] { (root as? ComposerTextView).map { [$0] } ?? root.subviews.flatMap(editors) }
        guard let content = window.contentView else { throw RelicError.message("Textarea resize has no native window") }
        let candidates = handles(content).filter { NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true }
        guard candidates.count == 1, let handle = candidates.first,
              let editor = editors(content).first(where: { "relic-composer/" + $0.composerID == handle.owner }) else {
            throw RelicError.message("Expected exactly one real form textarea for the resize scene")
        }
        self.handle = handle; self.editor = editor; self.path = path
    }
    private func state() -> [String: Any] {
        let pointer = NSEvent.mouseLocation
        return ["handle": handle.observation(), "editor_identity": String(describing: ObjectIdentifier(editor)),
            "value": editor.string, "placeholder": editor.placeholder, "selected_range": ["location": editor.selectedRange().location, "length": editor.selectedRange().length],
            "focused": editor.window?.firstResponder === editor,
            "pointer_screen": ["x": pointer.x, "y": pointer.y]]
    }
    func perform(window: NSWindow) async throws {
        defer { save() }
        let before = state(), frame = ElementCapture.rect(handle.observation()["control_screen_bounds"])
        guard !frame.isNull, frame.width > 6, frame.height > 6 else { throw RelicError.message("Native textarea has no actionable bounds") }
        receipt["before"] = before
        let start = NSPoint(x: frame.maxX - 3, y: frame.minY + 3)
        var requested: [[String: Any]] = []
        func send(_ type: NSEvent.EventType, _ screen: NSPoint) throws {
            try VisualCapture.movePointer(to: screen)
            let location = window.convertPoint(fromScreen: screen)
            guard let event = NSEvent.mouseEvent(with: type, location: location, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: type == .leftMouseUp ? 0 : 1) else {
                throw RelicError.message("Cannot queue native textarea drag input")
            }
            requested.append(["type": type.rawValue, "screen_point": ["x": screen.x, "y": screen.y]])
            NSApp.postEvent(event, atStart: false)
        }
        var released = false
        defer { if !released { try? send(.leftMouseUp, NSEvent.mouseLocation) }; receipt["requested_events"] = requested }
        try send(.leftMouseDown, start)
        try await Task.sleep(for: .milliseconds(40))
        for step in 1...8 {
            try send(.leftMouseDragged, NSPoint(x: start.x, y: start.y - CGFloat(step) * 8))
            try await Task.sleep(for: .milliseconds(40))
        }
        try send(.leftMouseUp, NSPoint(x: start.x, y: start.y - 64)); released = true
        try await Task.sleep(for: .milliseconds(250))
        let after = state(), resulting = ElementCapture.rect(handle.observation()["control_screen_bounds"])
        receipt["after"] = after
        receipt["measured_delta"] = ["x": resulting.minX - frame.minX, "y": resulting.minY - frame.minY, "width": resulting.width - frame.width, "height": resulting.height - frame.height]
        guard resulting.height > frame.height, editor.string == before["value"] as? String,
              editor.placeholder == before["placeholder"] as? String,
              handle.events.first?["type"] as? UInt == NSEvent.EventType.leftMouseDown.rawValue,
              handle.events.last?["type"] as? UInt == NSEvent.EventType.leftMouseUp.rawValue,
              handle.events.contains(where: { $0["type"] as? UInt == NSEvent.EventType.leftMouseDragged.rawValue }) else {
            throw RelicError.message("Actual native textarea drag did not resize the same unchanged editor")
        }
        try observe("after-action")
    }
    func observe(_ phase: String) throws {
        defer { save() }
        let current = state(), encoded = try JSONSerialization.data(withJSONObject: current, options: [.sortedKeys])
        var phases = receipt["observations"] as? [[String: Any]] ?? []
        phases.append(["phase": phase, "state": current]); receipt["observations"] = phases
        if let baseline, baseline != encoded { throw RelicError.message("Actual textarea resize state changed at " + phase) }
        baseline = encoded
    }
    func annotateElements(_ path: URL) throws {
        var document = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
        var evidence = document["capture_evidence"] as? [String: Any] ?? [:]
        evidence["textarea_resize_action"] = receipt; document["capture_evidence"] = evidence
        try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys, .prettyPrinted]).write(to: path)
    }
    private func save() { if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys, .prettyPrinted]) { try? data.write(to: path) } }
}
