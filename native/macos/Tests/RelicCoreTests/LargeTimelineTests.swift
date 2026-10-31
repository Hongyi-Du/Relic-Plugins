import XCTest
@testable import RelicCore

final class LargeTimelineTests: XCTestCase {
    func testContentDiffIgnoresDictionaryOrderButKeepsNestedValuesAndRowOrder() async {
        let a = Node(["id": 1, "data": ["done": false, "body": "original"]] as [String: Any])
        let b = Node(["data": ["body": "original", "done": false], "id": 1] as [String: Any])
        let c = Node(["id": 1, "data": ["done": true, "body": "original"]] as [String: Any])
        let equal = await Node.sameContent(a, b), changed = await Node.sameContent(a, c)
        let ordered = await Node.sameRows([a, c], [b, c]), reordered = await Node.sameRows([a, c], [c, b])
        XCTAssertTrue(equal); XCTAssertFalse(changed); XCTAssertTrue(ordered); XCTAssertFalse(reordered)
    }
    func testMergeKeepsEarliestMatchWhenIDsAndSequencesCollideAndChange() {
        let current = [Node(["id": 1, "seq": 10, "body": "one"]), Node(["id": 2, "seq": 20]), Node(["id": 1, "seq": 30])]
        let incoming = [Node(["id": 2, "seq": 10, "body": "updated"]), Node(["id": 1, "seq": 40]), Node(["id": 3]), Node(["id": 3, "extra": true])]
        let actual = Timeline.merge(current, incoming)
        var expected = current
        for item in incoming {
            if let index = expected.firstIndex(where: {
                (!item["seq"].isNull && item["seq"].text == $0["seq"].text) || (!item["id"].isNull && item["id"].text == $0["id"].text)
            }) { expected[index] = Node(expected[index].object.merging(item.object) { _, new in new }) }
            else { expected.append(item) }
        }
        XCTAssertEqual(actual.count, expected.count)
        for (a, b) in zip(actual, expected) { XCTAssertTrue(NSDictionary(dictionary: a.object).isEqual(to: b.object)) }
    }

    func testLargeHistoryMergeRetainsEveryMessageAndUpdatesOnlyTheLatestPage() async {
        let history = (1...5500).map { Node(["id": $0, "body": "message \($0)", "retained": true]) }
        let latest = (4501...5510).map { Node(["id": $0, "body": "updated \($0)"]) }
        let merged = await Timeline.mergeInBackground(history, latest)
        XCTAssertEqual(merged.count, 5510)
        XCTAssertEqual(merged.map { $0["id"].integer }, Array(1...5510))
        XCTAssertEqual(merged[0]["body"].text, "message 1")
        XCTAssertEqual(merged[4500]["body"].text, "updated 4501")
        XCTAssertTrue(merged[4500]["retained"].flag)
    }

    func testMarkdownPreparationPreservesBlocksLinksListsAndTableCells() async {
        let source = "# **Heading**\n\n- **bold**\n- https://example.com\n\n| Name | Link |\n| --- | --- |\n| **A** | /tmp/file.swift |\n\n```swift\nlet x = 1\n```"
        let prepared = await MarkdownPreparation.shared.prepare(source)
        XCTAssertEqual(prepared.blocks.map(\.kind), NativeMarkdown.blocks(source).map(\.kind))
        let list = prepared.blocks.first { $0.kind == "list" }!
        XCTAssertEqual(prepared.list(list).map(\.text), ["**bold**", "https://example.com"])
        XCTAssertEqual(prepared.inline("**bold**"), NativeMarkdown.attributed("**bold**"))
        let table = prepared.blocks.first { $0.kind == "table" }!
        XCTAssertEqual(prepared.table(table), NativeMarkdown.table(table))
        XCTAssertEqual(prepared.inline("/tmp/file.swift"), NativeMarkdown.attributed("/tmp/file.swift"))
    }

    func testMarkdownCacheStaysBoundedWhenScrollingThroughHistory() async {
        let cache = MarkdownPreparation()
        for index in 0..<400 { _ = await cache.prepare("message \(index): **long** " + String(repeating: "a", count: 12_000)) }
        let count = await cache.retainedCount, bytes = await cache.retainedSourceBytes
        XCTAssertLessThanOrEqual(count, 128); XCTAssertLessThanOrEqual(bytes, 4_194_304)
    }
}
