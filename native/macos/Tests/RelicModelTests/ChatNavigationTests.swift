import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

/// Responses are released by the test, without blocking URLSession's protocol
/// queue. A second click can therefore finish before the first response.
private final class NavigationTransport: URLProtocol {
    typealias Reply = (Int, String)
    static var handler: ((URLRequest, @escaping (Reply) -> Void) -> Void)?
    private let lock = NSLock()
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.handler?(request) { [weak self] response in
            guard let self else { return }
            self.lock.lock(); let deliver = !self.stopped; self.stopped = true; self.lock.unlock()
            guard deliver else { return }
            self.client?.urlProtocol(self, didReceive: HTTPURLResponse(url: self.request.url!, statusCode: response.0,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: Data(response.1.utf8))
            self.client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() { lock.lock(); stopped = true; lock.unlock() }
}

private final class NavigationReplyGate: @unchecked Sendable {
    private let lock = NSLock()
    private var reply: ((NavigationTransport.Reply) -> Void)?
    func hold(_ reply: @escaping (NavigationTransport.Reply) -> Void) { lock.lock(); self.reply = reply; lock.unlock() }
    func release(_ value: NavigationTransport.Reply) {
        lock.lock(); let callback = reply; reply = nil; lock.unlock(); callback?(value)
    }
}

@MainActor final class ChatNavigationTests: XCTestCase {
    func testSlowNavigationRetainsTheCurrentChatUntilPreparedReplacementPublishesOnce() async throws {
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        try await seed(model)
        let priorVersion = model.streamVersion, priorRows = model.streamRows.map(\.id)
        model.draft = "Still writing in A"
        var saved = ChatDraft(); saved.text = "Saved B draft"; model.drafts[ChatSelection("b").key] = saved
        let requested = expectation(description: "B history is waiting on the network"), gate = NavigationReplyGate()
        NavigationTransport.handler = { request, reply in
            if request.url!.path == "/api/org/b/chat" { gate.hold(reply); requested.fulfill() }
            else { reply((200, Self.snapshot("b"))) }
        }
        let loading = Task { try await model.select("b") }
        await fulfillment(of: [requested], timeout: 2)
        XCTAssertTrue(model.isLoadingSelectedChat)
        XCTAssertEqual(model.selection, ChatSelection("a"))
        XCTAssertEqual(model.snapshot["org"]["id"].text, "a")
        XCTAssertEqual(model.streamRows.map(\.id), priorRows)
        XCTAssertEqual(model.streamVersion, priorVersion)
        XCTAssertEqual(model.messages.last?["id"].integer, 1)
        model.draft = "Edited while B was loading"
        gate.release((200, Self.page(id: 42, body: "**Prepared latest B**")))
        try await loading.value
        XCTAssertEqual(model.selection, ChatSelection("b"))
        XCTAssertEqual(model.snapshot["org"]["id"].text, "b")
        XCTAssertEqual(model.messages.map { $0["id"].integer }, [42])
        XCTAssertEqual(model.streamVersion, priorVersion + 1, "No intermediate empty projection may be published")
        XCTAssertEqual(model.streamRows.last?.preparedBody?.source, "**Prepared latest B**")
        XCTAssertEqual(model.drafts[ChatSelection("a").key]?.text, "Edited while B was loading")
        XCTAssertEqual(model.draft, "Saved B draft")
        XCTAssertFalse(model.isPreparingConversation); XCTAssertFalse(model.isLoadingSelectedChat)
    }

    func testLaterClickWinsAndAnOlderResponseCannotReplaceItsPreparedChat() async throws {
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        try await seed(model)
        let requested = expectation(description: "First click is still waiting"), gate = NavigationReplyGate()
        NavigationTransport.handler = { request, reply in
            switch request.url!.path {
            case "/api/org/b/chat": gate.hold(reply); requested.fulfill()
            case "/api/org/b": reply((200, Self.snapshot("b")))
            case "/api/org/c": reply((200, Self.snapshot("c")))
            case "/api/org/c/chat": reply((200, Self.page(id: 63, body: "Winning C body")))
            default: XCTFail("Unexpected request " + request.url!.path); reply((500, "{}"))
            }
        }
        let first = Task { try await model.select("b") }
        await fulfillment(of: [requested], timeout: 2)
        try await model.select("c")
        gate.release((200, Self.page(id: 42, body: "Late losing B body")))
        try await first.value
        XCTAssertEqual(model.selection, ChatSelection("c"))
        XCTAssertEqual(model.snapshot["org"]["id"].text, "c")
        XCTAssertEqual(model.messages.map { $0["id"].integer }, [63])
        XCTAssertEqual(model.streamRows.last?.preparedBody?.source, "Winning C body")
        XCTAssertEqual(model.selectedChatLoadVersion, 1)
        XCTAssertFalse(model.isLoadingSelectedChat)
        // A new projection after navigation must retain its own worker identity
        // even if a canceled earlier projection is returning from its await.
        model.messages.append(Node(["id": 64, "type": "message", "body": "New C event"]))
        try await finishPreparation(model)
        XCTAssertEqual(model.streamRows.last?.item["id"].integer, 64)
        XCTAssertEqual(model.streamRows.last?.preparedBody?.source, "New C event")
    }

    func testFailedNavigationLeavesSelectionHistoryDraftAndNativeDataIntact() async throws {
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        try await seed(model)
        model.draft = "Unsent A"; model.quote = "A quote"; model.recipients = ["analyst"]
        let rows = model.streamRows.map(\.id), version = model.streamVersion, recent = model.recent
        NavigationTransport.handler = { request, reply in
            reply(request.url!.path.hasSuffix("/chat") ? (500, #"{"error":"fixture network failure"}"#) : (200, Self.snapshot("b")))
        }
        do { try await model.select("b"); XCTFail("A real network failure must be returned") }
        catch { XCTAssertTrue(error.localizedDescription.contains("fixture network failure")) }
        XCTAssertEqual(model.selection, ChatSelection("a"))
        XCTAssertEqual(model.snapshot["org"]["id"].text, "a")
        XCTAssertEqual(model.streamRows.map(\.id), rows); XCTAssertEqual(model.streamVersion, version)
        XCTAssertEqual(model.messages.last?["id"].integer, 1)
        XCTAssertEqual(model.recent, recent)
        XCTAssertEqual(model.draft, "Unsent A"); XCTAssertEqual(model.quote, "A quote"); XCTAssertEqual(model.recipients, ["analyst"])
        XCTAssertEqual(model.selectedChatLoadVersion, 0); XCTAssertFalse(model.isLoadingSelectedChat)
    }

    func testRefreshingTheCurrentChatPreservesOlderPagesAndDraft() async throws {
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        try await seed(model)
        model.messages = [Node(["id": 2, "type": "message", "body": "Loaded A page"])]
        model.draft = "Keep this draft"; model.quote = "Keep this quote"; model.recipients = ["analyst"]
        model.moreChat = true
        NavigationTransport.handler = { request, reply in
            if request.url!.query?.contains("before=") == true {
                reply((200, Self.page(id: 1, body: "Old page", more: true)))
            } else if request.url!.path.hasSuffix("/chat") {
                reply((200, Self.page(id: 3, body: "Refreshed latest A")))
            } else { reply((200, Self.snapshot("a"))) }
        }
        try await model.loadOlder(); try await finishPreparation(model)
        XCTAssertEqual(model.historyPagesLoaded, 1)
        try await model.select("a")
        XCTAssertEqual(model.messages.map { $0["id"].integer }, [1, 2, 3])
        XCTAssertEqual(model.historyPagesLoaded, 1); XCTAssertTrue(model.moreChat)
        XCTAssertEqual(model.draft, "Keep this draft"); XCTAssertEqual(model.quote, "Keep this quote"); XCTAssertEqual(model.recipients, ["analyst"])
        XCTAssertEqual(model.streamRows.last?.preparedBody?.source, "Refreshed latest A")
    }

    func testCurrentChatRefreshKeepsALiveEventReceivedDuringItsRequest() async throws {
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        model.setSelection(ChatSelection("a", "analyst"))
        let snap = #"{"org":{"id":"a"},"members":[{"name":"analyst","embedded":true}]}"#
        model.snapshot = Node(try JSONSerialization.jsonObject(with: Data(snap.utf8)))
        model.liveItems = [Node(["id": "live-1", "seq": 1, "text": "Existing live turn"])]
        try await finishPreparation(model)
        let requested = expectation(description: "Live request is pending"), gate = NavigationReplyGate()
        NavigationTransport.handler = { request, reply in
            switch request.url!.path {
            case "/api/org/a": reply((200, snap))
            case "/api/org/a/chat": reply((200, Self.page(id: 15, body: "Private latest")))
            case "/api/org/a/live": gate.hold(reply); requested.fulfill()
            default: XCTFail("Unexpected live request " + request.url!.path); reply((500, "{}"))
            }
        }
        let refresh = Task { try await model.select("a", "analyst") }
        await fulfillment(of: [requested], timeout: 2)
        await model.receive(Node(["type": "live", "org": "a", "member": "analyst",
            "item": ["id": "live-2", "seq": 2, "text": "New live turn"], "status": ["state": "running"]] as [String: Any]))
        gate.release((200, #"{"items":[{"id":"live-1","seq":1,"text":"Existing live turn"}],"status":{"state":"idle"}}"#))
        try await refresh.value
        XCTAssertEqual(model.liveItems.map { $0["seq"].integer }, [1, 2])
        XCTAssertEqual(model.liveStatus["state"].text, "running")
        XCTAssertEqual(model.messages.last?["id"].integer, 15)
        XCTAssertFalse(model.isPreparingConversation)
    }

    func testAtomicNavigationDisplaysTheActualNewNativeBodyAndKeepsTheViewport() async throws {
        _ = NSApplication.shared
        let model = try makeModel(); defer { model.stop(); NavigationTransport.handler = nil }
        try await seed(model)
        NavigationTransport.handler = { request, reply in
            switch request.url!.path {
            case "/api/org/b": reply((200, Self.snapshot("b")))
            case "/api/org/b/chat": reply((200, Self.page(id: 42, body: "Actual visible native B tail")))
            default: reply((404, "{}")) // The fixture has no avatar image.
            }
        }
        let host = NSHostingView(rootView: ChatView().environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 760, height: 600), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let oldScroll = try await visibleBody("Existing A body", in: host)
        try await model.select("b")
        let newScroll = try await visibleBody("Actual visible native B tail", in: host)
        XCTAssertTrue(newScroll === oldScroll, "Preparing a replacement chat must preserve its native viewport")
        XCTAssertEqual(ConversationKeyboardMount.bottomGap(in: window) ?? -1, 0, accuracy: 2)
    }

    private func makeModel() throws -> Model {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [NavigationTransport.self]
        let suite = "Relic.AtomicNavigation." + UUID().uuidString, defaults = UserDefaults(suiteName: suite)!
        addTeardownBlock { defaults.removePersistentDomain(forName: suite) }
        return Model(client: try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration)), defaults: defaults)
    }
    private func seed(_ model: Model) async throws {
        model.setSelection(ChatSelection("a"))
        model.snapshot = Node(["org": ["id": "a", "name": "A"], "members": []] as [String: Any])
        model.messages = [Node(["id": 1, "type": "message", "from": "human", "text": "Existing A body", "at": "2026-10-30T12:00:00Z"])]
        try await finishPreparation(model)
    }
    private func finishPreparation(_ model: Model) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + 5
        while model.isPreparingConversation, ProcessInfo.processInfo.systemUptime < deadline { try await Task.sleep(for: .milliseconds(5)) }
        XCTAssertFalse(model.isPreparingConversation, "Background conversation preparation must finish")
    }
    private func visibleBody(_ text: String, in host: NSView) async throws -> NSScrollView {
        func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }
        let deadline = ProcessInfo.processInfo.systemUptime + 8
        repeat {
            try await Task.sleep(for: .milliseconds(50)); host.layoutSubtreeIfNeeded()
            let all = descendants(host)
            if let scroll = all.compactMap({ $0 as? NSScrollView }).first(where: { $0.accessibilityIdentifier() == ConversationKeyboard.identifier }),
               all.compactMap({ $0 as? QuoteTextView }).contains(where: {
                   !$0.isHiddenOrHasHiddenAncestor && $0.string == text && $0.convert($0.bounds, to: scroll.contentView).intersects(scroll.contentView.bounds)
               }), RowMountQueue.shared.isIdle { return scroll }
        } while ProcessInfo.processInfo.systemUptime < deadline
        throw RelicError.message("Actual native latest body was not visible: " + text)
    }
    nonisolated private static func snapshot(_ org: String) -> String { "{\"org\":{\"id\":\"" + org + "\",\"name\":\"" + org + "\"},\"members\":[]}" }
    nonisolated private static func page(id: Int, body: String, more: Bool = false) -> String {
        let value: [String: Any] = ["items": [["id": id, "type": "message", "from": "human", "text": body, "at": "2026-10-30T12:00:00Z"]], "more": more]
        return String(data: try! JSONSerialization.data(withJSONObject: value), encoding: .utf8)!
    }
}
