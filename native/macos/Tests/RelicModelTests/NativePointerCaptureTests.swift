import XCTest
import AppKit
@testable import Relic

@MainActor final class NativePointerCaptureTests: XCTestCase {
    func testActualHitChainUsesTheFrontControlInsteadOfBothOverlappingFrames() throws {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 240, height: 140),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 140))
        let back = NSButton(title: "Back", target: nil, action: nil)
        let front = NSButton(title: "Front", target: nil, action: nil)
        for button in [back, front] {
            button.frame = NSRect(x: 20, y: 20, width: 120, height: 30)
            root.addSubview(button)
        }
        window.contentView = root; window.orderFront(nil); root.layoutSubtreeIfNeeded()
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let point = window.convertPoint(toScreen: NSPoint(x: 60, y: 35))
        func identities(_ receipt: [String: Any]) -> [String] {
            (receipt["chain"] as? [[String: Any]])?.compactMap { $0["identity"] as? String } ?? []
        }
        let covered = NativePointerCapture.capture(window: window, point: point)
        XCTAssertEqual(covered["status"] as? String, "measured-hit-chain")
        XCTAssertTrue(identities(covered).contains(String(describing: ObjectIdentifier(front))))
        XCTAssertFalse(identities(covered).contains(String(describing: ObjectIdentifier(back))))
        front.removeFromSuperview()
        let exposed = NativePointerCapture.capture(window: window, point: point)
        XCTAssertTrue(identities(exposed).contains(String(describing: ObjectIdentifier(back))))
        XCTAssertFalse(identities(exposed).contains(String(describing: ObjectIdentifier(front))))
        XCTAssertEqual(exposed["changes_hover_state"] as? Bool, false)
        let outside = NativePointerCapture.capture(window: window, point: NSPoint(x: -10000, y: -10000))
        XCTAssertEqual(outside["status"] as? String, "unmeasured")
        XCTAssertNil(outside["chain"])
    }
}
