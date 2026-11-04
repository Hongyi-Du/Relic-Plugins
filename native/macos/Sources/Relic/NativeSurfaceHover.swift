import AppKit

/// Actual production SwiftUI callbacks, retained independently of AX hit tests.
/// No callback means unknown; mounting or intersecting a rectangle is not an
/// enter/exit event. This observer neither changes paint nor handles clicks.
@MainActor final class NativeSurfaceHover {
    private(set) var value: Bool?
    private var count = 0
    private var lastEvent: [String: Any]?
    func received(_ value: Bool) {
        self.value = value; count += 1
        let point = NSEvent.mouseLocation
        lastEvent = ["hovered": value, "uptime": ProcessInfo.processInfo.systemUptime,
            "pointer_screen": ["x": point.x, "y": point.y]]
    }
    func observation() -> [String: Any] {
        ["source": "production RecordedSurface.onHover callback",
         "identity": String(describing: ObjectIdentifier(self)), "callback_count": count,
         "value": value as Any? ?? NSNull(), "last_event": lastEvent as Any? ?? NSNull(),
         "infers_from_geometry_or_ax_hit": false]
    }
}
