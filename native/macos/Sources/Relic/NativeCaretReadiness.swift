import AppKit

/// Wait for an actual finite insertion-indicator transition before recording
/// the screenshot baseline. Never hide the caret, remove an animation, pause a
/// layer clock or relax the subsequent geometry/presentation comparison.
@MainActor enum NativeCaretReadiness {
    static func observations(in root: NSView) -> [[String: Any]] {
        var result: [[String: Any]] = []
        func number(_ value: Double) -> Any { value.isFinite ? value : NSNull() }
        func animationValue(_ value: Any?) -> Any {
            guard let value else { return NSNull() }
            if let numeric = value as? NSNumber { return number(numeric.doubleValue) }
            if let string = value as? String { return string }
            return ["class": String(describing: type(of: value)), "description": String(describing: value)]
        }
        func visit(_ view: NSView) {
            if let indicator = view as? NSTextInsertionIndicator, let layer = indicator.layer {
                let localTime = layer.convertTime(CACurrentMediaTime(), from: nil)
                let animations: [[String: Any]] = (layer.animationKeys() ?? []).map { key in
                    guard let animation = layer.animation(forKey: key) else {
                        return ["key": key, "current_animation_available": false, "finite_transition": false]
                    }
                    let finite = animation.duration.isFinite && animation.duration > 0
                        && animation.repeatCount == 0 && animation.repeatDuration == 0
                        && animation.speed > 0
                    // AppKit can retain a finite keyframe animation until its
                    // own completion handler removes it. isRemovedOnCompletion
                    // controls retention, not whether the animation is finite.
                    let timed = animation.beginTime.isFinite && animation.beginTime > 0 && localTime.isFinite
                    let elapsed = timed ? (localTime - animation.beginTime) * Double(animation.speed) + animation.timeOffset : nil
                    let completedRetained = finite
                        && elapsed.map { $0 >= animation.duration * (animation.autoreverses ? 2 : 1) } == true
                    return ["key": key, "current_animation_available": true,
                        "class": String(describing: type(of: animation)),
                        "key_path": (animation as? CAPropertyAnimation)?.keyPath as Any? ?? NSNull(),
                        "values": (animation as? CAKeyframeAnimation)?.values?.map { animationValue($0) } as Any? ?? NSNull(),
                        "key_times": (animation as? CAKeyframeAnimation)?.keyTimes as Any? ?? NSNull(),
                        "calculation_mode": (animation as? CAKeyframeAnimation)?.calculationMode.rawValue as Any? ?? NSNull(),
                        "from_value": animationValue((animation as? CABasicAnimation)?.fromValue),
                        "to_value": animationValue((animation as? CABasicAnimation)?.toValue),
                        "duration": number(animation.duration), "begin_time": number(animation.beginTime),
                        "repeat_count": number(Double(animation.repeatCount)), "repeat_duration": number(animation.repeatDuration),
                        "speed": number(Double(animation.speed)), "time_offset": number(animation.timeOffset),
                        "autoreverses": animation.autoreverses, "removed_on_completion": animation.isRemovedOnCompletion,
                        "finite_transition": finite, "pending_transition": finite && !completedRetained,
                        "completed_retained_transition": completedRetained,
                        "elapsed_local_seconds": elapsed.map(number) ?? NSNull()]
                }
                result.append(["view_identity": String(describing: ObjectIdentifier(indicator)),
                    "window_identity": indicator.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                    "layer_identity": String(describing: ObjectIdentifier(layer)),
                    "class": String(describing: type(of: indicator)), "display_mode": indicator.displayMode.rawValue,
                    "bounds": ElementCapture.box(indicator.bounds), "animations": animations,
                    "layer_local_time": number(localTime), "layer_speed": number(Double(layer.speed)),
                    "layer_begin_time": number(layer.beginTime), "layer_time_offset": number(layer.timeOffset),
                    "model_opacity": number(Double(layer.opacity)),
                    "presentation_opacity": layer.presentation().map { number(Double($0.opacity)) } ?? NSNull()])
            }
            for child in view.subviews { visit(child) }
        }
        visit(root)
        return result
    }

    static func settle(in root: NSView, timeout: TimeInterval = 3) async throws -> [String: Any] {
        let started = ProcessInfo.processInfo.systemUptime
        var samples: [[String: Any]] = []
        var quietSignature: Data?, quietSince: Double?
        while true {
            let rows = observations(in: root)
            let animations = rows.flatMap { $0["animations"] as? [[String: Any]] ?? [] }
            let pending = animations.contains { $0["pending_transition"] as? Bool == true }
            let retained = animations.contains { $0["completed_retained_transition"] as? Bool == true }
            let elapsed = ProcessInfo.processInfo.systemUptime - started
            samples.append(["elapsed_seconds": elapsed, "indicators": rows])
            // A retained animation may have completed without being removed.
            // Observe its actual local clock and a quiet presentation interval;
            // do not wait forever for a removal that CoreAnimation does not own.
            let stableRows = rows.map { row -> [String: Any] in
                var copy = row
                copy.removeValue(forKey: "layer_local_time")
                copy["animations"] = (row["animations"] as? [[String: Any]] ?? []).map { animation in
                    var stable = animation; stable.removeValue(forKey: "elapsed_local_seconds"); return stable
                }
                return copy
            }
            let signature = try JSONSerialization.data(withJSONObject: stableRows, options: [.sortedKeys])
            if pending || signature != quietSignature { quietSince = pending ? nil : elapsed }
            quietSignature = signature
            let settled = !pending && (!retained || quietSince.map { elapsed - $0 >= 0.05 } == true)
            if settled || elapsed >= timeout {
                return ["source": "actual mounted NSTextInsertionIndicator layer animation getters",
                    "settled": settled, "timeout_seconds": timeout, "elapsed_seconds": elapsed,
                    "changes_animation_or_visibility": false, "refreshes_watchdog": false, "samples": samples,
                    "retained_completion_quiet_seconds": 0.05,
                    "scope": "Finite indicator-root transitions and observed retained completion only; blinking and final paint retain independent checks"]
            }
            try await Task.sleep(for: .milliseconds(50))
        }
    }
}
