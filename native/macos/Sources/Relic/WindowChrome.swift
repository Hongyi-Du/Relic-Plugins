import AppKit
import SwiftUI

/// One application row, with the real AppKit traffic lights over its leading
/// reserved space. No extra title/toolbar strip is inserted above the content.
@MainActor enum WindowChrome {
    static let rowHeight: CGFloat = 40
    static let controlsWidth: CGFloat = 78
    static func apply(to window: NSWindow) {
        // NSHostingView updates this mount for every model publication. Setting
        // the style mask again rebuilds AppKit's frame/content layout even when
        // the requested style is unchanged.
        if !window.styleMask.contains(.fullSizeContentView) { window.styleMask.insert(.fullSizeContentView) }
        if window.titleVisibility != .hidden { window.titleVisibility = .hidden }
        if !window.titlebarAppearsTransparent { window.titlebarAppearsTransparent = true }
        if window.titlebarSeparatorStyle != .none { window.titlebarSeparatorStyle = .none }
        if window.toolbar != nil { window.toolbar = nil }
        if window.isMovableByWindowBackground { window.isMovableByWindowBackground = false }
        positionButtons(in: window)
    }
    static func positionButtons(in window: NSWindow) {
        guard !window.styleMask.contains(.fullScreen) else { return }
        for (index, type) in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton].enumerated() {
            guard let button = window.standardWindowButton(type), let parent = button.superview else { continue }
            let screenY = window.frame.maxY - rowHeight / 2
            let center = parent.convert(window.convertPoint(fromScreen: NSPoint(x: window.frame.minX, y: screenY)), from: nil)
            let origin = NSPoint(x: 12 + CGFloat(index) * 20, y: center.y - button.frame.height / 2)
            if button.frame.origin != origin { button.setFrameOrigin(origin) }
        }
    }
}

struct WindowChromeMount: NSViewRepresentable {
    func makeNSView(context: Context) -> Mount { Mount() }
    func updateNSView(_ view: Mount, context: Context) { view.apply() }
    final class Mount: NSView {
        private var resizeObserver: NSObjectProtocol?
        private weak var observedWindow: NSWindow?
        override func isAccessibilityElement() -> Bool { false }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); apply() }
        override func layout() { super.layout(); if let window { WindowChrome.positionButtons(in: window) } }
        func apply() {
            guard let window else { return }
            WindowChrome.apply(to: window)
            if observedWindow !== window {
                if let resizeObserver { NotificationCenter.default.removeObserver(resizeObserver) }
                observedWindow = window
                resizeObserver = NotificationCenter.default.addObserver(forName: NSWindow.didResizeNotification, object: window, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { if let window = self?.window { WindowChrome.positionButtons(in: window) } }
                }
            }
            DispatchQueue.main.async { [weak self] in
                if let window = self?.window { WindowChrome.positionButtons(in: window) }
            }
        }
        deinit { if let resizeObserver { NotificationCenter.default.removeObserver(resizeObserver) } }
    }
}

/// Only empty toolbar space receives the native window-drag event. Real
/// controls and their entire groups remain outside this view's hit region.
struct WindowDragRegion: NSViewRepresentable {
    let excluded: [CGRect]
    func makeNSView(context: Context) -> DragView { DragView() }
    func updateNSView(_ view: DragView, context: Context) { view.excluded = excluded }
    final class DragView: NSView {
        var excluded: [CGRect] = []
        override var isFlipped: Bool { true }
        override func isAccessibilityElement() -> Bool { false }
        override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? {
            let local = convert(point, from: superview)
            guard bounds.contains(local), local.x >= WindowChrome.controlsWidth,
                  !excluded.contains(where: { $0.contains(local) }) else { return nil }
            return self
        }
        override func mouseDown(with event: NSEvent) {
            if event.clickCount == 2 { window?.performZoom(nil) }
            else { window?.performDrag(with: event) }
        }
    }
}

struct ToolbarControlBounds: PreferenceKey {
    static var defaultValue: [CGRect] = []
    static func reduce(value: inout [CGRect], nextValue: () -> [CGRect]) { value += nextValue() }
}
