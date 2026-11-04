import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class ThreadConversationTests: XCTestCase {
    func testLargeThreadRetainsAllRepliesButOnlyMountsViewportContent() async throws {
        _ = NSApplication.shared
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ModelTransport.self]
        let suite = "Relic.LargeThread." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let model = Model(client: try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration)), defaults: defaults)
        model.organization = "test"
        let replies: [[String: Any]] = (1...3_000).map {
            ["id": $0 + 1, "type": "message", "from": "human", "text": "Reply \($0)", "at": "2026-10-30T12:00:00Z"]
        }
        let payload: [String: Any] = ["root": ["id": 1, "type": "message", "from": "human", "text": "Thread root"], "replies": replies]
        let response = String(decoding: try JSONSerialization.data(withJSONObject: payload), as: UTF8.self)
        ModelTransport.handler = { request in
            if request.url?.path == "/api/org/test/thread" { return (200, response) }
            return (404, "{}")
        }
        try await model.openThread("1")
        XCTAssertEqual(model.threadRows.count, 3_000)
        XCTAssertEqual(model.threadRows.first?.item["text"].text, "Reply 1")
        XCTAssertEqual(model.threadRows.last?.item["text"].text, "Reply 3000")
        XCTAssertEqual(model.threadRows.prefix(3).map(\.continued), [false, true, true])
        XCTAssertTrue(model.threadRows.allSatisfy { $0.separator == nil })

        let host = NSHostingView(rootView: ThreadView().environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 600), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func texts(_ view: NSView) -> [QuoteTextView] {
            (view as? QuoteTextView).map { [$0] } ?? view.subviews.flatMap(texts)
        }
        func firstReplyIsVisible() -> Bool {
            texts(host).contains { text in
                guard text.string == "Reply 1", let clip = text.enclosingScrollView?.contentView else { return false }
                return text.convert(text.bounds, to: clip).intersects(clip.bounds)
            }
        }
        let deadline = ProcessInfo.processInfo.systemUptime + 10
        var quiet = 0
        while quiet < 3 && ProcessInfo.processInfo.systemUptime < deadline {
            try await Task.sleep(for: .milliseconds(100))
            quiet = firstReplyIsVisible() && RowMountQueue.shared.isIdle ? quiet + 1 : 0
        }
        XCTAssertTrue(firstReplyIsVisible(), "The actual native first reply must be visible")
        XCTAssertLessThan(texts(host).count, 40, "A large thread must not construct all native reply documents")
        XCTAssertEqual(model.threadRows.count, 3_000, "Virtualization must retain all server replies")
        model.closeThread()
        XCTAssertTrue(model.threadRows.isEmpty)
    }
}
