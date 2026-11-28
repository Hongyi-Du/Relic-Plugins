import AppKit
import SwiftUI

@MainActor enum PerformancePointer {
    static var bounds: [String: CGRect] = [:]
    static var clicks: [String: Int] = [:]
    struct HandledClick {
        let count: Int
        let uptime: Double
        let unixMilliseconds: Double
    }
    static var handled: [String: HandledClick] = [:]
    private static let mounts = NSMapTable<NSString, PerformancePointerMount.Probe>.strongToWeakObjects()
    static func organization(_ id: String) -> String { "org:" + id }
    static func chat(_ org: String, _ member: String) -> String { "chat:" + org + ":" + (member.isEmpty ? "group" : member) }
    static func register(_ probe: PerformancePointerMount.Probe) { mounts.setObject(probe, forKey: probe.identity as NSString) }
    static func unregister(_ probe: PerformancePointerMount.Probe) {
        if mounts.object(forKey: probe.identity as NSString) === probe {
            mounts.removeObject(forKey: probe.identity as NSString); bounds.removeValue(forKey: probe.identity)
        }
    }
    static func mount(_ target: String, in window: NSWindow) -> PerformancePointerMount.Probe? {
        guard let probe = mounts.object(forKey: target as NSString), probe.window === window else { return nil }
        return probe
    }
    // Invoked only by the real production Button action, not by the injector.
    static func observed(_ target: String) {
        guard ResponsivenessCapture.enabled, let event = NSApp.currentEvent,
              event.type == .leftMouseUp || event.type == .leftMouseDown else { return }
        clicks[target, default: 0] += 1
        handled[target] = HandledClick(count: clicks[target, default: 0], uptime: ProcessInfo.processInfo.systemUptime,
            unixMilliseconds: Date().timeIntervalSince1970 * 1000)
    }
}

struct PerformancePointerTarget: ViewModifier {
    let identity: String
    func body(content: Content) -> some View {
        content.background {
            if ResponsivenessCapture.enabled {
                GeometryReader { proxy in
                    let rect = proxy.frame(in: .named("relic-window"))
                    Color.clear.onAppear { PerformancePointer.bounds[identity] = rect }
                        .onChange(of: rect) { PerformancePointer.bounds[identity] = rect }
                }.allowsHitTesting(false).background(PerformancePointerMount(identity: identity))
            }
        }
    }
}

/// A weak reference to the real mounted Button's rectangle. It is used only by
/// CI to scroll and click that control, never to invoke its action directly.
struct PerformancePointerMount: NSViewRepresentable {
    let identity: String
    func makeNSView(context: Context) -> Probe { Probe(identity: identity) }
    func updateNSView(_ view: Probe, context: Context) {
        if view.identity != identity { PerformancePointer.unregister(view); view.identity = identity }
        if view.window != nil { PerformancePointer.register(view) }
    }
    static func dismantleNSView(_ view: Probe, coordinator: ()) { PerformancePointer.unregister(view) }
    final class Probe: NSView {
        var identity: String
        init(identity: String) { self.identity = identity; super.init(frame: .zero) }
        required init?(coder: NSCoder) { nil }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if window != nil { PerformancePointer.register(self) } else { PerformancePointer.unregister(self) }
        }
        var clippedBounds: NSRect {
            guard !isHiddenOrHasHiddenAncestor, window != nil else { return .zero }
            var visible = bounds, ancestor = superview
            while let view = ancestor {
                if view is NSClipView || view.clipsToBounds { visible = visible.intersection(convert(view.bounds, from: view)) }
                ancestor = view.superview
            }
            if let root = window?.contentView { visible = visible.intersection(convert(root.bounds, from: root)) }
            return visible.isNull ? .zero : visible
        }
    }
}
