import XCTest
@testable import RelicCore

final class RuleExampleTests: XCTestCase {
    func testExampleUsesCommandThenFileThenPathAndPreservesUnicode() {
        XCTAssertEqual(RuleExample.text(Node(["tool": "Bash", "input": ["command": "echo  你好\nworld", "file_path": "ignored"]])), "Bash echo 你好 world")
        XCTAssertEqual(RuleExample.text(Node(["tool": "Read", "input": ["file_path": "README.md", "path": "ignored"]])), "Read README.md")
        XCTAssertEqual(RuleExample.text(Node(["tool": "Glob", "input": ["path": "src/"]])), "Glob src/")
        XCTAssertEqual(RuleExample.text(Node(["tool": "Reply", "input": [:]])), "Reply")
    }
    func testExampleClipsWholeDisplayTo160UTF16Units() {
        let result = RuleExample.text(Node(["tool": "Bash", "input": ["command": String(repeating: "x", count: 200)]]))
        XCTAssertEqual((result as NSString).length, 160)
        XCTAssertTrue(result.hasSuffix("…"))
    }
}
