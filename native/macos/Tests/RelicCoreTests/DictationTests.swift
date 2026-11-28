import Foundation
import XCTest
@testable import RelicCore

final class DictationTests: XCTestCase {
    func testDictationReplacesSelectionAndInterimResultsWithUTF16Caret() {
        let original = "🙂旧词，保留尾部"
        let selected = (original as NSString).range(of: "旧词")
        let insertion = DictationInsertion(text: original, selection: selected)
        XCTAssertEqual(insertion.applying("新").text, "🙂新，保留尾部")
        let final = insertion.applying("新的话🎤")
        XCTAssertEqual(final.text, "🙂新的话🎤，保留尾部")
        XCTAssertEqual(final.caret, ("🙂新的话🎤" as NSString).length)
    }
    func testDictationUsesCursorAndFallsBackToEndWithoutAddedSpace() {
        let insertion = DictationInsertion(text: "前后", selection: NSRange(location: 1, length: 0))
        XCTAssertEqual(insertion.applying("中").text, "前中后")
        XCTAssertEqual(insertion.applying("中").caret, 2)
        for range in [nil, NSRange(location: NSNotFound, length: 0), NSRange(location: 0, length: 99)] as [NSRange?] {
            XCTAssertEqual(DictationInsertion(text: "原文", selection: range).applying("继续").text, "原文继续")
        }
    }
}
