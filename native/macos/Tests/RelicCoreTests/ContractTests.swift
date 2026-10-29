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
}
