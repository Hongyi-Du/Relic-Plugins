import XCTest
import AppKit
@testable import Relic

@MainActor final class InitialEditorFocusTests: XCTestCase {
    func testInitialReplyFocusRunsAfterMountAndDoesNotStealLaterFocus() async {
        _ = NSApplication.shared
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 120))
        let window = NSWindow(contentRect: root.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = root; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let first = ComposerTextView.makeObserved(frame: NSRect(x: 0, y: 0, width: 200, height: 40))
        let second = ComposerTextView.makeObserved(frame: NSRect(x: 0, y: 50, width: 200, height: 40))
        first.isEditable = true; second.isEditable = true
        first.needsInitialFocus = true
        root.addSubview(first); root.addSubview(second)
        await withCheckedContinuation { continuation in DispatchQueue.main.async { continuation.resume() } }
        XCTAssertTrue(window.firstResponder === first)
        XCTAssertFalse(first.needsInitialFocus)
        XCTAssertTrue(window.makeFirstResponder(second))
        first.removeFromSuperview(); root.addSubview(first)
        await withCheckedContinuation { continuation in DispatchQueue.main.async { continuation.resume() } }
        XCTAssertTrue(window.firstResponder === second, "Reattachment must not overwrite a person's later focus choice")
    }
}
