import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ConversationKeyboardTests: XCTestCase {
    private final class Document: NSView {
        var documentCoordinatesFlipped = true
        override var isFlipped: Bool { documentCoordinatesFlipped }
    }

    func testDisclosureRestoresTheRealReadingOffsetAfterNativeBottomAnchoring() async {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
        let document = Document(frame: NSRect(x: 0, y: 0, width: 200, height: 600))
        scroll.documentView = document; scroll.tile()
        let keyboard = ConversationKeyboard(); keyboard.scroll = scroll
        scroll.contentView.scroll(to: NSPoint(x: 0, y: 480))
        keyboard.preserveDisclosurePosition()
        document.setFrameSize(NSSize(width: 200, height: 697))
        scroll.contentView.scroll(to: NSPoint(x: 0, y: 577))
        keyboard.finishDisclosureLayout()
        await withCheckedContinuation { continuation in DispatchQueue.main.async { continuation.resume() } }
        XCTAssertEqual(scroll.contentView.bounds.origin.y, 480, accuracy: 0.01)

        keyboard.preserveDisclosurePosition()
        document.setFrameSize(NSSize(width: 200, height: 720))
        keyboard.finishDisclosureLayout()
        _ = keyboard.handle(.home, modifiers: [])
        await withCheckedContinuation { continuation in DispatchQueue.main.async { continuation.resume() } }
        XCTAssertEqual(scroll.contentView.bounds.origin.y, 0, accuracy: 0.01, "A later explicit navigation must cancel the queued restoration")
    }

    func testKeyboardScrollUsesTheMountedClipAndPreservesOtherRespondersKeys() {
        for flipped in [true, false] {
            let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
            scroll.borderType = .noBorder; scroll.verticalLineScroll = 20; scroll.verticalPageScroll = 10
            let document = Document(frame: NSRect(x: 0, y: 0, width: 200, height: 600)); document.documentCoordinatesFlipped = flipped
            scroll.documentView = document; scroll.tile()
            let keyboard = ConversationKeyboard(); keyboard.scroll = scroll
            _ = keyboard.handle(.home, modifiers: [])
            let start = scroll.contentView.bounds.origin.y
            _ = keyboard.handle(.pageDown, modifiers: [])
            XCTAssertEqual(abs(scroll.contentView.bounds.origin.y - start), 110, accuracy: 0.01)
            _ = keyboard.handle(.space, modifiers: [.shift])
            XCTAssertEqual(scroll.contentView.bounds.origin.y, start, accuracy: 0.01)
            _ = keyboard.handle(.downArrow, modifiers: [])
            XCTAssertEqual(abs(scroll.contentView.bounds.origin.y - start), 20, accuracy: 0.01)
            let position = scroll.contentView.bounds.origin
            if case .ignored = keyboard.handle("a", modifiers: []) {} else { XCTFail("Typing belongs to an editing responder") }
            if case .ignored = keyboard.handle(.downArrow, modifiers: [.command]) {} else { XCTFail("Command shortcuts must remain in the responder chain") }
            XCTAssertEqual(scroll.contentView.bounds.origin, position)
            keyboard.enabled = false
            if case .ignored = keyboard.handle(.pageDown, modifiers: []) {} else { XCTFail("Disabled viewport must not consume scrolling keys") }
            XCTAssertEqual(scroll.contentView.bounds.origin, position)
            keyboard.enabled = true
            _ = keyboard.handle(.end, modifiers: [])
            XCTAssertEqual(abs(scroll.contentView.bounds.origin.y - start), 480, accuracy: 0.01)
            _ = keyboard.handle(.pageDown, modifiers: [])
            XCTAssertEqual(abs(scroll.contentView.bounds.origin.y - start), 480, accuracy: 0.01)
        }
    }

    func testMountBindsItsOwnDocumentAndDetachesWithoutChangingScrollPosition() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 200, height: 120), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
        let document = Document(frame: NSRect(x: 0, y: 0, width: 200, height: 600))
        scroll.documentView = document; window.contentView = scroll
        defer { window.contentView = nil; window.close() }
        let keyboard = ConversationKeyboard()
        // Keep the actual controller alive through its production mount.
        let actual = ConversationKeyboardMount.Mount(keyboard: keyboard)
        document.addSubview(actual); actual.resolveScroll()
        XCTAssertTrue(keyboard.scroll === scroll)
        XCTAssertEqual(scroll.accessibilityIdentifier(), ConversationKeyboard.identifier)
        actual.update(enabled: false, focused: false)
        XCTAssertFalse(keyboard.enabled); XCTAssertFalse(scroll.isAccessibilityEnabled())
        actual.update(enabled: true, focused: true)
        XCTAssertTrue(keyboard.enabled); XCTAssertTrue(scroll.isAccessibilityEnabled())
        XCTAssertEqual(actual.observation()["focused"] as? Bool, true)
        XCTAssertEqual(actual.observation()["controller_bound"] as? Bool, true)
        let position = scroll.contentView.bounds.origin
        actual.removeFromSuperview()
        XCTAssertNil(keyboard.scroll)
        XCTAssertEqual(scroll.contentView.bounds.origin, position)
        XCTAssertFalse(actual.isAccessibilityElement())
    }
}
