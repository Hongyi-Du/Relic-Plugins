import XCTest
import Foundation
@testable import RelicCore

final class Stub: URLProtocol {
    static var handle: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try Self.handle!(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

final class ContractTests: XCTestCase {
    func client() throws -> Client {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        return try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration))
    }
    func testOnlyTwoLanguages() {
        XCTAssertEqual(Words.normalize("zh-TW"), "zh-CN"); XCTAssertEqual(Words.normalize("zh-Hant"), "zh-CN")
        XCTAssertEqual(Words.normalize("ja-JP"), "en-US"); XCTAssertEqual(Words.normalize("en-GB"), "en-US")
    }
    func testMentionsStayInGroupAndPrivateHasOneRecipient() {
        let members = [Node(["name": "ana", "display": "分析员"])]
        let group = Composer.message(body: "@分析员 请看", member: "", selected: ["all"], members: members)
        XCTAssertEqual(group["to"] as? [String], ["ana"]); XCTAssertEqual(group["channel"] as? String, "group")
        let dm = Composer.message(body: "hello", member: "bob", selected: ["all"], members: members)
        XCTAssertEqual(dm["to"] as? [String], ["bob"]); XCTAssertEqual(dm["channel"] as? String, "private")
    }
    func testTokenAndUnicodeTransport() async throws {
        Stub.handle = { request in
            XCTAssertEqual(request.url?.host, "127.0.0.1")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Relic-Token"), "fixture")
            XCTAssertEqual(request.httpMethod, "POST")
            return (200, "{\"id\":42}")
        }
        let reply = try await client().post(Client.org("组织 one", "/send"), ["body": "你好", "to": ["all"], "channel": "group"])
        XCTAssertEqual(reply["id"].text, "42")
        XCTAssertFalse(Client.org("a/b").dropFirst(9).contains("/"))
    }
    func testFailedApprovalIsAnError() async throws {
        Stub.handle = { _ in (403, "{\"error\":\"missing token\"}") }
        do { _ = try await client().post("/api/org/o/request", ["decision": "approve"]); XCTFail("Expected failure") }
        catch { XCTAssertEqual(error.localizedDescription, "missing token") }
    }
    func testWordsPlural() {
        var words = Words(); words.load(Node(["lang": "en-US", "strings": ["count": ["one": "{n} item", "other": "{n} items"]]]))
        XCTAssertEqual(words.t("count", ["n": "1"]), "1 item"); XCTAssertEqual(words.t("count", ["n": "2"]), "2 items")
    }
    func testHTTP200FailedRequestRemainsFailure() async throws {
        Stub.handle = { _ in (200, #"{"status":"failed","error":"parent would form a cycle"}"#) }
        do { _ = try await client().post("/api/org/o/request", ["request_id": "R1", "decision": "approve"]); XCTFail("Business error must be surfaced") }
        catch { XCTAssertEqual(error.localizedDescription, "parent would form a cycle") }
    }
    func testNonJSONFailureIsReportedWithoutClearingState() async throws {
        Stub.handle = { _ in (502, "temporarily unavailable") }
        do { _ = try await client().get("/api/orgs"); XCTFail("Expected failure") } catch { XCTAssertTrue(error.localizedDescription.contains("502")) }
    }
    func testRequestCannotEscapeLoopback() throws {
        let client = try client()
        XCTAssertThrowsError(try client.request("https://example.com/api/orgs"))
        XCTAssertThrowsError(try client.request("//example.com/api/orgs"))
        XCTAssertThrowsError(try client.request("/api/orgs#token"))
        let request = try client.request(Client.org("组织/a?b", "/send"), body: ["body": "你好"])
        XCTAssertEqual(request.url?.host, "127.0.0.1")
        XCTAssertEqual(request.url?.port, 39321)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
    }
    func testSSEFramingUTF8MultilineCommentsAndCRLF() {
        var decoder = EventDecoder()
        let stream = ": heartbeat\r\n\r\nevent: org\r\ndata: {\"type\":\"org\",\r\ndata: \"org\":\"组织一\"}\r\n\r\ndata: invalid\n\ndata: {\"type\":\"live\",\"item\":{\"seq\":2,\"text\":\"你好\"}}\n\n"
        let events = stream.utf8.compactMap { decoder.append($0) }
        XCTAssertEqual(events.count, 2); XCTAssertEqual(events[0]["org"].text, "组织一"); XCTAssertEqual(events[1]["item"]["text"].text, "你好")
    }
    func testSSEIncompleteFrameIsNotDelivered() {
        var decoder = EventDecoder()
        XCTAssertTrue("data: {\"type\":\"org\"}\n".utf8.compactMap { decoder.append($0) }.isEmpty)
        XCTAssertEqual(decoder.append(10)?["type"].text, "org")
    }
    func testLiveUpdatesMergeBySequenceAndToolID() {
        let first = [Node(["seq": 1, "id": "tool-1", "text": "running", "type": "tool"])]
        let result = Timeline.merge(first, [Node(["seq": 1, "text": "done"]), Node(["seq": 2, "text": "reply"])])
        XCTAssertEqual(result.count, 2); XCTAssertEqual(result[0]["text"].text, "done"); XCTAssertEqual(result[0]["type"].text, "tool")
        XCTAssertEqual(Timeline.merge(result, [Node(["id": "tool-1", "status": "complete"])])[0]["status"].text, "complete")
    }
    func testQuoteAndThreadPayloadMatchesReference() {
        let send = Composer.message(body: "check this", member: "", selected: ["ana", "bob"], members: [], quote: "> Ana: earlier")
        XCTAssertEqual(send["body"] as? String, "> Ana: earlier\n\ncheck this"); XCTAssertEqual(send["to"] as? [String], ["ana", "bob"])
        let reply = Composer.message(body: "answer", member: "ana", selected: [], members: [], replyTo: "42")
        XCTAssertEqual(reply["reply_to"] as? Int, 42); XCTAssertEqual(reply["channel"] as? String, "private"); XCTAssertNil(reply["to"])
    }
    func testExplicitRecipientWinsOverMentions() {
        let send = Composer.message(body: "@bob", member: "", selected: ["ana"], members: [Node(["name": "bob"])])
        XCTAssertEqual(send["to"] as? [String], ["ana"])
    }
    func testTreeCyclesAndFolding() {
        let tree = [Node(["id": "a", "parent": "c"]), Node(["id": "b", "parent": "a"]), Node(["id": "c", "parent": "b"]), Node(["id": "d", "parent": ""])]
        XCTAssertEqual(Tree.descendants("a", in: tree), ["a", "b", "c"])
        var folded: Set<String> = []; Tree.toggle("a", folded: &folded); XCTAssertTrue(folded.contains("a")); Tree.toggle("a", folded: &folded); XCTAssertTrue(folded.isEmpty)
    }
    func testHistoryDropsForwardBranchAndPreservesMember() {
        var history = NavigationHistory(); history.visit(ChatSelection("a")); history.visit(ChatSelection("a", "member")); history.visit(ChatSelection("b"))
        XCTAssertEqual(history.move(-1), ChatSelection("a", "member")); XCTAssertTrue(history.canForward)
        history.visit(ChatSelection("c")); XCTAssertFalse(history.canForward); XCTAssertEqual(history.items.count, 3)
    }
    func testCapabilityChoicesAreNotAssumedOnMac() {
        XCTAssertEqual(Capabilities.hostKinds(Node()), ["claude-code/cli", "codex/cli"])
        XCTAssertEqual(Capabilities.hostKinds(Node(["codex_desktop_wake": true])), ["claude-code/cli", "codex/cli", "codex/gui"])
        XCTAssertFalse(Capabilities.automatic(Node(), harness: "chatgpt", surface: "chat"))
    }
    func testLanguageMenuFiltersWithoutForkingNames() {
        var words = Words(); words.load(Node(["lang": "zh-TW", "languages": [["code": "zh-CN", "name": "简体中文"], ["code": "en-US", "name": "English"], ["code": "ja-JP", "name": "日本語"]], "strings": ["count": ["one": "wrong", "other": "{n} 项"]]]))
        XCTAssertEqual(words.languages.map { $0["code"].text }, ["zh-CN", "en-US"]); XCTAssertEqual(words.t("count", ["n": "1"]), "1 项")
    }
    func testSnapshotPreservesRulesEvidenceAndSessionObject() throws {
        let payload = #"{"org":{"id":"o","parent":{"id":"p","name":"Parent"},"secretary":"ana"},"members":[{"name":"ana","display":"分析员","config":{"surface":"cli","env":{"FLAG":"value"}},"also_in":[{"org":"p","member":"lead"}]}],"tasks":[{"id":"T1","status":"done","evidence":["/tmp/result.json:12"],"report":"## Result"}],"protocols":[{"id":"P1","rules":[{"effect":"check","tools":["Bash"],"code":"def check(call): pass","examples":[{"call":{"tool":"Bash"},"expect":"allow"}]}]}],"documents":[{"key":"handoff","revision":2}],"decisions":[{"kind":"permission","id":"perm","options":[{"id":"allow_once","name":"Allow once"}]}]}"#
        let node = Node(try JSONSerialization.jsonObject(with: Data(payload.utf8)))
        XCTAssertEqual(node["org"]["parent"]["id"].text, "p")
        XCTAssertEqual(node["members"].rows[0]["config"]["env"]["FLAG"].text, "value")
        XCTAssertEqual(node["tasks"].rows[0]["evidence"].rows[0].text, "/tmp/result.json:12")
        XCTAssertEqual(node["protocols"].rows[0]["rules"].rows[0]["examples"].rows[0]["expect"].text, "allow")
        XCTAssertEqual(node["decisions"].rows[0]["options"].rows[0]["id"].text, "allow_once")
    }
}
