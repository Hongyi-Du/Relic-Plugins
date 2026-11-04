import XCTest
@testable import RelicCore

final class FilePresentationTests: XCTestCase {
    func testBinaryUnitBoundariesAndDecimalPrecisionMatchFileMetadata() {
        XCTAssertEqual(FilePresentation.size(0), "0 B")
        XCTAssertEqual(FilePresentation.size(1023), "1023 B")
        XCTAssertEqual(FilePresentation.size(1024), "1.0 KB")
        XCTAssertEqual(FilePresentation.size(1536), "1.5 KB")
        XCTAssertEqual(FilePresentation.size(1_048_575), "1024.0 KB")
        XCTAssertEqual(FilePresentation.size(1_048_576), "1.0 MB")
    }
    func testRelativePathsUseWholeDirectoryBoundariesAndBothSeparators() {
        XCTAssertEqual(FilePresentation.relative("S:\\Work\\src\\App.swift", root: "s:/work/"), "src/App.swift")
        XCTAssertEqual(FilePresentation.relative("/workspace-other/readme", root: "/workspace"), "/workspace-other/readme")
        XCTAssertEqual(FilePresentation.name("S:\\Work\\README.md"), "README.md")
        XCTAssertEqual(FilePresentation.status("??"), "U")
        XCTAssertEqual(FilePresentation.status(" M"), " ")
    }
    func testCodePreservesEmptyFinalLineAndNormalizesLineEndings() {
        XCTAssertEqual(FilePresentation.lines("a\r\nb\rc\n"), ["a", "b", "c", ""])
        XCTAssertEqual(FilePresentation.lines(""), [""])
    }
}
