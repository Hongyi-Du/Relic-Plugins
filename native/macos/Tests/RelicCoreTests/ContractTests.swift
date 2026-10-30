import XCTest
import CoreGraphics
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
    func testCancelledReadIsTaskCancellationAndDoesNotRenewOrRetry() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        var renewed = false
        let client = try Client(port: 39321, token: "fixture", session: URLSession(configuration: configuration), serverRecord: { renewed = true; return Node() })
        var calls = 0
        Stub.handle = { _ in calls += 1; throw URLError(.cancelled) }
        do { _ = try await client.get("/api/org/a/document?key=review-plan"); XCTFail("Expected task cancellation") }
        catch is CancellationError {} catch { XCTFail("Unexpected user-visible error: \(error)") }
        XCTAssertEqual(calls, 1)
        XCTAssertFalse(renewed)
    }

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
    func testSharedListTemplatesUseBothLanguagesAndAllLengths() {
        var words = Words(); words.load(Node(["lang": "en-US", "strings": ["list.pair": "{a} and {b}", "list.middle": "{a}, {b}", "list.end": "{a}, and {b}"]]))
        XCTAssertEqual(words.list([]), ""); XCTAssertEqual(words.list(["A"]), "A"); XCTAssertEqual(words.list(["A", "B"]), "A and B"); XCTAssertEqual(words.list(["A", "B", "C"]), "A, B, and C")
        words.load(Node(["lang": "zh-CN", "strings": ["list.pair": "{a}、{b}", "list.middle": "{a}、{b}", "list.end": "{a}、{b}"]]))
        XCTAssertEqual(words.list(["甲", "乙", "丙", "丁"]), "甲、乙、丙、丁")
    }
    func testHTTP200FailedRequestRemainsFailure() async throws {
        Stub.handle = { _ in (200, #"{"status":"failed","error":"parent would form a cycle"}"#) }
        do { _ = try await client().post("/api/org/o/request", ["request_id": "R1", "decision": "approve"]); XCTFail("Business error must be surfaced") }
        catch { XCTAssertEqual(error.localizedDescription, "parent would form a cycle") }
    }
    func testMissingTokenRefreshesVerifiedRecordAndRetriesRejectedPostOnce() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        let client = try Client(port: 39321, token: "old", session: URLSession(configuration: configuration), serverRecord: { Node(["port": 39322, "token": "new", "pid": 42, "instance": "new-instance"]) })
        var calls: [String] = []
        Stub.handle = { request in
            calls.append(request.url!.path + ":" + (request.value(forHTTPHeaderField: "X-Relic-Token") ?? ""))
            if request.value(forHTTPHeaderField: "X-Relic-Token") == "old" { return (403, #"{"error":"missing token"}"#) }
            XCTAssertEqual(request.url?.host, "127.0.0.1"); XCTAssertEqual(request.url?.port, 39322)
            if request.url?.path == "/api/lifecycle" { return (200, #"{"app":"relic","state":"running","port":39322,"pid":42,"instance":"new-instance"}"#) }
            return (200, #"{"id":7}"#)
        }
        let sent = try await client.post("/api/org/a/send", ["body": "only once accepted"])
        XCTAssertEqual(sent["id"].integer, 7)
        XCTAssertEqual(calls, ["/api/org/a/send:old", "/api/lifecycle:new", "/api/org/a/send:new"])
    }
    func testForgedLifecycleRecordIsNeverAdopted() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        let client = try Client(port: 39321, token: "old", session: URLSession(configuration: configuration), serverRecord: { Node(["port": 39322, "token": "candidate", "pid": 42, "instance": "expected"]) })
        Stub.handle = { request in
            if request.url?.path == "/api/lifecycle" { return (200, #"{"app":"relic","state":"running","port":39322,"pid":99,"instance":"wrong"}"#) }
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Relic-Token"), "old"); return (403, #"{"error":"missing token"}"#)
        }
        do { _ = try await client.post("/api/org/a/send", ["body": "keep draft"]); XCTFail("Expected rejection") } catch { XCTAssertEqual(error.localizedDescription, "missing token") }
        XCTAssertEqual(try client.request("/api/orgs").value(forHTTPHeaderField: "X-Relic-Token"), "old")
    }
    func testAmbiguousWriteFailureNeverRefreshesOrReplays() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        let client = try Client(port: 39321, token: "old", session: URLSession(configuration: configuration), serverRecord: { XCTFail("Ambiguous write must not read a new token or retry"); return Node() })
        var requests = 0
        Stub.handle = { _ in requests += 1; throw URLError(.networkConnectionLost) }
        do { _ = try await client.post("/api/org/a/send", ["body": "may already be sent"]); XCTFail("Expected transport error") } catch {}
        XCTAssertEqual(requests, 1)
        Stub.handle = { _ in requests += 1; return (403, #"{"error":"request denied by policy"}"#) }
        do { _ = try await client.post("/api/org/a/request", ["decision": "approve"]); XCTFail("Expected policy rejection") } catch { XCTAssertEqual(error.localizedDescription, "request denied by policy") }
        XCTAssertEqual(requests, 2)
    }
    func testReconnectRenewsTransportOnlyAfterLifecycleVerification() async throws {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [Stub.self]
        let client = try Client(port: 39321, token: "old", session: URLSession(configuration: configuration), serverRecord: { Node(["port": 39322, "token": "new", "pid": 42, "instance": "next"]) })
        Stub.handle = { request in XCTAssertEqual(request.url?.path, "/api/lifecycle"); return (200, #"{"app":"relic","state":"running","port":39322,"pid":42,"instance":"next"}"#) }
        let renewed = await client.refreshRecord(); XCTAssertTrue(renewed)
        let events = try client.request("/api/events"); XCTAssertEqual(events.url?.port, 39322); XCTAssertEqual(events.value(forHTTPHeaderField: "X-Relic-Token"), "new")
        let unchanged = await client.refreshRecord(); XCTAssertFalse(unchanged)
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
        let payload = ###"{"org":{"id":"o","parent":{"id":"p","name":"Parent"},"secretary":"ana"},"members":[{"name":"ana","display":"分析员","config":{"surface":"cli","env":{"FLAG":"value"}},"also_in":[{"org":"p","member":"lead"}]}],"tasks":[{"id":"T1","status":"done","evidence":["/tmp/result.json:12"],"report":"## Result"}],"protocols":[{"id":"P1","rules":[{"effect":"check","tools":["Bash"],"code":"def check(call): pass","examples":[{"call":{"tool":"Bash"},"expect":"allow"}]}]}],"documents":[{"key":"handoff","revision":2}],"decisions":[{"kind":"permission","id":"perm","options":[{"id":"allow_once","name":"Allow once"}]}]}"###
        let node = Node(try JSONSerialization.jsonObject(with: Data(payload.utf8)))
        XCTAssertEqual(node["org"]["parent"]["id"].text, "p")
        XCTAssertEqual(node["members"].rows[0]["config"]["env"]["FLAG"].text, "value")
        XCTAssertEqual(node["tasks"].rows[0]["evidence"].rows[0].text, "/tmp/result.json:12")
        XCTAssertEqual(node["protocols"].rows[0]["rules"].rows[0]["examples"].rows[0]["expect"].text, "allow")
        XCTAssertEqual(node["decisions"].rows[0]["options"].rows[0]["id"].text, "allow_once")
    }
    func testLiveTurnBoundaryAndCompletedTurnAreNotDuplicated() {
        let items = [Node(["seq": 1, "start": true, "type": "prompt", "at": "2026-10-29T06:00:00Z"]), Node(["seq": 2, "type": "assistant", "text": "old"]), Node(["seq": 3, "start": true, "type": "prompt", "at": "2026-10-29T07:00:00Z"]), Node(["seq": 4, "type": "assistant", "text": "new"])]
        XCTAssertEqual(Timeline.activeLive(items, status: Node(["state": "running"]), decisions: []).map { $0["seq"].integer }, [3, 4])
        XCTAssertTrue(Timeline.activeLive(items, status: Node(["state": "idle"]), decisions: []).isEmpty)
        let pending = Node(["seq": 5, "type": "permission", "id": "p1"])
        XCTAssertEqual(Timeline.activeLive(items + [pending], status: Node(["state": "idle"]), decisions: [Node(["kind": "permission", "id": "p1"])]).count, 1)
    }
    func testEmbeddedTranscriptStripsEnginePromptAndFoldsTools() {
        var words = Words(); words.load(Node(["lang": "en-US", "strings": ["msg.auto_woken": "Woken"]]))
        let steps = [Node(["role": "user", "text": "[Relic App] The person (human) writes to you directly: hello\n\nReply in this conversation; extra", "at": "2026-10-29T06:00:00Z"]), Node(["role": "tool_call", "tool": "Bash", "text": "pwd", "at": "2026-10-29T06:00:01Z"]), Node(["role": "tool_result", "text": "/tmp", "at": "2026-10-29T06:00:02Z"]), Node(["role": "assistant", "text": "done", "at": "2026-10-29T06:00:03Z"])]
        let items = Timeline.conversation(steps: steps, chat: [Node(["body": "duplicate"])], member: Node(["name": "ana", "embedded": true]), live: [], words: words)
        XCTAssertEqual(items.count, 3); XCTAssertEqual(items[0]["body"].text, "hello"); XCTAssertEqual(items[1]["type"].text, "acts"); XCTAssertEqual(items[1]["steps"].rows.count, 2); XCTAssertEqual(items[2]["body"].text, "done")
    }
    func testMarkdownHasNativeBlocksAndTableCells() {
        let blocks = NativeMarkdown.blocks("# Title\n\n> Quote\n- first\n  continued\n\n| Name | Value |\n| --- | --- |\n| A | **B** |\n\n```swift\nlet x = 1\n```")
        XCTAssertEqual(blocks.map(\.kind), ["head", "quote", "list", "table", "code"])
        XCTAssertEqual(NativeMarkdown.table(blocks[3]), [["Name", "Value"], ["A", "**B**"]])
        XCTAssertEqual(blocks[4].text, "let x = 1")
    }
    func testReferenceInlineGrammarKeepsUnsupportedMarkdownVisible() {
        let tokens = NativeMarkdown.inline("*italic* [label](https://example.com/a) **bold** and /tmp/a.swift:12。")
        XCTAssertEqual(tokens.map(\.kind), ["text", "url", "text", "bold", "text", "path", "text"])
        XCTAssertEqual(tokens[0].text, "*italic* [label](")
        XCTAssertEqual(tokens[5].text, "/tmp/a.swift:12")
        let rendered = NativeMarkdown.attributed("*italic* **bold**")
        XCTAssertEqual(String(rendered.characters), "*italic* bold")
        XCTAssertEqual(NativeMarkdown.inline("src/app.swift").map(\.kind), ["text"])
    }
    func testReferenceListsNumberEveryRowFromTheFirstMarkerAndTablesRequireAHeaderRule() {
        let ordered = NativeMarkdown.list(NativeMarkdown.blocks("3) first\n99) second\n  + nested")[0])
        XCTAssertEqual(ordered.map(\.marker), ["3.", "4.", "5."])
        XCTAssertFalse(NativeMarkdown.tableHasHeader(NativeMarkdown.blocks("| A | B |\n| C | D |")[0]))
        XCTAssertTrue(NativeMarkdown.tableHasHeader(NativeMarkdown.blocks("| A | B |\n| --- | --- |")[0]))
    }
    func testDraftRoundTripRetainsQuoteAndMultiRecipient() throws {
        var draft = ChatDraft(); draft.text = "你好"; draft.quote = "> Earlier"; draft.recipients = ["a", "b"]
        let decoded = try JSONDecoder().decode(ChatDraft.self, from: JSONEncoder().encode(draft))
        XCTAssertEqual(decoded, draft)
    }
    func testNativeLinksKeepURLsSeparateFromLocalFileReferences() throws {
        XCTAssertEqual(NativeLinks.file("/tmp/a.py:12:3")?.path, "/tmp/a.py"); XCTAssertEqual(NativeLinks.file("/tmp/a.py:12:3")?.line, 12)
        XCTAssertEqual(NativeLinks.file(#"C:\work\a.py:9"#)?.path, #"C:\work\a.py"#)
        XCTAssertNil(NativeLinks.file("https://example.com/a")); XCTAssertNil(NativeLinks.file("src/app.swift"))
        let linked = NativeLinks.markdown("https://example.com/a [keep](https://example.com/b) `/tmp/a.py:12` and /tmp/b.py.")
        XCTAssertTrue(linked.contains("[https://example.com/a](https://example.com/a)")); XCTAssertTrue(linked.contains("[keep](https://example.com/b)"))
        XCTAssertEqual(linked.components(separatedBy: "relic-file://").count - 1, 2)
        let url = try XCTUnwrap(NativeLinks.file("/tmp/中文 a.swift:12")?.url)
        XCTAssertEqual(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "path" })?.value, "/tmp/中文 a.swift")
    }
    func testHistoryInsertionKeepsRowIdentitiesAndRepeatedKeysDistinct() {
        let old = NodeRow.identify([Node(["id": 2, "body": "old"]), Node(["id": 3])])
        let updated = NodeRow.identify([Node(["id": 1]), Node(["id": 2, "body": "new"]), Node(["id": 3])])
        XCTAssertEqual(old.map(\.id), Array(updated.dropFirst()).map(\.id))
        XCTAssertEqual(Set(NodeRow.identify([Node("same"), Node("same")]).map(\.id)).count, 2)
    }
    func testMarkdownListContinuationDoesNotInventAnotherBullet() {
        let block = NativeMarkdown.blocks("3. first\n   continuation\n  + nested\n4. last")[0]
        let list = NativeMarkdown.list(block)
        XCTAssertEqual(list.count, 3); XCTAssertEqual(list[0].marker, "3."); XCTAssertEqual(list[0].text, "first\ncontinuation"); XCTAssertTrue(list[1].indented)
    }
    func testSendKeyPreservesIMECompletionAndNewline() {
        XCTAssertTrue(Composer.sendsReturn(shift: false, composing: false, completing: false))
        XCTAssertFalse(Composer.sendsReturn(shift: true, composing: false, completing: false))
        XCTAssertFalse(Composer.sendsReturn(shift: false, composing: true, completing: false))
        XCTAssertFalse(Composer.sendsReturn(shift: false, composing: false, completing: true))
    }
    func testParallelToolResultsPairWithOldestPendingCall() {
        let rows = ToolActivity.pair([Node(["role": "tool_result", "text": "orphan"]), Node(["role": "tool_call", "tool": "mcp__plugin_relic_org__org_status", "text": #"{"command":"pwd"}"#]), Node(["role": "tool_call", "tool": "mcp__Read", "text": #"{"file_path":"/tmp/a"}"#]), Node(["role": "tool_result", "text": "first", "error": true]), Node(["role": "tool_result", "text": "second"])])
        XCTAssertEqual(rows.count, 3); XCTAssertNil(rows[0].call)
        XCTAssertEqual(rows[1].title, "Relic org_status"); XCTAssertEqual(rows[1].argument, "pwd"); XCTAssertEqual(rows[1].result?["text"].text, "first"); XCTAssertTrue(rows[1].failed)
        XCTAssertEqual(rows[2].title, "Read"); XCTAssertEqual(rows[2].argument, "/tmp/a"); XCTAssertEqual(rows[2].result?["text"].text, "second")
    }
    func testActivitySummaryCountsRepeatedToolsAndKeepsStableTies() {
        let names = ["Read", "Bash", "Read", "Search", "Bash", "Write", "Glob"]
        let steps = [Node(["role": "tool_result", "text": "orphan"])] + names.map { Node(["role": "tool_call", "tool": $0, "text": "  " + String(repeating: "x", count: 130) + "  "]) }
        let rows = ToolActivity.pair(steps)
        XCTAssertEqual(ToolActivity.summary(rows), "Read ×2 · Bash ×2 · Search · Write")
        XCTAssertEqual(rows[1].argument, String(repeating: "x", count: 119) + "…")
        XCTAssertEqual(ToolActivity.summary(ToolActivity.pair([steps[0]])), "")
    }
    func testChartParentCentersChildrenAndOrdersCabinetBeforeSubgroups() {
        let graph = OrganizationLayout([Node(["id": "root", "status": "active"]), Node(["id": "sub", "parent": "root", "kind": "subgroup", "status": "active"]), Node(["id": "cab", "parent": "root", "cabinet": true, "status": "active"]), Node(["id": "formal", "parent": "root", "status": "active"])])
        XCTAssertEqual(graph.nodes.map { $0["id"].text }, ["root", "cab", "formal", "sub"])
        XCTAssertEqual(graph.centers["root"]!.x, (graph.centers["cab"]!.x + graph.centers["sub"]!.x) / 2, accuracy: 0.01)
        XCTAssertLessThan(graph.centers["root"]!.y, graph.centers["formal"]!.y)
        XCTAssertGreaterThan(graph.centers["formal"]!.x - graph.centers["cab"]!.x, OrganizationLayout.card.width)
        XCTAssertEqual(graph.parents["cab"], "root")
    }
    func testChartCyclesOrphansAndFocusedBoundsStayReachable() {
        let graph = OrganizationLayout([Node(["id": "a", "parent": "b"]), Node(["id": "b", "parent": "a"]), Node(["id": "orphan", "parent": "filtered"]), Node(["id": "self", "parent": "self"])])
        XCTAssertEqual(Set(graph.nodes.map { $0["id"].text }), Set(["a", "b", "orphan", "self"]))
        XCTAssertEqual(graph.nodes.count, 4); XCTAssertEqual(graph.parents.count, 1)
        let focus = graph.bounds(focus: "orphan"), all = graph.bounds()
        XCTAssertEqual(focus.width, OrganizationLayout.card.width); XCTAssertTrue(all.contains(focus))
        XCTAssertEqual(OrganizationLayout([]).bounds().width, OrganizationLayout.card.width + 48)
    }
}
