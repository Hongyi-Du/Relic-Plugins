import XCTest
@testable import RelicCore

final class ReferenceTextTests: XCTestCase {
    func testClipNormalizesWhitespaceBeforeApplyingTheReferenceUTF16Limit() {
        XCTAssertEqual(ReferenceText.clip("  one\n two\tthree  ", to: 20), "one two three")
        XCTAssertEqual(ReferenceText.clip("one two three", to: 8), "one two…")
        XCTAssertEqual(ReferenceText.clip("一二三四五", to: 4), "一二三…")
        XCTAssertEqual(ReferenceText.clip("😀12345", to: 5), "😀12…")
    }
}
