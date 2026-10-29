import XCTest
@testable import RelicCore

final class ReferenceTextTests: XCTestCase {
    func testNameInputLimitPreservesWhitespaceAndCompleteUnicodeScalars() {
        XCTAssertEqual(ReferenceText.inputPrefix("  名字  ", utf16Limit: 40), "  名字  ")
        XCTAssertEqual(ReferenceText.inputPrefix("abc😀def", utf16Limit: 4), "abc")
        XCTAssertEqual(ReferenceText.inputPrefix("abc😀def", utf16Limit: 5), "abc😀")
        XCTAssertEqual(ReferenceText.inputPrefix("e\u{301}abc", utf16Limit: 2), "e\u{301}")
        XCTAssertEqual(ReferenceText.inputPrefix("name", utf16Limit: 0), "")
    }
    func testClipNormalizesWhitespaceBeforeApplyingTheReferenceUTF16Limit() {
        XCTAssertEqual(ReferenceText.clip("  one\n two\tthree  ", to: 20), "one two three")
        XCTAssertEqual(ReferenceText.clip("one two three", to: 8), "one two…")
        XCTAssertEqual(ReferenceText.clip("一二三四五", to: 4), "一二三…")
        XCTAssertEqual(ReferenceText.clip("😀12345", to: 5), "😀12…")
    }
}
