import XCTest
import Foundation
@testable import RelicCore

final class NodeAccessTests: XCTestCase {
    func testFoundationJSONAndSwiftValuesKeepNestedFieldAndArraySemantics() throws {
        let source = #"{"org":{"id":"a","name":"秘书处"},"members":[{"name":"秘书","n":42,"active":true}],"empty":null}"#
        let foundation = try JSONSerialization.jsonObject(with: Data(source.utf8))
        for raw in [foundation, foundation as! [String: Any]] {
            let node = Node(raw)
            XCTAssertEqual(node["org"]["name"].text, "秘书处")
            XCTAssertEqual(node["members"].rows.first?["n"].integer, 42)
            XCTAssertTrue(node["members"].rows.first?["active"].flag == true)
            XCTAssertTrue(node["empty"].isNull); XCTAssertTrue(node["missing"]["nested"].isNull)
            XCTAssertTrue(node["members"]["not-an-index"].isNull)
            XCTAssertEqual(node.object.count, 3)
        }
    }

    func testWordListLoadsOnceAndKeepsPluralArgumentsShortcutsAndLanguageReplacement() throws {
        let source = #"{"lang":"en-US","strings":{"n":{"one":"{n} item","other":"{n} items"},"copy":"Copy {text} (Ctrl+C)"}}"#
        var words = Words()
        words.load(Node(try JSONSerialization.jsonObject(with: Data(source.utf8))))
        for _ in 0..<1000 {
            XCTAssertEqual(words.t("n", ["n": "1"]), "1 item")
            XCTAssertEqual(words.t("n", ["n": "2"]), "2 items")
            XCTAssertEqual(words.t("copy", ["text": "Ctrl+literal"]), "Copy Ctrl+literal (Cmd+C)")
        }
        words.load(Node(["lang": "zh-CN", "strings": ["n": ["one": "unused", "other": "{n} 项"]]]))
        XCTAssertEqual(words.t("n", ["n": "1"]), "1 项")
        XCTAssertEqual(words.t("copy"), ""); XCTAssertEqual(words.t("missing"), "")
    }
}
