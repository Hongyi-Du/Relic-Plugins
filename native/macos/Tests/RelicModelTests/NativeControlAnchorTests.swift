import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeControlAnchorTests: XCTestCase {
    private final class FlippedRoot: NSView { override var isFlipped: Bool { true } }

    func testActivationReadsCurrentMountedBoundsAcrossWindowAndControlMoves() throws {
        _ = NSApplication.shared
        for flipped in [false, true] {
            let root: NSView = flipped ? FlippedRoot() : NSView()
            let window = NSWindow(contentRect: CGRect(x: 80, y: 80, width: 300, height: 200), styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = root
            let probe = NativeControlAnchor.Probe(frame: CGRect(x: 40, y: 120, width: 92, height: 28))
            root.addSubview(probe)
            let anchor = NativeControlAnchor(); anchor.view = probe
            XCTAssertEqual(try XCTUnwrap(anchor.contentBounds), CGRect(x: 40, y: flipped ? 120 : 52, width: 92, height: 28))
            let screen = try XCTUnwrap(anchor.screenBounds)
            window.setFrameOrigin(CGPoint(x: 180, y: 180))
            XCTAssertEqual(try XCTUnwrap(anchor.screenBounds), screen.offsetBy(dx: 100, dy: 100))
            probe.setFrameOrigin(CGPoint(x: 70, y: 90))
            XCTAssertEqual(try XCTUnwrap(anchor.contentBounds), CGRect(x: 70, y: flipped ? 90 : 82, width: 92, height: 28))
            XCTAssertNil(probe.hitTest(CGPoint(x: 4, y: 4)))
            XCTAssertFalse(probe.isAccessibilityElement())
            probe.removeFromSuperview()
            XCTAssertNil(anchor.contentBounds)
            XCTAssertNil(anchor.screenBounds)
        }
    }

    func testRecipientPopupStaysAboveMeasuredButtonAndCapsItsRightAnchor() {
        let button = CGRect(x: 311, y: 845, width: 95, height: 28)
        XCTAssertEqual(RecipientMenuGeometry.origin(anchor: button, windowWidth: 1440, height: 223), CGPoint(x: 311, y: 616))
        XCTAssertEqual(RecipientMenuGeometry.origin(anchor: button.offsetBy(dx: 600, dy: -200), windowWidth: 1024, height: 223), CGPoint(x: 764, y: 416))
    }
}
