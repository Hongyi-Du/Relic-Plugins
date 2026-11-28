import XCTest
import RelicCore
@testable import Relic

final class ConversationWindowTests: XCTestCase {
    private func rows(_ ids: ClosedRange<Int>) -> [ConversationRow] {
        ids.map { ConversationRow(id: "id:\($0)#0", item: Node(["id": $0, "type": "message"]), separator: nil, continued: false) }
    }

    func testDefaultWindowShowsOnlyTheNewestBoundedRows() {
        let all = rows(1...1000)
        let range = ConversationWindow(selection: "a/").range(in: all, selection: "a/")
        XCTAssertEqual(range, (1000 - ConversationWindow.initial)..<1000)
        XCTAssertEqual(ConversationWindow(selection: "a/").range(in: rows(1...5), selection: "a/"), 0..<5)
        XCTAssertEqual(ConversationWindow().range(in: [], selection: ""), 0..<0)
    }

    func testAnotherChatStartsAtItsOwnTail() {
        let all = rows(1...500)
        let reading = ConversationWindow(selection: "a/", anchor: "id:10#0", count: ConversationWindow.maximum)
        XCTAssertEqual(reading.range(in: all, selection: "b/"), (500 - ConversationWindow.initial)..<500)
    }

    func testPinnedHistoryKeepsItsRowsWhenOlderPagesAndNewRowsArrive() {
        var all = rows(201...400)
        let window = ConversationWindow.pinned(0..<24, in: all, selection: "a/")
        XCTAssertEqual(window.range(in: all, selection: "a/"), 0..<24)
        all = rows(1...420)
        XCTAssertEqual(window.range(in: all, selection: "a/"), 200..<224, "An earlier page must not move the rows being read")
    }

    func testShowingTheNewestRowFollowsLaterRows() {
        let all = rows(1...100)
        let window = ConversationWindow.showing(60..<100, in: all, selection: "a/")
        XCTAssertNil(window.anchor)
        XCTAssertEqual(window.range(in: rows(1...101), selection: "a/"), 61..<101)
        XCTAssertEqual(ConversationWindow.showing(10..<50, in: all, selection: "a/").anchor, "id:11#0")
    }

    func testWindowNeverExceedsItsMaximum() {
        let all = rows(1...1000)
        let window = ConversationWindow(selection: "a/", anchor: nil, count: 10_000)
        XCTAssertEqual(window.range(in: all, selection: "a/").count, ConversationWindow.maximum)
    }
}
