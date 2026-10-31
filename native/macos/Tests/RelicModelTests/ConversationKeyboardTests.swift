import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class ConversationKeyboardTests: XCTestCase {
    func testRealHomeScrollTriggersTheProductionHistoryPager() async throws {
        _ = NSApplication.shared
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ModelTransport.self]
        let suite = "Relic.ScrollPager." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let model = Model(client: try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration)), defaults: defaults)
        model.organization = "test"
        model.snapshot = Node(["org": ["id": "test", "name": "Test"], "members": []] as [String: Any])
        model.messages = (201...250).map { Node(["id": $0, "type": "message", "from": "human", "text": "Message \($0)", "at": "2026-10-30T12:00:00Z"] as [String: Any]) }
        ModelTransport.handler = { request in
            if request.url?.path == "/api/avatar" { return (404, "{}") }
            XCTAssertEqual(request.url?.path, "/api/org/test/chat")
            XCTAssertTrue(request.url?.query?.contains("limit=200&before=201") == true)
            return (200, #"{"items":[{"id":1,"type":"message","from":"human","text":"Earliest message","at":"2026-10-30T11:00:00Z"}],"more":false}"#)
        }
        let host = NSHostingView(rootView: ConversationStream().environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 400), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func controller(_ root: NSView) -> ConversationKeyboard? {
            if let scroll = root as? NSScrollView, let keyboard = ConversationKeyboardMount.controller(for: scroll) { return keyboard }
            for child in root.subviews { if let keyboard = controller(child) { return keyboard } }
            return nil
        }
        let initialDeadline = ProcessInfo.processInfo.systemUptime + 5
        while model.isPreparingConversation || !RowMountQueue.shared.isIdle || controller(host) == nil {
            guard ProcessInfo.processInfo.systemUptime < initialDeadline else { XCTFail("Conversation did not mount"); return }
            try await Task.sleep(for: .milliseconds(100))
        }
        try await Task.sleep(for: .milliseconds(300))
        model.moreChat = true
        XCTAssertEqual(try XCTUnwrap(controller(host)).handle(.home, modifiers: []), .handled)
        let deadline = ProcessInfo.processInfo.systemUptime + 5
        while model.historyPagesLoaded == 0 && ProcessInfo.processInfo.systemUptime < deadline {
            try await Task.sleep(for: .milliseconds(100))
        }
        XCTAssertEqual(model.historyPagesLoaded, 1, "Home must trigger the production scroll observer without calling loadOlder from the test")
        XCTAssertEqual(model.messages.first?["id"].integer, 1)
        XCTAssertFalse(model.moreChat)
    }
    func testRealConversationHomeAndEndMoveTheLazyNativeViewport() async throws {
        _ = NSApplication.shared
        let suite = "Relic.KeyboardViewport." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let model = Model(defaults: defaults)
        model.organization = "test"
        model.snapshot = Node(["org": ["id": "test", "name": "Test"], "members": []] as [String: Any])
        model.messages = (1...50).map { Node(["id": $0, "type": "message", "from": "human", "to": ["all"], "text": "Message \($0)", "at": "2026-10-30T12:00:00Z"] as [String: Any]) }
        let paragraph = String(repeating: "Long synthetic message. 原生界面必须保留完整内容并保持响应。 ", count: 8)
        let longMarkdown = "# Newest message\n\n" + Array(repeating: paragraph, count: 12).joined(separator: "\n\n")
            + "\n\n```swift\nlet result = 42\nprint(result)\n```\n\nFinal paragraph."
        model.messages[49] = Node(["id": 50, "type": "message", "from": "human", "to": ["all"],
            "text": longMarkdown,
            "at": "2026-10-30T12:00:00Z"] as [String: Any])
        let host = NSHostingView(rootView: ConversationStream().environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 400), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func find(_ root: NSView) -> NSScrollView? {
            if let scroll = root as? NSScrollView, scroll.accessibilityIdentifier() == ConversationKeyboard.identifier { return scroll }
            for child in root.subviews { if let scroll = find(child) { return scroll } }
            return nil
        }
        func settled() async throws {
            let deadline = ProcessInfo.processInfo.systemUptime + 5
            var quiet = 0
            var previousHeight: CGFloat?
            repeat {
                try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
                let height = find(host)?.documentView?.bounds.height ?? 0
                if !model.isPreparingConversation, RowMountQueue.shared.isIdle,
                   height > 1000, previousHeight == height { quiet += 1 }
                else { quiet = 0 }
                previousHeight = height
                if quiet >= 3 { return }
            } while ProcessInfo.processInfo.systemUptime < deadline
            XCTFail("The production lazy conversation did not settle")
        }
        try await settled()
        let scroll = try XCTUnwrap(find(host))
        let keyboard = try XCTUnwrap(ConversationKeyboardMount.controller(for: scroll))
        func visibleText(_ expected: String, in view: NSView) -> Bool {
            if let text = view as? QuoteTextView, text.string == expected {
                let frame = text.convert(text.bounds, to: scroll.contentView)
                if frame.intersects(scroll.contentView.bounds) { return true }
            }
            return view.subviews.contains { visibleText(expected, in: $0) }
        }
        let initialBottom = try XCTUnwrap(scroll.documentView).bounds.maxY - scroll.contentView.bounds.height
        XCTAssertEqual(scroll.contentView.bounds.minY, initialBottom, accuracy: 2, "Initial presentation must show the newest row completely")
        XCTAssertTrue(visibleText("Final paragraph.", in: host), "The latest Markdown paragraph must be inside the actual viewport")
        model.messages.append(Node(["id": 51, "type": "message", "from": "human", "to": ["all"], "text": "Arrived after the view mounted", "at": "2026-10-30T12:01:00Z"] as [String: Any]))
        try await settled()
        XCTAssertTrue(visibleText("Arrived after the view mounted", in: host), "Scoped conversation observation must update actual visible native text")
        XCTAssertEqual(ConversationKeyboardMount.bottomGap(in: window) ?? -1, 0, accuracy: 2)
        XCTAssertEqual(keyboard.handle(.home, modifiers: []), .handled)
        try await settled()
        XCTAssertEqual(scroll.contentView.bounds.minY, 0, accuracy: 2, "Home must reach the real first row, not merely return handled")
        XCTAssertEqual(keyboard.handle(.end, modifiers: []), .handled)
        try await settled()
        let bottom = try XCTUnwrap(scroll.documentView).bounds.maxY - scroll.contentView.bounds.height
        XCTAssertEqual(scroll.contentView.bounds.minY, bottom, accuracy: 2, "End must reach the real last row including its trailing space")
        XCTAssertTrue(visibleText("Arrived after the view mounted", in: host), "End must restore the actual latest text, not an empty offset")
    }
    private final class Document: NSView {
        var documentCoordinatesFlipped = true
        override var isFlipped: Bool { documentCoordinatesFlipped }
    }

    func testEdgeNavigationUsesTheLazyFrameworkOwner() {
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 200, height: 120))
        let document = Document(frame: NSRect(x: 0, y: 0, width: 200, height: 900))
        scroll.documentView = document; scroll.tile()
        let keyboard = ConversationKeyboard(); keyboard.scroll = scroll
        var edges: [Bool] = []
        keyboard.scrollToEdge = { edges.append($0) }
        XCTAssertEqual(keyboard.handle(.end, modifiers: []), .handled)
        XCTAssertEqual(keyboard.handle(.home, modifiers: []), .handled)
        XCTAssertEqual(edges, [false, true])
        // SwiftUI owns both its offset and row visibility. Do not also force
        // a native clip offset that bypasses the lazy row lifecycle.
        XCTAssertEqual(scroll.contentView.bounds.origin.y, 0, accuracy: 1)
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
        XCTAssertEqual(actual.observation()["focus_scope_binding"] as? Bool, true)
        XCTAssertFalse(scroll.isAccessibilityFocused())
        XCTAssertEqual(actual.observation()["focused"] as? Bool, false,
            "A surrounding focus binding must not become the exact scroll element's AX focus")
        XCTAssertEqual(actual.observation()["controller_bound"] as? Bool, true)
        let position = scroll.contentView.bounds.origin
        actual.removeFromSuperview()
        XCTAssertNil(keyboard.scroll)
        XCTAssertEqual(scroll.contentView.bounds.origin, position)
        XCTAssertFalse(actual.isAccessibilityElement())
    }
}
