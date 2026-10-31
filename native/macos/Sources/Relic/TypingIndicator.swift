import AppKit
import SwiftUI

/// The production indicator is driven by AppKit's real animation clock. Capture
/// can stop and seek that clock; it never assigns a capture-only dot opacity.
struct TypingIndicator: NSViewRepresentable {
    @Environment(\.captureRegion) private var region
    func makeNSView(context: Context) -> TypingIndicatorView { TypingIndicatorView() }
    func updateNSView(_ view: TypingIndicatorView, context: Context) {
        view.region = region; view.color = NSColor(RelicStyle.muted)
        view.reducedMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        view.needsDisplay = true
    }
    static func dismantleNSView(_ view: TypingIndicatorView, coordinator: ()) { view.clock.stop() }
}

final class TypingClock: NSAnimation {
    var tick: (() -> Void)?
    var completedCycles = 0
    var paused = false
    override var currentProgress: NSAnimation.Progress {
        get { super.currentProgress }
        set { super.currentProgress = newValue; tick?() }
    }
    var elapsed: Double { (Double(completedCycles) + Double(currentProgress)) * duration }
    func pauseAtStart() { paused = true; stop(); completedCycles = 0; currentProgress = 0 }
    /// CSS blink's three keyframe intervals, with the default cubic-bezier ease
    /// within each interval. Delay is part of the animation, including the
    /// underlying opacity of 1 before the second/third dot starts.
    func opacity(dot: Int, reducedMotion: Bool) -> Double {
        if reducedMotion { return 1 }
        let local = elapsed - Double(dot) * 0.2
        if local < 0 { return 1 }
        let phase = local.truncatingRemainder(dividingBy: duration) / duration
        if phase < 0.4 { return 0.25 + 0.75 * Self.ease(phase / 0.4) }
        if phase < 0.8 { return 1 - 0.75 * Self.ease((phase - 0.4) / 0.4) }
        return 0.25
    }
    private static func ease(_ x: Double) -> Double {
        if x <= 0 { return 0 }; if x >= 1 { return 1 }
        func cubic(_ t: Double, _ p: Double, _ q: Double) -> Double { 3 * (1-t) * (1-t) * t * p + 3 * (1-t) * t * t * q + t*t*t }
        var low = 0.0, high = 1.0
        for _ in 0..<32 { let middle = (low + high) / 2; if cubic(middle, 0.25, 0.25) < x { low = middle } else { high = middle } }
        return cubic((low + high) / 2, 0.1, 1)
    }
    var evidence: [String: Any] {
        ["provider": "NSAnimation", "duration": duration, "current_progress": Double(currentProgress), "current_value": Double(currentValue), "completed_cycles": completedCycles, "elapsed": elapsed, "is_animating": isAnimating, "paused": paused, "frame_rate": frameRate]
    }
}

final class TypingIndicatorView: NSView, NSAnimationDelegate {
    static let live = NSHashTable<TypingIndicatorView>.weakObjects()
    let identity = UUID().uuidString
    let clock = TypingClock(duration: 1.2, animationCurve: .linear)
    var region = "conversation", color = NSColor.gray
    var reducedMotion = false { didSet { if reducedMotion { clock.stop() } else { startIfVisible() } } }
    private(set) var drawn: [(rect: NSRect, color: NSColor, opacity: Double)] = []
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        Self.live.add(self); clock.animationBlockingMode = .nonblocking; clock.frameRate = 60; clock.delegate = self
        clock.tick = { [weak self] in self?.needsDisplay = true }
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func isAccessibilityElement() -> Bool { false }
    override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); if window == nil { clock.stop() } else { startIfVisible() } }
    private func startIfVisible() {
        if window != nil && !reducedMotion && !clock.paused && !clock.isAnimating { clock.start() }
    }
    func animationDidEnd(_ animation: NSAnimation) {
        clock.completedCycles += 1
        DispatchQueue.main.async { [weak self] in self?.startIfVisible() }
    }
    override func draw(_ dirtyRect: NSRect) {
        drawn = (0..<3).map { index in
            let rect = NSRect(x: CGFloat(2 + index * 10), y: 6, width: 6, height: 6)
            let opacity = clock.opacity(dot: index, reducedMotion: reducedMotion)
            let resolved = color.usingColorSpace(.sRGB) ?? color
            resolved.withAlphaComponent(resolved.alphaComponent * CGFloat(opacity)).setFill()
            NSBezierPath(ovalIn: rect).fill()
            return (rect, resolved, opacity)
        }
    }
    static func pauseVisibleClocks() -> [[String: Any]] {
        live.allObjects.filter { $0.window?.isVisible == true && !$0.isHiddenOrHasHiddenAncestor }.map { view in
            let before = view.clock.evidence
            view.clock.pauseAtStart(); view.needsDisplay = true; view.displayIfNeeded()
            return ["id": view.identity, "before": before, "after": view.clock.evidence, "reduced_motion": view.reducedMotion,
                    "drawn": view.drawn.map { ["bounds": ElementCapture.box($0.rect), "color": ElementCapture.rgba($0.color), "opacity": $0.opacity] }]
        }
    }
    static func snapshots(in content: NSRect) -> [[String: Any]] {
        live.allObjects.flatMap { view -> [[String: Any]] in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor else { return [] }
            let clip = NativeVisibility.screenClip(view).map { $0.isNull ? NSRect.null : ElementCapture.topLeft($0, in: content) } ?? .null
            return view.drawn.enumerated().map { index, paint in
                let rect = ElementCapture.topLeft(window.convertToScreen(view.convert(paint.rect, to: nil)), in: content)
                return ["rectValue": NSValue(rect: rect), "bounds": ElementCapture.box(rect), "nativeVisibleBounds": clip.isNull ? NSNull() : ElementCapture.box(clip), "region": view.region, "kind": "card", "hovered": false,
                        "style": ["backgroundColor": ElementCapture.rgba(paint.color), "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 3,
                                  "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [3,3,3,3],
                                  "opacity": paint.opacity * NativeVisibility.opacity(view), "background_image": "none", "shadow": []],
                        "evidence": ["source": "actual-AppKit-draw", "renderer": "NSBezierPath oval fill", "identity": view.identity + "/" + String(index), "animation": view.clock.evidence, "reduced_motion": view.reducedMotion]]
            }
        }
    }
}
