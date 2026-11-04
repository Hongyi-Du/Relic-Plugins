import XCTest
import AppKit
@testable import Relic

@MainActor final class TypingIndicatorTests: XCTestCase {
    func testRealAppKitClockSeekPreservesDelayedDotsAndActualCurve() {
        let clock = TypingClock(duration: 1.2, animationCurve: .linear)
        clock.currentProgress = 0.4
        XCTAssertEqual(clock.opacity(dot: 0, reducedMotion: false), 1, accuracy: 0.000001)
        clock.currentProgress = 0.8
        XCTAssertEqual(clock.opacity(dot: 0, reducedMotion: false), 0.25, accuracy: 0.000001)
        clock.completedCycles = 3; clock.currentProgress = 0.3
        clock.pauseAtStart()
        XCTAssertFalse(clock.isAnimating)
        XCTAssertEqual(clock.currentProgress, 0)
        XCTAssertEqual(clock.completedCycles, 0)
        XCTAssertEqual((0..<3).map { clock.opacity(dot: $0, reducedMotion: false) }, [0.25,1,1])
        XCTAssertTrue(clock.paused)
        XCTAssertEqual((0..<3).map { clock.opacity(dot: $0, reducedMotion: true) }, [1,1,1])
    }
    func testDelayedClockMatchesBlinkKeyframeAtItsActualTime() {
        let clock = TypingClock(duration: 1.2, animationCurve: .linear)
        clock.currentProgress = NSAnimation.Progress(0.68 / 1.2)
        XCTAssertEqual(clock.opacity(dot: 1, reducedMotion: false), 1, accuracy: 0.000001)
        clock.currentProgress = NSAnimation.Progress(0.2 / 1.2)
        XCTAssertEqual(clock.opacity(dot: 1, reducedMotion: false), 0.25, accuracy: 0.000001)
        XCTAssertEqual(clock.opacity(dot: 2, reducedMotion: false), 1)
    }
}
