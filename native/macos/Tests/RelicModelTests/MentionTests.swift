import XCTest
import AppKit
import RelicCore
@testable import Relic

@MainActor final class MentionTests: XCTestCase {
    func testMentionAtUTF16CaretReplacesOnlyQueryAndSelectsRecipient() {
        let editor = ComposerTextView()
        editor.string = "检查 ✅ @工 后续文字"
        let prefix = "检查 ✅ @工"
        editor.setSelectedRange(NSRange(location: (prefix as NSString).length, length: 0))
        var recipient = ""
        editor.onMention = { recipient = $0 }
        editor.acceptMention(Node(["name": "engineer", "display": "工程师"]))
        XCTAssertEqual(editor.string, "检查 ✅ @工程师  后续文字")
        XCTAssertEqual(recipient, "engineer")
        XCTAssertEqual(editor.selectedRange().location, ("检查 ✅ @工程师 " as NSString).length)
    }

    func testClosedQueryDoesNotReplaceTextOrDispatchRecipient() {
        let editor = ComposerTextView()
        editor.string = "@engineer completed"
        editor.setSelectedRange(NSRange(location: (editor.string as NSString).length, length: 0))
        var selected = false
        editor.onMention = { _ in selected = true }
        editor.acceptMention(Node(["name": "engineer", "display": "Engineer"]))
        XCTAssertEqual(editor.string, "@engineer completed")
        XCTAssertFalse(selected)
        XCTAssertEqual(editor.rangeForUserCompletion.location, NSNotFound)
    }
}
