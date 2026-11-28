import AppKit

/// Passive CI history of the real clip/document geometry. It records setup and
/// subsequent native notifications without setting an offset or laying out views.
@MainActor final class ScrollGeometryTrace: NSObject {
    private static var traces: [ObjectIdentifier: ScrollGeometryTrace] = [:]
    private weak var scroll: NSScrollView?
    private var observations: [[String: Any]] = []
    private var omitted = 0

    static func reset() { traces.removeAll() }
    static func observe(_ scroll: NSScrollView, phase: String, once: Bool = false) {
        let key = ObjectIdentifier(scroll)
        // ObjectIdentifier addresses can be reused after a scene releases a view.
        let existing = traces[key].flatMap { $0.scroll === scroll ? $0 : nil }
        if once, existing != nil { return }
        let trace = existing ?? ScrollGeometryTrace(scroll)
        traces[key] = trace
        trace.append(phase)
    }
    static func receipt() -> [String: Any] {
        ["provider": "passive NSClipView bounds/frame notifications and scroller setup",
         "scroll_views": traces.values.map { $0.receipt }]
    }
    init(_ scroll: NSScrollView) {
        self.scroll = scroll
        super.init()
        let clip = scroll.contentView
        clip.postsBoundsChangedNotifications = true
        clip.postsFrameChangedNotifications = true
        NotificationCenter.default.addObserver(self, selector: #selector(changed(_:)), name: NSView.boundsDidChangeNotification, object: clip)
        NotificationCenter.default.addObserver(self, selector: #selector(changed(_:)), name: NSView.frameDidChangeNotification, object: clip)
        append("observer-attached")
    }
    deinit { NotificationCenter.default.removeObserver(self) }
    @objc private func changed(_ notification: Notification) { append(notification.name.rawValue) }
    private var receipt: [String: Any] {
        ["scroll_identity": scroll.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
         "alive": scroll != nil, "observations": observations, "omitted_observations": omitted]
    }
    private func append(_ phase: String) {
        guard let scroll else { return }
        guard observations.count < 4096 else { omitted += 1; return }
        func insets(_ value: NSEdgeInsets) -> [Double] { [value.top, value.right, value.bottom, value.left].map(Double.init) }
        let clip = scroll.contentView
        var row: [String: Any] = ["phase": phase, "uptime": ProcessInfo.processInfo.systemUptime,
            "scroll_frame": ElementCapture.box(scroll.frame), "clip_frame": ElementCapture.box(clip.frame),
            "clip_bounds": ElementCapture.box(clip.bounds), "scroll_content_insets": insets(scroll.contentInsets),
            "clip_content_insets": insets(clip.contentInsets), "scroll_automatic_insets": scroll.automaticallyAdjustsContentInsets,
            "clip_automatic_insets": clip.automaticallyAdjustsContentInsets,
            "document_frame": scroll.documentView.map { ElementCapture.box($0.frame) } as Any? ?? NSNull(),
            "document_flipped": scroll.documentView?.isFlipped as Any? ?? NSNull(),
            "vertical_scroller": scroll.verticalScroller.map { String(describing: type(of: $0)) } as Any? ?? NSNull(),
            "scroller_style": scroll.scrollerStyle.rawValue]
        if let window = scroll.window {
            row["screen_bounds"] = ElementCapture.box(window.convertToScreen(scroll.convert(scroll.bounds, to: nil)))
            row["first_responder_class"] = window.firstResponder.map { String(describing: type(of: $0)) } as Any? ?? NSNull()
        }
        if phase == NSView.boundsDidChangeNotification.rawValue {
            // Diagnose the real caller of an unexpected scroll. This is a passive
            // CI receipt, never a rule for changing the offset or matching boxes.
            row["notification_call_stack"] = Array(Thread.callStackSymbols.prefix(48))
        }
        observations.append(row)
    }
}
