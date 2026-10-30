import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ConversationKeyboardTests: XCTestCase {
    private final class Document: NSView {
        var documentCoordinatesFlipped = true
        override var isFlipped: Bool { documentCoordinatesFlipped }
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
        let position = scroll.contentView.bounds.origin
        actual.removeFromSuperview()
        XCTAssertNil(keyboard.scroll)
        XCTAssertEqual(scroll.contentView.bounds.origin, position)
        XCTAssertFalse(actual.isAccessibilityElement())
    }
}
