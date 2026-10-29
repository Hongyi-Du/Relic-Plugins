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
}
