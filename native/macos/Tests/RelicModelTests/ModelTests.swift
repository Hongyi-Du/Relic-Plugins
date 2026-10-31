import XCTest
import Foundation
import Combine
import Observation
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
    func testWindowGeometryIsObservedWithoutRepublishingConversationData() async throws {
        let model = try model()
        let changed = expectation(description: "Actual geometry readers are invalidated")
        var dataUpdates = 0
        let subscription = model.objectWillChange.sink { dataUpdates += 1 }
        defer { subscription.cancel() }
        withObservationTracking {
            XCTAssertEqual(model.windowSize, CGSize(width: 1440, height: 900))
        } onChange: { changed.fulfill() }
        model.updateWindowGeometry(CGSize(width: 1024, height: 700))
        await fulfillment(of: [changed], timeout: 1)
        XCTAssertEqual(model.windowSize, CGSize(width: 1024, height: 700))
        XCTAssertEqual(dataUpdates, 0, "Resize must not invalidate the whole conversation model")
    }
    func testResizeStillDismissesVisibleTransientControls() throws {
        let model = try model(); model.recipientPicker = true; model.appMenu = "file"
        model.updateWindowGeometry(CGSize(width: 1024, height: 700))
        XCTAssertFalse(model.recipientPicker)
        XCTAssertNil(model.appMenu)
    }
    func testRepeatedAppMenuDismissalDoesNotRepublishConversationData() throws {
        let model = try model()
        var updates = 0
        let subscription = model.objectWillChange.sink { updates += 1 }
        defer { subscription.cancel() }
        model.appMenu = nil
        XCTAssertEqual(updates, 0)
        model.appMenu = "file"; model.appMenu = "file"
        XCTAssertEqual(updates, 1)
        model.appMenu = nil; model.appMenu = nil
        XCTAssertEqual(updates, 2, "Only actual menu changes should notify views")
    }
    func testDialogPresentationDoesNotInvalidateConversationAndOrganizationData() throws {
        let model = try model()
        var dataUpdates = 0, presentationUpdates = 0
        let data = model.objectWillChange.sink { dataUpdates += 1 }
        let presentation = model.dialogPresentation.objectWillChange.sink { presentationUpdates += 1 }
        defer { data.cancel(); presentation.cancel() }
        model.sheet = .settings
        XCTAssertEqual(model.dialogPresentation.sheet, .settings)
        model.sheet = .settings
        model.sheet = nil
        model.sheet = nil
        XCTAssertEqual(presentationUpdates, 2)
        XCTAssertEqual(dataUpdates, 0, "Opening and closing a dialog must not re-layout the underlying chat")
    }
    func testDialogOpeningStillDismissesAnActiveRecipientPicker() throws {
        let model = try model(); model.recipientPicker = true
        model.sheet = .create
        XCTAssertFalse(model.recipientPicker)
        XCTAssertEqual(model.sheet, .create)
    }
    func testConversationRefreshRequestsTheReferenceHistoryWindowForGroupAndPrivateChats() async throws {
        for member in ["", "analyst"] {
            let model = try model(); model.setSelection(ChatSelection("a", member))
            let received = expectation(description: "Reference chat history request")
            let entries = (1...250).map { ["id": $0, "type": "message", "text": "Message \($0)"] as [String: Any] }
            let payload = String(data: try JSONSerialization.data(withJSONObject: ["items": entries, "more": true]), encoding: .utf8)!
            ModelTransport.handler = { request in
                switch request.url!.path {
                case "/api/orgs": return (200, #"[{"id":"a"}]"#)
                case "/api/cc": return (200, #"{"items":[],"unread":0}"#)
                case "/api/org/a": return (200, #"{"members":[]}"#)
                case "/api/org/a/chat":
                    XCTAssertEqual(request.url?.query, member.isEmpty ? "kind=group&limit=1000" : "kind=private&member=analyst&limit=1000")
                    received.fulfill(); return (200, payload)
                default: XCTFail("Unexpected request " + request.url!.path); return (500, "{}")
                }
            }
            try await model.refresh(); await fulfillment(of: [received], timeout: 1)
            XCTAssertEqual(model.messages.count, 250)
            XCTAssertEqual(model.messages.first?["id"].integer, 1)
            XCTAssertEqual(model.messages.last?["id"].integer, 250)
        }
    }
    func testRoleNameUsesSeatIDOnlyWhenDisplayRepeatsTheLocalizedOfficeTitle() throws {
        let model = try model()
        for (language, title, distinct) in [("en-US", "Secretary", "Chief of staff"), ("zh-CN", "秘书", "秘书处负责人")] {
            model.words.load(Node(["lang": language, "strings": ["common.secretary": title]]))
            model.snapshot = Node(["members": [["name": "secretary", "display": title, "role": distinct]]])
            XCTAssertEqual(model.roleName("secretary", "common.secretary"), "secretary")
            model.snapshot = Node(["members": [["name": "secretary", "display": distinct, "role": title]]])
            XCTAssertEqual(model.roleName("secretary", "common.secretary"), distinct)
        }
    }

    func testCopiesCounterUsesTheServerTotalEvenWhenNotEveryCopyIsReturned() async throws {
        let model = try model()
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, "[]")
            case "/api/cc": return (200, #"{"items":[{"id":1,"read":false}],"unread":3}"#)
            default: XCTFail("Unexpected refresh request " + request.url!.path); return (500, "{}")
            }
        }
        try await model.refresh()
        XCTAssertEqual(model.copies.count, 1)
        XCTAssertEqual(model.unreadCopies, 3)
        model.stop()
    }

    func testSelectWaitsForAnInFlightRefreshAndThenLoadsItsOwnOrganization() async throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        let firstSnapshot = expectation(description: "first organization request is in flight")
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, #"[{"id":"a"},{"id":"b"}]"#)
            case "/api/cc": return (200, #"{"items":[]}"#)
            case "/api/org/a": firstSnapshot.fulfill(); Thread.sleep(forTimeInterval: 0.1); return (200, #"{"org":{"id":"a"},"members":[]}"#)
            case "/api/org/b": return (200, #"{"org":{"id":"b"},"members":[]}"#)
            case "/api/org/a/chat", "/api/org/b/chat": return (200, #"{"items":[],"more":false}"#)
            default: XCTFail("Unexpected refresh request " + request.url!.path); return (500, "{}")
            }
        }
        let first = Task { try await model.refresh() }
        await fulfillment(of: [firstSnapshot], timeout: 2)
        try await model.select("b")
        XCTAssertEqual(model.organization, "b")
        XCTAssertEqual(model.snapshot["org"]["id"].text, "b", "select must finish after the selected snapshot, not after an unrelated in-flight call")
        try await first.value; model.stop()
    }
    func testUnrelatedEventsDoNotReloadTheOrganizationList() async throws {
        let model = try model(); model.setSelection(ChatSelection())
        let unwanted = expectation(description: "no network request for unrelated event"); unwanted.isInverted = true
        ModelTransport.handler = { _ in unwanted.fulfill(); return (200, "[]") }
        await model.receive(Node(["type": "org", "org": "other"]))
        await model.receive(Node(["type": "live", "org": "other", "member": "ana"]))
        await model.receive(Node(["type": "heartbeat"]))
        await fulfillment(of: [unwanted], timeout: 0.5)
        XCTAssertTrue(model.organization.isEmpty); XCTAssertTrue(model.organizations.isEmpty); model.stop()
    }
    func testFileFailureStaysInThePreviewWithTheRequestedPath() async throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        ModelTransport.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/fs/read")
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first?.value, "/workspace/missing.txt")
            return (404, #"{"error":"No such file"}"#)
        }
        try await model.openFile("/workspace/missing.txt", line: 3)
        XCTAssertEqual(model.pane, "files"); XCTAssertTrue(model.panelOpen)
        XCTAssertEqual(model.file["path"].text, "/workspace/missing.txt")
        XCTAssertEqual(model.file["error"].text, "No such file")
        XCTAssertEqual(model.fileLine, 3); XCTAssertTrue(model.error.isEmpty)
    }
    func testFilePreviewRetainsServerDisplayOrderAndMetadata() async throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        ModelTransport.handler = { _ in
            (200, #"{"path":"/workspace/config.json","kind":"json","text":"{\"z\":1,\"a\":2}","display_text":"{\n  \"z\": 1,\n  \"a\": 2\n}","size":13,"mtime":1793271600}"#)
        }
        try await model.openFile("/workspace/config.json")
        XCTAssertEqual(model.file["display_text"].text, "{\n  \"z\": 1,\n  \"a\": 2\n}")
        XCTAssertEqual(model.file["size"].integer, 13)
        XCTAssertEqual(model.file["mtime"].integer, 1793271600)
    }
    func testMessageContinuationUsesRecipientsTimeAndThreadBoundary() throws {
        let model = try model()
        func message(_ id: Int, _ at: String, to: [String] = ["human", "reviewer"], thread: Any = NSNull()) -> Node {
            Node(["id": id, "type": "message", "from": "designer", "to": to, "at": at, "thread": thread])
        }
        let items = [message(1, "2026-10-29T11:00:00Z"), message(2, "2026-10-29T11:01:00Z"),
                     Node(["id": 3, "type": "acts", "at": "2026-10-29T11:01:30Z"]), message(4, "2026-10-29T11:02:00Z", thread: ["count": 1]),
                     message(5, "2026-10-29T11:02:30Z"), message(6, "2026-10-29T11:02:45Z", to: ["reviewer", "human"]),
                     message(7, "2026-10-29T11:05:45Z", to: ["reviewer", "human"])]
        XCTAssertEqual(model.conversationRows(items, separators: false).map(\.continued), [false, true, false, true, false, false, false])
        let gap = model.conversationRows([items[0], message(8, "2026-10-29T11:21:00Z")])
        XCTAssertNotNil(gap[0].separator)
        XCTAssertEqual(gap[1].separator, model.clock(Node("2026-10-29T11:21:00Z")))
    }
    func testReadReceiptOnlyCountsRecipientsOtherThanThePerson() throws {
        let model = try model()
        model.words.load(Node(["lang": "en-US", "strings": ["msg.read_count": "{read}/{total}", "msg.read": "Read", "msg.unread": "Unread"]]))
        XCTAssertEqual(model.readReceipt(Node(["to": ["human", "one", "two"], "read_by": ["human", "one", "unrelated"]])), "1/2")
        XCTAssertEqual(model.readReceipt(Node(["to": ["human", "one"], "read_by": ["one"]])), "Read")
        XCTAssertEqual(model.readReceipt(Node(["to": ["one"], "read_by": []])), "Unread")
    }
    func testInspectorUsesReferencePreviewAndMemberDetailOrder() throws {
        let model = try model()
        model.words.load(Node(["lang": "en-US", "strings": ["card.ex_officio": "From {org}", "state.waiting": "Waiting"]]))
        XCTAssertEqual(model.taskReportPreview("# Ready\n**Reviewed** `paths` | next_step"), "Ready Reviewed paths next step")
        XCTAssertEqual(model.taskReportPreview(String(repeating: "x", count: 81)), String(repeating: "x", count: 79) + "…")
        XCTAssertEqual(model.overviewMemberDetail(Node(["state": "waiting", "doing": "Preparing", "detail": "Older", "ex_officio": ["org_name": "Studio"]])), "From Studio · Preparing")
        XCTAssertEqual(model.overviewMemberDetail(Node(["state": "waiting", "detail": "Reading"])), "Reading")
        XCTAssertEqual(model.overviewMemberDetail(Node(["state": "waiting"])), "Waiting")
        XCTAssertEqual(model.clippedDecisionError("\n  first\tsecond  "), "first second")
    }
    func testInspectorProtocolNotesRespectOriginAndRetirement() throws {
        let model = try model()
        model.words.load(Node(["lang": "en-US", "strings": [
            "org.issued_by_person": "By you", "org.issued_by": "By {name}", "org.protocol_inherits": "Inherited below", "org.protocol_check": "Checked",
            "org.inherited_from": "From {name}", "org.protocol_retired": "{from}/{at}/{by}", "org.protocol_voting": "{n} votes"]]))
        XCTAssertEqual(model.overviewProtocolDetail(Node(["issued_by": ["person": true, "name": "Human"], "inherit": true, "check": true]), source: "protocols"), "By you · Inherited below · Checked")
        XCTAssertEqual(model.overviewProtocolDetail(Node(["from": "Parent", "issued_by": ["name": "Lead"], "check": true]), source: "inherited_protocols"), "From Parent · By Lead · Checked")
        XCTAssertEqual(model.overviewProtocolDetail(Node(["how": "retired", "from": "Parent", "at": "Child", "by": "R2", "check": true]), source: "replaced_protocols"), "Parent/Child/R2")
        XCTAssertEqual(model.overviewProtocolDetail(Node(["status": "proposed", "votes": 2]), source: "protocols"), "2 votes")
    }
    func testReferenceDateFormattingKeeps24HourClockAndRelativeCalendarDays() throws {
        let model = try model()
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let now = Timeline.date(Node("2026-10-29T15:00:00Z"))!
        for language in ["en-US", "zh-CN"] {
            model.words.load(Node(["lang": language, "strings": ["time.today": "today-fixture", "time.yesterday": "yesterday-fixture"]]))
            XCTAssertEqual(model.clock(Node("2026-10-29T13:07:00Z"), calendar: calendar), "13:07")
            XCTAssertEqual(model.day(Node("2026-10-29T00:00:00Z"), now: now, calendar: calendar), "today-fixture")
            XCTAssertEqual(model.day(Node("2026-10-28T23:59:00Z"), now: now, calendar: calendar), "yesterday-fixture")
            XCTAssertEqual(model.shortWhen(Node("2026-10-29T13:07:00Z"), now: now, calendar: calendar), "13:07")
            XCTAssertEqual(model.clock(Node("invalid"), calendar: calendar), "")
        }
        model.words.load(Node(["lang": "en-US", "strings": [:]]))
        XCTAssertEqual(model.day(Node("2026-10-20T12:00:00Z"), now: now, calendar: calendar), "October 20")
        XCTAssertEqual(model.day(Node("2025-10-20T12:00:00Z"), now: now, calendar: calendar), "October 20, 2025")
        XCTAssertEqual(model.shortWhen(Node("2026-10-20T12:00:00Z"), now: now, calendar: calendar), "10/20")
    }
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
    func testQuotePreviewKeepsAuthorAndBodySeparateAcrossDraftRestorationAndClear() throws {
        let model = try model(); model.setSelection(ChatSelection("a"))
        model.words.load(Node(["lang": "en-US", "strings": ["sel.quote_line": "{who}: {text}"]]))
        model.setQuote("First line\nSecond line", from: "ana")
        XCTAssertEqual(model.quote, "> ana: First line\n> Second line")
        XCTAssertEqual(model.quoteAuthor, "ana")
        XCTAssertEqual(model.quotePreviewText, "First line\nSecond line")
        model.setSelection(ChatSelection("b")); XCTAssertEqual(model.quoteAuthor, "")
        model.setSelection(ChatSelection("a")); XCTAssertEqual(model.quoteAuthor, "ana")
        XCTAssertEqual(model.quotePreviewText, "First line\nSecond line")
        model.persistDraft()
        let reopened = Model(defaults: model.defaults); reopened.setSelection(ChatSelection("a"))
        XCTAssertEqual(reopened.quoteAuthor, "ana"); XCTAssertEqual(reopened.quotePreviewText, "First line\nSecond line")
        reopened.quote = ""
        XCTAssertEqual(reopened.quoteAuthor, ""); XCTAssertEqual(reopened.quoteText, "")
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
        XCTAssertEqual(model.historyPagesLoaded, 1)
        model.setSelection(ChatSelection("b")); XCTAssertEqual(model.historyPagesLoaded, 0)
    }
    func testRefreshingLatestPageDoesNotReopenExhaustedHistoryOrDiscardOlderMessages() async throws {
        let model = try model(); defer { model.stop() }
        model.setSelection(ChatSelection("a"))
        var requestedBefore = false
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, #"[{"id":"a"}]"#)
            case "/api/cc": return (200, #"{"items":[],"unread":0}"#)
            case "/api/org/a": return (200, #"{"members":[]}"#)
            case "/api/org/a/chat":
                if request.url!.query!.contains("before=1001") {
                    requestedBefore = true
                    return (200, #"{"items":[{"id":1,"body":"first"}],"more":false}"#)
                }
                return (200, #"{"items":[{"id":1001,"body":"latest"}],"more":true}"#)
            default: XCTFail("Unexpected request"); return (500, "{}")
            }
        }
        try await model.refresh(); XCTAssertTrue(model.moreChat)
        try await model.loadOlder(); XCTAssertTrue(requestedBefore); XCTAssertFalse(model.moreChat)
        model.draft = "unsent"; model.plainOne.insert("1")
        try await model.select("a")
        XCTAssertFalse(model.moreChat)
        XCTAssertEqual(model.messages.map { $0["id"].integer }, [1, 1001])
        XCTAssertEqual(model.historyPagesLoaded, 1)
        XCTAssertEqual(model.draft, "unsent"); XCTAssertTrue(model.plainOne.contains("1"))
    }
    func testPreparedConversationDiscardsPreviousSelectionAndKeepsStableIDs() async throws {
        let model = try model(); defer { model.stop() }
        model.setSelection(ChatSelection("a"))
        model.messages = (1...5500).map { Node(["id": $0, "type": "message", "from": "secretary", "at": 1000 + $0]) }
        await Task.yield()
        model.setSelection(ChatSelection("b"))
        model.messages = [Node(["id": 9000, "type": "message", "from": "member", "at": 20000])]
        let prepared = expectation(description: "latest selection projected off main actor")
        let subscription = model.$streamRows.sink { rows in
            if rows.map(\.id) == ["id:9000#0"] { prepared.fulfill() }
        }
        await fulfillment(of: [prepared], timeout: 5)
        XCTAssertEqual(model.streamRows.map(\.id), ["id:9000#0"])
        XCTAssertFalse(model.isPreparingConversation)
        subscription.cancel()
    }
    func testEventBurstDuringSlowRefreshProducesOneFollowupWithoutAQueuedTimer() async throws {
        let model = try model(); defer { model.stop() }
        model.setSelection(ChatSelection("a"))
        let loading = expectation(description: "snapshot request in flight")
        var snapshots = 0
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, #"[{"id":"a"}]"#)
            case "/api/cc": return (200, #"{"items":[],"unread":0}"#)
            case "/api/org/a":
                snapshots += 1
                if snapshots == 1 { loading.fulfill() }
                Thread.sleep(forTimeInterval: 0.15)
                return (200, #"{"members":[]}"#)
            case "/api/org/a/chat": return (200, #"{"items":[],"more":false}"#)
            default: XCTFail("Unexpected request"); return (500, "{}")
            }
        }
        let refresh = Task { try await model.refresh() }
        await fulfillment(of: [loading], timeout: 2)
        for _ in 0..<1000 { await model.receive(Node(["type": "org", "org": "a"])) }
        try await refresh.value
        try await Task.sleep(for: .milliseconds(500))
        XCTAssertEqual(snapshots, 2)
    }
    func testChangingChatPreservesItsOrganizationTreeButChangingOrganizationClearsIt() throws {
        let model = try model(); defer { model.stop() }
        model.setSelection(ChatSelection("a"))
        model.snapshot = Node(["org": ["id": "a"], "members": [["name": "analyst"], ["name": "secretary"]]])
        model.messages = [Node(["id": 1, "body": "group message"])]
        model.setSelection(ChatSelection("a", "analyst"))
        XCTAssertEqual(model.members.map { $0["name"].text }, ["analyst", "secretary"])
        XCTAssertEqual(model.snapshot["org"]["id"].text, "a")
        XCTAssertTrue(model.messages.isEmpty)
        model.setSelection(ChatSelection("b"))
        XCTAssertTrue(model.members.isEmpty)
        XCTAssertTrue(model.snapshot["org"].isNull)
    }
    func testUnchangedRefreshDoesNotRepublishEntireViewButNewMessageStillAppears() async throws {
        let model = try model(); defer { model.stop() }
        var newMessage = false
        ModelTransport.handler = { request in
            switch request.url!.path {
            case "/api/orgs": return (200, #"[{"id":"a"}]"#)
            case "/api/cc": return (200, #"{"items":[],"unread":0}"#)
            case "/api/org/a": return (200, #"{"org":{"id":"a"},"members":[]}"#)
            case "/api/org/a/chat": return (200, newMessage
                ? #"{"items":[{"id":1,"body":"first"},{"id":2,"body":"new"}],"more":false}"#
                : #"{"items":[{"id":1,"body":"first"}],"more":false}"#)
            default: XCTFail("Unexpected request"); return (500, "{}")
            }
        }
        try await model.refresh()
        while model.isPreparingConversation { await Task.yield() }
        var publications = 0
        let subscription = model.objectWillChange.sink { publications += 1 }
        try await model.refresh()
        XCTAssertEqual(publications, 0, "unchanged SSE refresh must not invalidate all view trees")
        newMessage = true; try await model.refresh()
        while model.isPreparingConversation { await Task.yield() }
        XCTAssertEqual(model.messages.map { $0["id"].integer }, [1, 2])
        XCTAssertGreaterThan(publications, 0)
        subscription.cancel()
    }
}

private extension InputStream {
    func readAll() -> Data { open(); defer { close() }; var result = Data(), buffer = [UInt8](repeating: 0, count: 4096); while hasBytesAvailable { let count = read(&buffer, maxLength: buffer.count); if count <= 0 { break }; result.append(contentsOf: buffer.prefix(count)) }; return result }
}
