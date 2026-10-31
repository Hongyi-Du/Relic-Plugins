import XCTest
import AppKit
import RelicCore
import RelicAX
@testable import Relic

@MainActor final class MentionTests: XCTestCase {
    func testComposerMeasurementReflowsAfterEditingResizingAndTextScaleChanges() {
        let measurement = ComposerTextMeasurement()
        let font = NSFont.systemFont(ofSize: 14)
        let paragraph = NSMutableParagraphStyle()
        paragraph.minimumLineHeight = 22; paragraph.maximumLineHeight = 22
        let short = measurement.height(text: "Draft", font: font, paragraph: paragraph, width: 240)
        let draft = String(repeating: "Draft with long text and 中文. ", count: 24)
        let narrow = measurement.height(text: draft, font: font, paragraph: paragraph, width: 240)
        let wide = measurement.height(text: draft, font: font, paragraph: paragraph, width: 720)
        XCTAssertGreaterThan(narrow, short * 5)
        XCTAssertLessThan(wide, narrow)
        XCTAssertEqual(measurement.height(text: draft, font: font, paragraph: paragraph, width: 240), narrow)
        // Mutating the caller's paragraph style must invalidate measurements;
        // retaining its mutable reference would incorrectly compare it to itself.
        paragraph.minimumLineHeight = 32; paragraph.maximumLineHeight = 32
        let scaled = measurement.height(text: draft, font: .systemFont(ofSize: 20), paragraph: paragraph, width: 240)
        XCTAssertGreaterThan(scaled, narrow)
        paragraph.minimumLineHeight = 22; paragraph.maximumLineHeight = 22
        XCTAssertEqual(measurement.height(text: "Draft", font: font, paragraph: paragraph, width: 240), short)
    }

    func testComposerDocumentTracksTheActualViewportAcrossWindowSizes() throws {
        let scroll = ComposerScrollView()
        scroll.hasHorizontalScroller = false; scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true
        let editor = ComposerTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 50))
        editor.isHorizontallyResizable = false; editor.minSize.width = 0; editor.autoresizingMask = []
        editor.textContainer?.widthTracksTextView = true
        editor.string = "A draft with @engineer that must survive resize"
        editor.setSelectedRange(NSRange(location: 8, length: 0))
        let original = editor.string
        scroll.documentView = editor
        XCTAssertFalse(scroll.isAccessibilityElement(), "The unpainted clip wrapper is not a second named field")
        XCTAssertTrue(editor.isAccessibilityElement())
        XCTAssertEqual(RelicAXRead(editor)["role"] as? String, "AXTextArea")
        for width in [758.0, 598, 342, 758] {
            scroll.setFrameSize(NSSize(width: width, height: 50))
            scroll.layoutSubtreeIfNeeded()
            XCTAssertEqual(editor.frame.width, scroll.contentView.bounds.width, accuracy: 0.01)
            XCTAssertLessThanOrEqual(editor.frame.maxX, scroll.contentView.bounds.maxX + 0.01,
                                     "The editor must not keep its initial 400px in addition to the viewport")
            XCTAssertEqual(editor.string, original)
            XCTAssertEqual(editor.selectedRange(), NSRange(location: 8, length: 0))
        }
    }

    func testCompletionUsesPrefixAndWrapsKeyboardSelection() {
        let editor = ComposerTextView()
        editor.members = [Node(["name": "engineer", "display": "Engineer"]), Node(["name": "reviewer", "display": "Engineering review"])]
        editor.string = "@gine"; editor.setSelectedRange(NSRange(location: 5, length: 0))
        XCTAssertTrue(editor.mentionCandidates().isEmpty)
        editor.string = "@eng"; editor.setSelectedRange(NSRange(location: 4, length: 0))
        XCTAssertEqual(editor.mentionCandidates().count, 2)
        XCTAssertEqual(ComposerTextView.nextSuggestion(0, direction: -1, count: 5), 4)
        XCTAssertEqual(ComposerTextView.nextSuggestion(4, direction: 1, count: 5), 0)
        XCTAssertEqual(ComposerTextView.nextSuggestion(0, direction: 1, count: 0), 0)
    }
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
