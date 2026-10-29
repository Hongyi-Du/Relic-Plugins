import XCTest
import Foundation
@testable import Relic
import RelicCore

final class ModelTransport: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let result = try Self.handler!(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: result.0, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(result.1.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@MainActor final class ModelTests: XCTestCase {
    func testSavingPreferencesRetainsGetOnlyServerMetadata() async throws {
        let model = try model()
        model.preferences = Node(["version": "0.6", "port": 39321, "data": "/fixture/.relic", "theme": "light"])
        ModelTransport.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/prefs")
            return (200, #"{"theme":"dark","lang":"en-US"}"#)
        }
        try await model.savePreferences(["theme": "dark"])
        XCTAssertEqual(model.preferences["theme"].text, "dark")
        XCTAssertEqual(model.preferences["version"].text, "0.6")
        XCTAssertEqual(model.preferences["port"].integer, 39321)
        XCTAssertEqual(model.preferences["data"].text, "/fixture/.relic")
    }

    func model() throws -> Model {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [ModelTransport.self]
        let defaults = UserDefaults(suiteName: "RelicTests." + UUID().uuidString)!
        return Model(client: try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration)), defaults: defaults)
    }
    func testDraftQuoteAndRecipientsFollowSelectionAndPersist() throws {
        let model = try model(); model.setSelection(ChatSelection("a", "ana")); model.draft = "unsent"; model.quote = "> quote"; model.recipients = ["ana"]
        model.setSelection(ChatSelection("b")); XCTAssertEqual(model.draft, "")
        model.setSelection(ChatSelection("a", "ana")); XCTAssertEqual(model.draft, "unsent"); XCTAssertEqual(model.quote, "> quote"); XCTAssertEqual(model.recipients, ["ana"])
        model.persistDraft(); let reopened = Model(defaults: model.defaults); reopened.setSelection(ChatSelection("a", "ana")); XCTAssertEqual(reopened.draft, "unsent")
    }
    func testFailedSendKeepsDraftAndQuote() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.draft = "unsent"; model.quote = "> quote"
        model.words.load(Node(["lang": "en-US", "strings": ["composer.send_failed": "{error}"]]))
        ModelTransport.handler = { _ in (200, #"{"status":"failed","error":"delivery failed"}"#) }
        do { try await model.send(); XCTFail("Expected error") } catch { XCTAssertEqual(error.localizedDescription, "delivery failed") }
        XCTAssertEqual(model.draft, "unsent"); XCTAssertEqual(model.quote, "> quote"); XCTAssertFalse(model.sending)
    }
    func testQuoteOnlyMainSendIsDispatchedAndSurvivesRejection() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.quote = "> quote only"
        var requests = 0
        ModelTransport.handler = { request in
            requests += 1; XCTAssertEqual(request.url?.path, "/api/org/a/send")
            let body = try JSONSerialization.jsonObject(with: request.httpBody ?? request.httpBodyStream!.readAll()) as! [String: Any]
            XCTAssertEqual(body["body"] as? String, "> quote only\n\n")
            return (503, #"{"error":"temporarily unavailable"}"#)
        }
        do { try await model.send(); XCTFail("Expected error") } catch {}
        XCTAssertEqual(requests, 1); XCTAssertEqual(model.quote, "> quote only"); XCTAssertTrue(model.draft.isEmpty)
    }
    func testSuccessClearsOnlySentDraft() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.draft = "sent"; model.quote = "> quoted"
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/org/a/send": return (200, #"{"id":4,"to":["ana"]}"#)
            case "/api/orgs": return (200, #"[{"id":"a","name":"A"}]"#)
            case "/api/cc": return (200, #"{"items":[],"unread":0}"#)
            case "/api/org/a": return (200, #"{"org":{"id":"a"},"members":[],"decisions":[],"chats":{}}"#)
            default: return (200, #"{"items":[],"more":false}"#)
            }
        }
        try await model.send(); XCTAssertEqual(model.draft, ""); XCTAssertEqual(model.quote, ""); XCTAssertEqual(model.recipients, ["all"])
    }
    func testPlainEventsAreOrganizationScoped() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.plainPending = ["1", "2"]
        await model.receive(Node(["type": "plain", "org": "a", "items": ["1": "explained"], "ids": [1, 2]]))
        XCTAssertEqual(model.plain["1"]?.text, "explained"); XCTAssertTrue(model.plainPending.isEmpty); XCTAssertTrue(model.plainFailed.contains("2"))
        await model.receive(Node(["type": "plain", "org": "other", "items": ["1": "wrong"], "ids": [1]]))
        XCTAssertEqual(model.plain["1"]?.text, "explained"); model.stop()
    }
    func testDigestCompletionKeepsSelectedOrganization() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.digestPending = true
        await model.receive(Node(["type": "digest", "org": "a", "digest": ["text": "summary", "last_id": 3]]))
        XCTAssertFalse(model.digestPending); XCTAssertEqual(model.digest["text"].text, "summary")
        model.setSelection(ChatSelection("b")); XCTAssertTrue(model.digest["text"].text.isEmpty)
    }
    func testLiveEventUpdatesExistingToolInsteadOfDuplicating() async throws {
        let model = try model(); model.setSelection(ChatSelection("a", "ana")); model.liveItems = [Node(["seq": 1, "text": "working"])]
        await model.receive(Node(["type": "live", "org": "a", "member": "ana", "item": ["seq": 1, "text": "done"]]))
        XCTAssertEqual(model.liveItems.count, 1); XCTAssertEqual(model.liveItems[0]["text"].text, "done"); model.stop()
    }
    func testInFlightSnapshotDoesNotOverwriteNewSelection() async throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        let snapshotRequested = expectation(description: "A snapshot requested")
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, #"[{"id":"a"},{"id":"b"}]"#)
            case "/api/cc": return (200, #"{"items":[]}"#)
            case "/api/org/a": snapshotRequested.fulfill(); Thread.sleep(forTimeInterval: 0.1); return (200, #"{"org":{"id":"a"},"members":[]}"#)
            case "/api/org/a/chat": return (200, #"{"items":[{"id":1,"body":"A private data"}]}"#)
            default: XCTFail("Request was retargeted while in flight: \(request.url!.path)"); return (200, "{}")
            }
        }
        let refresh = Task { try await model.refresh() }
        await fulfillment(of: [snapshotRequested], timeout: 2)
        model.setSelection(ChatSelection("b"))
        try await refresh.value; model.stop()
        XCTAssertEqual(model.organization, "b"); XCTAssertTrue(model.snapshot["org"]["id"].text.isEmpty); XCTAssertTrue(model.messages.isEmpty)
    }
    func testUnreadUsesLocalSeenAndExcludesHumanMessages() throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        model.snapshot = Node(["chats": ["member:ana": ["ids": [[1, "ana"], [2, "human"], [3, "ana"]]]]])
        XCTAssertEqual(model.unread("ana"), 2)
        model.defaults.set(1, forKey: "seen.a/member:ana"); XCTAssertEqual(model.unread("ana"), 1)
        model.defaults.set(3, forKey: "seen.a/member:ana"); XCTAssertEqual(model.unread("ana"), 0)
    }
    func testPlainVisibleMessagesBatchAndCancelOnNavigation() async throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        let sent = expectation(description: "visible messages share one request")
        ModelTransport.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/org/b/plain")
            let body = try JSONSerialization.jsonObject(with: request.httpBody ?? request.httpBodyStream!.readAll()) as! [String: Any]
            XCTAssertEqual(body["ids"] as? [Int], [3, 4]); sent.fulfill()
            return (200, #"{"items":{"3":"three","4":"four"}}"#)
        }
        model.enqueuePlain("1"); model.enqueuePlain("2"); model.setSelection(ChatSelection("b"))
        model.enqueuePlain("3"); model.enqueuePlain("4"); model.enqueuePlain("3")
        await fulfillment(of: [sent], timeout: 2)
        try await Task.sleep(for: .milliseconds(30)); model.stop()
        XCTAssertEqual(model.plain["3"]?.text, "three"); XCTAssertNil(model.plain["1"])
    }
    func testQuoteKeepsSelectedQuoteButStripsExistingWholeMessageQuote() throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.words.load(Node(["lang": "en-US", "strings": ["sel.quote_line": "{who}: {text}"]]))
        model.setQuote("> old\n\nnew", from: "ana", stripExisting: true); XCTAssertEqual(model.quote, "> ana: new")
        model.setQuote("> old", from: "ana"); XCTAssertEqual(model.quote, "> ana: > old")
        model.setQuote(String(repeating: "字", count: 1300), from: "ana"); XCTAssertTrue(model.quote.hasSuffix("…")); XCTAssertLessThan(model.quote.count, 1250)
    }
    func testQuoteOnlyThreadSendLocksDuplicateEnterAndPreservesReplyTo() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.threadID = "7"; model.quote = "> quote only"
        let requested = expectation(description: "single quoted reply sent")
        ModelTransport.handler = { request in
            if request.url?.path == "/api/org/a/send" {
                let body = try JSONSerialization.jsonObject(with: request.httpBody ?? request.httpBodyStream!.readAll()) as! [String: Any]
                XCTAssertEqual(body["reply_to"] as? Int, 7); XCTAssertEqual(body["body"] as? String, "> quote only\n\n"); XCTAssertNil(body["to"])
                requested.fulfill(); Thread.sleep(forTimeInterval: 0.1); return (200, #"{"id":8}"#)
            }
            XCTAssertEqual(request.url?.path, "/api/org/a/thread"); return (200, #"{"root":{"id":7},"replies":[{"id":8}]}"#)
        }
        let first = Task { try await model.sendThread() }
        await fulfillment(of: [requested], timeout: 2); try await model.sendThread(); try await first.value
        model.stop(); XCTAssertFalse(model.threadSending); XCTAssertTrue(model.quote.isEmpty)
    }
    func testHistoryCursorSkipsOrganizationNotices() async throws {
        let model = try model(); model.setSelection(ChatSelection("a")); model.messages = [Node(["id": "e4", "type": "notice"]), Node(["id": 22, "body": "oldest message"])]
        ModelTransport.handler = { request in
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(query?.first(where: { $0.name == "before" })?.value, "22")
            return (200, #"{"items":[{"id":10,"body":"older"}],"more":false}"#)
        }
        try await model.loadOlder(); XCTAssertEqual(model.messages.first?["id"].integer, 10); XCTAssertFalse(model.moreChat)
    }
}

private extension InputStream {
    func readAll() -> Data { open(); defer { close() }; var result = Data(), buffer = [UInt8](repeating: 0, count: 4096); while hasBytesAvailable { let count = read(&buffer, maxLength: buffer.count); if count <= 0 { break }; result.append(contentsOf: buffer.prefix(count)) }; return result }
}
