import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeCaretReadinessTests: XCTestCase {
    private final class TextOwner: NSView {
        override var acceptsFirstResponder: Bool { true }
    }
    func testReadinessWaitsForActualFiniteAnimationWithoutRemovingOrHidingAnything() async throws {
        _ = NSApplication.shared
        let root = TextOwner(frame: NSRect(x: 0, y: 0, width: 160, height: 70))
        let indicator = NSTextInsertionIndicator(frame: NSRect(x: 20, y: 20, width: 2, height: 18))
        indicator.wantsLayer = true; root.addSubview(indicator)
        let window = NSWindow(contentRect: root.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = root; window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        XCTAssertTrue(window.makeFirstResponder(root))
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        root.layoutSubtreeIfNeeded(); root.displayIfNeeded(); CATransaction.flush()
        // A custom text owner manages its real first-responder state, as an
        // NSTextView does. The .visible mode disables AppKit's cursor
        // animations, so use the normal active text-owner mode for this test.
        indicator.displayMode = .automatic
        let layer = try XCTUnwrap(indicator.layer)
        let transition = CABasicAnimation(keyPath: "opacity")
        transition.fromValue = 1; transition.toValue = 1; transition.duration = 0.15
        transition.isRemovedOnCompletion = true
        layer.add(transition, forKey: "actual-finite-transition"); CATransaction.flush()
        let before = NativeCaretReadiness.observations(in: root)
        XCTAssertTrue((before.first?["animations"] as? [[String: Any]] ?? []).contains {
            $0["key"] as? String == "actual-finite-transition" && $0["finite_transition"] as? Bool == true
        })
        let frame = indicator.frame, hidden = indicator.isHidden, mode = indicator.displayMode
        let receipt = try await NativeCaretReadiness.settle(in: root)
        XCTAssertEqual(receipt["settled"] as? Bool, true, String(describing: receipt))
        XCTAssertGreaterThan((receipt["samples"] as? [[String: Any]])?.count ?? 0, 1)
        XCTAssertEqual(indicator.frame, frame); XCTAssertEqual(indicator.isHidden, hidden)
        XCTAssertEqual(indicator.displayMode, mode)
        let completed = CABasicAnimation(keyPath: "opacity")
        completed.fromValue = 1; completed.toValue = 1; completed.duration = 0.01
        completed.beginTime = layer.convertTime(CACurrentMediaTime(), from: nil) - 1
        completed.isRemovedOnCompletion = false; completed.fillMode = .forwards
        layer.add(completed, forKey: "completed-retained-transition"); CATransaction.flush()
        let ended = try await NativeCaretReadiness.settle(in: root)
        XCTAssertEqual(ended["settled"] as? Bool, true, String(describing: ended))
        XCTAssertGreaterThanOrEqual(ended["elapsed_seconds"] as? Double ?? 0, 0.05)
        XCTAssertNotNil(layer.animation(forKey: "completed-retained-transition"))
        XCTAssertNil(layer.animation(forKey: "actual-finite-transition"))

        let long = CABasicAnimation(keyPath: "opacity")
        long.fromValue = 1; long.toValue = 1; long.duration = 10; long.isRemovedOnCompletion = false
        long.beginTime = layer.convertTime(CACurrentMediaTime(), from: nil)
        layer.add(long, forKey: "retained-transition"); CATransaction.flush()
        let timedOut = try await NativeCaretReadiness.settle(in: root, timeout: 0.05)
        XCTAssertEqual(timedOut["settled"] as? Bool, false)
        XCTAssertTrue((NativeCaretReadiness.observations(in: root).first?["animations"] as? [[String: Any]] ?? []).contains {
            $0["key"] as? String == "retained-transition" && $0["finite_transition"] as? Bool == true
        }, "Completion retention must not disguise an actual finite transition")
        XCTAssertNotNil(layer.animation(forKey: "retained-transition"), "Readiness cannot remove an animation to manufacture stability")
        XCTAssertEqual(indicator.frame, frame); XCTAssertEqual(indicator.isHidden, hidden)
        XCTAssertEqual(indicator.displayMode, mode)
    }
}
