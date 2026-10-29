import XCTest
import AppKit
import RelicCore
@testable import Relic

@MainActor final class MentionTests: XCTestCase {
    func testMentionAnchorStaysInTextCoordinatesAfterMovingEditor() {
        let editor = ComposerTextView(frame: NSRect(x: 400, y: 500, width: 600, height: 100))
        editor.font = .systemFont(ofSize: 14)
        editor.textContainerInset = NSSize(width: 6, height: 6)
        editor.string = "@"; editor.setSelectedRange(NSRange(location: 1, length: 0))
        let first = editor.mentionAnchorRect()
        XCTAssertGreaterThan(first.width, 0)
        XCTAssertLessThan(first.maxX, 50)
        XCTAssertLessThan(first.maxY, 40)
        editor.setFrameOrigin(NSPoint(x: 800, y: 900))
        XCTAssertEqual(editor.mentionAnchorRect(), first)
        editor.string = "前一行\n@工"; editor.setSelectedRange(NSRange(location: (editor.string as NSString).length, length: 0))
        let second = editor.mentionAnchorRect()
        XCTAssertGreaterThan(second.minY, first.minY)
        XCTAssertEqual(second.minX, first.minX, accuracy: 1)
    }

    func testBareAtOffersMembersAndQueryMatchesDisplayOrSeatName() {
        let editor = ComposerTextView()
        editor.members = [Node(["name": "engineer", "display": "工程师"]), Node(["name": "designer", "display": "设计师"])]
        editor.string = "@"; editor.setSelectedRange(NSRange(location: 1, length: 0))
        XCTAssertEqual(editor.mentionCandidates().map { $0["name"].text }, ["engineer", "designer"])
        editor.string = "@工程"; editor.setSelectedRange(NSRange(location: 3, length: 0))
        XCTAssertEqual(editor.mentionCandidates().map { $0["name"].text }, ["engineer"])
        editor.string = "@DES"; editor.setSelectedRange(NSRange(location: 4, length: 0))
        XCTAssertEqual(editor.mentionCandidates().map { $0["name"].text }, ["designer"])
    }

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
