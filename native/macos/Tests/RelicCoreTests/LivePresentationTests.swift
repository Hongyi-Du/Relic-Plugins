import XCTest
@testable import RelicCore

final class LivePresentationTests: XCTestCase {
    func testRealHubTurnProjectionRetainsOrderedActionsAndOnlyLatestReply() throws {
        let payload = #"{"status":{"state":"waiting"},"items":[{"seq":1,"type":"prompt","start":true,"text":"old prompt"},{"seq":2,"type":"assistant","text":"old reply"},{"seq":3,"type":"prompt","start":true,"text":"review"},{"seq":4,"id":"read","type":"tool","title":"Read README.md","status":"completed","text":"Read README.md\n\tLayout: three columns"},{"seq":5,"id":"compare","type":"tool","title":"Compare current screens","status":"in_progress"},{"seq":6,"type":"error","text":"Image unavailable"},{"seq":7,"type":"assistant","text":"partial"},{"seq":8,"id":"approve","type":"permission","title":"Read the design notes","options":[{"id":"once","name":"Allow once","kind":"allow_once"}]},{"seq":9,"type":"assistant","text":"latest **reply**"}]}"#
        let live = Node(try JSONSerialization.jsonObject(with: Data(payload.utf8)))
        let active = Timeline.activeLive(live["items"].rows, status: live["status"], decisions: [])
        let turn = LivePresentation(items: active, status: live["status"], member: Node(["embedded": true, "has_transcript": true]))
        XCTAssertEqual(turn.prompt?["text"].text, "review")
        XCTAssertEqual(turn.reply, "latest **reply**")
        XCTAssertEqual(turn.actions.map { $0["seq"].integer }, [4,5,6,8])
        XCTAssertEqual(turn.actions[0]["text"].text, "Read README.md\n\tLayout: three columns")
        XCTAssertEqual(turn.actions[3]["options"].rows[0]["id"].text, "once")
        XCTAssertFalse(turn.showsTyping)
    }
    func testTypingRequiresRunningAndNoVisibleAssistantText() {
        let prompt = Node(["type": "prompt", "text": "review"])
        XCTAssertTrue(LivePresentation(items: [prompt], status: Node(["state": "running"]), member: Node()).showsTyping)
        XCTAssertFalse(LivePresentation(items: [prompt], status: Node(["state": "waiting"]), member: Node()).showsTyping)
        XCTAssertFalse(LivePresentation(items: [prompt, Node(["type": "assistant", "text": "reply"])], status: Node(["state": "running"]), member: Node()).showsTyping)
        XCTAssertNil(LivePresentation(items: [prompt], status: Node(), member: Node(["embedded": true, "has_transcript": false])).prompt)
    }
    func testUnknownToolStatusRetainsServerWording() {
        var words = Words(); words.load(Node(["lang": "en-US", "strings": ["live.pending": "Pending", "task.working": "In progress", "task.done": "Done", "common.failed": "Failed"]]))
        XCTAssertEqual(["pending", "in_progress", "completed", "failed", "paused"].map { LivePresentation.toolState($0, words: words) }, ["Pending", "In progress", "Done", "Failed", "paused"])
    }
}
