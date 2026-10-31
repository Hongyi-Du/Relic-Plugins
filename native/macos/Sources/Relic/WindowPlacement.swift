import AppKit
import SwiftUI
import RelicCore

/// The product and CI use the same point-based placement controller. Captures
/// supply a unique autosave name, so fixture sizes never become user defaults.
@MainActor final class ApplicationWindowPlacement {
    private weak var window: NSWindow?
    private var observers: [NSObjectProtocol] = []
    let initialFrame: CGRect
    let initialVisibleFrame: CGRect

    init(window: NSWindow, autosaveName: String = "Relic.MainWindow") {
        self.window = window
        let visible = window.screen?.visibleFrame ?? NSScreen.main?.visibleFrame ?? window.frame
        initialVisibleFrame = visible
        // Our explicit autosave policy owns the normal frame. In particular a
        // new installation never inherits a SwiftUI fullscreen restoration.
        window.isRestorable = false
        let hasSavedFrame = window.setFrameUsingName(autosaveName)
        let frame = WindowPlacement.restoredFrame(hasSavedFrame ? window.frame : nil,
            screens: NSScreen.screens.map(\.visibleFrame), preferred: visible)
        let target = NSScreen.screens.first { $0.visibleFrame.contains(CGPoint(x: frame.midX, y: frame.midY)) }?.visibleFrame ?? visible
        window.minSize = WindowPlacement.minimumSize(in: target)
        window.setFrameAutosaveName(autosaveName)
        window.setFrame(frame, display: false)
        initialFrame = window.frame
        observe(NSWindow.didChangeScreenNotification, object: window) { $0.updateMinimum() }
        observe(NSWindow.didChangeBackingPropertiesNotification, object: window) { $0.updateMinimum() }
        observe(NSApplication.didChangeScreenParametersNotification, object: nil) { $0.fitChangedDisplays() }
    }

    private func observe(_ name: NSNotification.Name, object: AnyObject?, action: @escaping (ApplicationWindowPlacement) -> Void) {
        observers.append(NotificationCenter.default.addObserver(forName: name, object: object, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { if let self { action(self) } }
        })
    }

    private func updateMinimum() {
        guard let window, let screen = window.screen ?? NSScreen.main else { return }
        window.minSize = WindowPlacement.minimumSize(in: screen.visibleFrame)
        // Moving between Retina/non-Retina displays changes backing pixels,
        // not the user's point size or position. Do not setFrame here.
    }

    func fitChangedDisplays() {
        guard let window, !window.styleMask.contains(.fullScreen), let screen = window.screen ?? NSScreen.main else { return }
        updateMinimum()
        let frame = WindowPlacement.restoredFrame(window.frame, screens: NSScreen.screens.map(\.visibleFrame), preferred: screen.visibleFrame)
        if frame != window.frame { window.setFrame(frame, display: true) }
    }

    deinit { for observer in observers { NotificationCenter.default.removeObserver(observer) } }
}

struct WindowPlacementMount: NSViewRepresentable {
    let onInitialFrame: (CGSize) -> Void
    func makeNSView(context: Context) -> Mount { Mount(onInitialFrame: onInitialFrame) }
    func updateNSView(_ view: Mount, context: Context) { view.attach() }
    final class Mount: NSView {
        private var placement: ApplicationWindowPlacement?
        private weak var attachedWindow: NSWindow?
        private let onInitialFrame: (CGSize) -> Void
        init(onInitialFrame: @escaping (CGSize) -> Void) { self.onInitialFrame = onInitialFrame; super.init(frame: .zero) }
        required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
        override func isAccessibilityElement() -> Bool { false }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); attach() }
        func attach() {
            guard !VisualCapture.enabled, !TitlebarCapture.enabled, let window, attachedWindow !== window else { return }
            attachedWindow = window
            WindowChrome.apply(to: window)
            placement = ApplicationWindowPlacement(window: window)
            let size = window.frame.size
            DispatchQueue.main.async { [weak self] in self?.onInitialFrame(size) }
        }
    }
}

extension Model {
    func prepareInitialWindow(size: CGSize) {
        windowSize = size
        // Match app.js startup: a narrow window opens the inspector only when
        // requested, while preserving the user's wide-window pane preference.
        if InspectorGeometry.overlaysConversation(window: size.width) { panelOpen = false }
    }
}
