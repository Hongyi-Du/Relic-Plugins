import AppKit

/// Wait for an actual finite insertion-indicator transition before recording
/// the screenshot baseline. Never hide the caret, remove an animation, pause a
/// layer clock or relax the subsequent geometry/presentation comparison.
@MainActor enum NativeCaretReadiness {
    static func observations(in root: NSView) -> [[String: Any]] {
        var result: [[String: Any]] = []
        func number(_ value: Double) -> Any { value.isFinite ? value : NSNull() }
        func visit(_ view: NSView) {
            if let indicator = view as? NSTextInsertionIndicator, let layer = indicator.layer {
                let animations: [[String: Any]] = (layer.animationKeys() ?? []).map { key in
                    guard let animation = layer.animation(forKey: key) else {
                        return ["key": key, "current_animation_available": false, "finite_transition": false]
                    }
                    let finite = animation.duration.isFinite && animation.duration > 0
                        && animation.repeatCount == 0 && animation.repeatDuration == 0
                        && animation.speed > 0 && animation.isRemovedOnCompletion
                    return ["key": key, "current_animation_available": true,
                        "class": String(describing: type(of: animation)),
                        "duration": number(animation.duration), "begin_time": number(animation.beginTime),
                        "repeat_count": number(Double(animation.repeatCount)), "repeat_duration": number(animation.repeatDuration),
                        "speed": number(Double(animation.speed)), "time_offset": number(animation.timeOffset),
                        "autoreverses": animation.autoreverses, "removed_on_completion": animation.isRemovedOnCompletion,
                        "finite_transition": finite]
                }
                result.append(["view_identity": String(describing: ObjectIdentifier(indicator)),
                    "window_identity": indicator.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                    "layer_identity": String(describing: ObjectIdentifier(layer)),
                    "class": String(describing: type(of: indicator)), "display_mode": indicator.displayMode.rawValue,
                    "bounds": ElementCapture.box(indicator.bounds), "animations": animations])
            }
            for child in view.subviews { visit(child) }
        }
        visit(root)
        return result
    }

    static func settle(in root: NSView, timeout: TimeInterval = 3) async throws -> [String: Any] {
        let started = ProcessInfo.processInfo.systemUptime
        var samples: [[String: Any]] = []
        while true {
            let rows = observations(in: root)
            let pending = rows.flatMap { $0["animations"] as? [[String: Any]] ?? [] }
                .contains { $0["finite_transition"] as? Bool == true }
            let elapsed = ProcessInfo.processInfo.systemUptime - started
            samples.append(["elapsed_seconds": elapsed, "indicators": rows])
            if !pending || elapsed >= timeout {
                return ["source": "actual mounted NSTextInsertionIndicator layer animation getters",
                    "settled": !pending, "timeout_seconds": timeout, "elapsed_seconds": elapsed,
                    "changes_animation_or_visibility": false, "refreshes_watchdog": false, "samples": samples,
                    "scope": "Finite indicator-root transitions only; blinking and final paint retain independent checks"]
            }
            try await Task.sleep(for: .milliseconds(50))
        }
    }
}
