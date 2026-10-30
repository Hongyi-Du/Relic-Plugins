import AppKit
import RelicCore

/// Passive continuity receipts around a real message action. The only clock
/// operation is pause/resume of the production toast's actual expiry task.
@MainActor final class MessageCaptureSession {
    private let model: Model
    private let messageID: String
    private let copying: Bool
    private let path: URL
    private let toast: NativeToastMessage?
    private var baseline: Data?
    private(set) var receipt: [String: Any]
    init(model: Model, messageID: String, copying: Bool, action: [String: Any], path: URL) {
        self.model = model; self.messageID = messageID; self.copying = copying; self.path = path
        self.toast = copying ? model.toasts.last(where: { $0.text == model.t("msg.copied") }) : nil
        receipt = action; receipt["action_status"] = action["status"] ?? NSNull()
        receipt["continuity_status"] = "not-started"; receipt["observations"] = [] as [[String: Any]]
    }
    func begin(window: NSWindow) async throws {
        defer { save() }
        do {
          if copying {
            guard let toast else { throw RelicError.message("The actual Copy action has no success toast to pause") }
            // Model publication precedes SwiftUI mounting. Do not pause and
            // inspect an as-yet absent toast a few milliseconds after Copy.
            // Wait for this exact toast's real view/surface while its original
            // production expiry clock keeps running; never recreate or extend it.
            try await waitForMountedToast(toast, window: window)
            receipt["timer_pause"] = try toast.pauseTimer()
          }
          try observe("after-action", window: window)
        } catch {
            receipt["continuity_status"] = "failed"
            receipt["failure"] = String(describing: error)
            throw error
        }
    }
    private func waitForMountedToast(_ toast: NativeToastMessage, window: NSWindow) async throws {
        var attempts: [[String: Any]] = []
        defer { receipt["toast_mount_observations"] = attempts }
        let deadline = ContinuousClock.now.advanced(by: .seconds(1))
        let owner = "relic-toast/" + toast.id.uuidString
        while true {
            guard model.toasts.contains(where: { $0 === toast }), toast.timerState == "running",
                  let content = window.contentView else {
                throw RelicError.message("The original Copy toast expired, was replaced, or lost its window before mounting")
            }
            let canvas = window.convertToScreen(content.convert(content.bounds, to: nil))
            func labels(_ view: NSView) -> [ReferenceLabelView] { (view as? ReferenceLabelView).map { [$0] } ?? view.subviews.flatMap(labels) }
            let texts = labels(content).filter { $0.productionOwner == owner && NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true }
            let surfaces = SurfacePaintProbe.snapshots(in: canvas).filter {
                $0["owner"] as? String == owner && !ElementCapture.rect($0["nativeVisibleBounds"]).isEmpty && !ElementCapture.rect($0["nativeVisibleBounds"]).isNull
            }
            attempts.append(["host_uptime_seconds": ProcessInfo.processInfo.systemUptime,
                "timer": toast.timerSnapshot(), "text_views": texts.map { ["identity": String(describing: ObjectIdentifier($0)), "text": $0.string] },
                "surfaces": surfaces.map { ["bounds": $0["bounds"]!, "identity": ($0["evidence"] as? [String: Any])?["identity"] as Any? ?? NSNull()] }])
            if texts.count == 1, texts.first?.string == model.t("msg.copied"), surfaces.count == 1 { return }
            guard ContinuousClock.now < deadline else { throw RelicError.message("The actual Copy toast did not mount before the bounded observation deadline") }
            try await Task.sleep(for: .milliseconds(16))
        }
    }
    func observe(_ phase: String, window: NSWindow) throws {
        defer { save() }
        guard let content = window.contentView else { throw RelicError.message("Message capture lost the native window") }
        let canvas = window.convertToScreen(content.convert(content.bounds, to: nil))
        let anchors = MessageInteractionAnchor.live.allObjects.filter {
            $0.messageID == messageID && $0.window === window && NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true
        }
        let copyID = "relic-icon-button/message-copy/" + messageID
        let surfaces = SurfacePaintProbe.snapshots(in: canvas)
        let buttons = surfaces.filter { $0["owner"] as? String == copyID }
        let toastID = toast.map { "relic-toast/" + $0.id.uuidString }
        func labels(_ view: NSView) -> [ReferenceLabelView] { (view as? ReferenceLabelView).map { [$0] } ?? view.subviews.flatMap(labels) }
        let texts = toastID.map { id in labels(content).filter { $0.productionOwner == id && NativeVisibility.screenClip($0).map { !$0.isNull && !$0.isEmpty } == true } } ?? []
        let toastSurfaces = toastID.map { id in surfaces.filter { $0["owner"] as? String == id } } ?? []
        let pointer = NSEvent.mouseLocation
        let clipboard = copying ? NSPasteboard.general.string(forType: .string) : nil
        let expected = model.messages.first(where: { $0["id"].text == messageID })?["body"].text
        let timer = toast?.timerSnapshot()
        let stable: [String: Any] = [
            "message_instances": anchors.map { String(describing: ObjectIdentifier($0)) },
            "message_bounds": anchors.compactMap { NativeVisibility.screenClip($0).map(ElementCapture.box) },
            "copy_surfaces": buttons.map { ["bounds": $0["bounds"]!, "style": $0["style"]!, "identity": ($0["evidence"] as? [String: Any])?["identity"] as Any? ?? NSNull()] },
            "pointer_screen": ["x": pointer.x, "y": pointer.y],
            "clipboard": clipboard as Any? ?? NSNull(),
            "toast_instance": toast.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "toast_text_views": texts.map { ["identity": String(describing: ObjectIdentifier($0)), "text": $0.string, "bounds": NativeVisibility.screenClip($0).map(ElementCapture.box) as Any? ?? NSNull()] },
            "toast_surfaces": toastSurfaces.map { ["bounds": $0["bounds"]!, "style": $0["style"]!] },
            "timer_state": timer?["state"] ?? NSNull(), "remaining_ms": timer?["remaining_ms"] ?? NSNull()
        ]
        var observation = stable
        observation["phase"] = phase; observation["timer"] = timer as Any? ?? NSNull()
        observation["host_uptime_seconds"] = ProcessInfo.processInfo.systemUptime
        var observations = receipt["observations"] as? [[String: Any]] ?? []
        observations.append(observation); receipt["observations"] = observations
        let encoded = try JSONSerialization.data(withJSONObject: stable, options: [.sortedKeys])
        let pointerInTarget = anchors.contains { NativeVisibility.screenClip($0)?.contains(pointer) == true } ||
            buttons.contains { ElementCapture.rect($0["bounds"]).contains(NSPoint(x: pointer.x - canvas.minX, y: canvas.maxY - pointer.y)) }
        guard anchors.count == 1, buttons.count == 1, pointerInTarget else {
            receipt["continuity_status"] = "failed"
            receipt["failure"] = "Message/toolbar/pointer continuity failed at " + phase
            throw RelicError.message(receipt["failure"] as! String)
        }
        if copying {
            guard let toast, model.toasts.contains(where: { $0 === toast }), texts.count == 1, texts.first?.string == model.t("msg.copied"),
                  toastSurfaces.count == 1, clipboard == expected, timer?["state"] as? String == "paused" else {
                receipt["continuity_status"] = "failed"
                receipt["failure"] = "Clipboard/toast/paused timer continuity failed at " + phase
                throw RelicError.message(receipt["failure"] as! String)
            }
        }
        if let baseline, baseline != encoded {
            receipt["continuity_status"] = "failed"
            receipt["failure"] = "Actual message action state changed between capture phases at " + phase
            throw RelicError.message(receipt["failure"] as! String)
        }
        baseline = encoded
        receipt["continuity_status"] = "observed"
        receipt["verified_through"] = phase
    }
    func annotateElements(_ path: URL) throws {
        var document = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
        document["capture_evidence"] = ["message_action": receipt]
        try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys, .prettyPrinted]).write(to: path)
    }
    func finish() {
        if let toast { receipt["timer_cleanup"] = toast.resumeTimer() }
        receipt["cleanup"] = "Resume the same production timer; the isolated Model is disposed by the per-case defer"
        save()
    }
    private func save() {
        if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys, .prettyPrinted]) { try? data.write(to: path) }
    }
}
