import AppKit
import RelicAX

/// Read the frontmost actual accessibility hit and its real parent chain.
/// A rectangle containing the pointer does not establish hover through an
/// overlay. Keep this observation separate from component onHover state until
/// the captured identities establish their exact relationship.
@MainActor enum NativePointerCapture {
    static func capture(window: NSWindow, point: NSPoint = NSEvent.mouseLocation) -> [String: Any] {
        let front = NSApp.orderedWindows.first { $0.isVisible && !$0.ignoresMouseEvents && $0.frame.contains(point) }
        var result: [String: Any] = ["source": "actual accessibilityHitTest and accessibilityParent getters",
            "point": ["x": point.x, "y": point.y], "coordinate_space": "bottom-left screen points",
            "capture_window": identity(window), "front_window": front.map(identity) as Any? ?? NSNull(),
            "status": "unmeasured", "changes_hover_state": false]
        guard let front else {
            result["reason"] = "No frontmost native accessibility hit at the observed pointer"; return result
        }
        // Read the actual content hierarchy for a point inside it. A window's
        // own accessibility hit implementation can stop at the window element.
        // Retain that result too, rather than treating it as a deepest control.
        result["window_hit"] = (RelicAXHitTest(front, point) as AnyObject?).map(identity) as Any? ?? NSNull()
        var receiver: AnyObject = front
        if let content = front.contentView,
           front.convertToScreen(content.convert(content.bounds, to: nil)).contains(point) { receiver = content }
        result["hit_test_receiver"] = identity(receiver)
        guard let hit = RelicAXHitTest(receiver, point) as AnyObject? else {
            result["reason"] = "The actual content accessibility hit returned no element"; return result
        }
        var chain: [[String: Any]] = [], seen = Set<ObjectIdentifier>(), next: AnyObject? = hit
        var reachedWindow = false, cycle = false
        while let current = next {
            guard seen.insert(ObjectIdentifier(current)).inserted else { cycle = true; break }
            let values = RelicAXRead(current)
            let parent = RelicAXParent(current) as AnyObject?
            chain.append(["identity": identity(current), "class": String(describing: type(of: current)),
                "role": values["role"] ?? NSNull(), "identifier": values["identifier"] ?? NSNull(),
                "label": values["label"] ?? NSNull(), "parent": parent.map(identity) as Any? ?? NSNull(),
                "cell_control_view": (current as? NSCell)?.controlView.map(identity) as Any? ?? NSNull()])
            if current === front { reachedWindow = true; break }
            next = parent
        }
        result["hit"] = identity(hit); result["chain"] = chain
        result["reached_front_window"] = reachedWindow; result["cycle"] = cycle
        result["status"] = reachedWindow && !cycle ? "measured-hit-chain" : "incomplete-hit-chain"
        return result
    }
    private static func identity(_ value: AnyObject) -> String { String(describing: ObjectIdentifier(value)) }
}
