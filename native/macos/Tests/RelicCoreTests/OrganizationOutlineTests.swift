import XCTest
@testable import RelicCore

final class OrganizationOutlineTests: XCTestCase {
    private let organizations = [Node(["id": "a", "name": "Root"]), Node(["id": "b", "parent": "a", "name": "Office"]), Node(["id": "c", "parent": "removed", "name": "Orphan"])]
    private let members = [Node(["name": "sec", "secretary": true]), Node(["name": "ana", "role": "Analyst"]), Node(["name": "dev", "role": "Developer"])]
    private func rows(_ folded: Set<String> = [], search: String = "", reveal: Bool = true) -> [OrganizationOutlineRow] {
        OrganizationOutline.rows(organizations: organizations, selected: "b", members: members, folded: folded,
            search: search, groupLabel: "Group chat", secretaryLabel: "Secretary", revealMembers: reveal)
    }
    func testEveryMemberIsAnIndependentStableRowInReferenceReadingOrder() {
        let result = rows()
        XCTAssertEqual(result.map(\.id), ["org/a", "org/b", "b/group", "b/secretary", "b/member/ana", "b/member/dev", "b/add", "org/c"])
        XCTAssertEqual(result[1].depth, 1); XCTAssertTrue(result[0].hasChildren)
        XCTAssertTrue(result[2].first); XCTAssertTrue(result[6].last)
        XCTAssertEqual(result.filter { $0.kind == .member }.map { $0.node["name"].text }, ["ana", "dev"])
        XCTAssertEqual(rows(reveal: false).map(\.id), ["org/a", "org/b", "org/c"])
    }
    func testFoldingAndSearchKeepDescendantsAndMemberMatchesReachable() {
        XCTAssertEqual(rows(["a"]).map(\.id), ["org/a", "org/c"])
        XCTAssertEqual(rows(["b"]).map(\.id), ["org/a", "org/b", "org/c"])
        XCTAssertEqual(rows(["a", "b"], search: "analyst").map(\.id), ["org/b", "b/member/ana", "b/add"])
        XCTAssertTrue(rows(search: "analyst")[1].first)
    }
    func testLargeOrganizationDoesNotBecomeASingleCompoundRow() {
        let people = (0..<42).map { Node(["name": "person-\($0)", "secretary": $0 == 0]) }
        let result = OrganizationOutline.rows(organizations: organizations, selected: "b", members: people, folded: [],
            search: "", groupLabel: "Group chat", secretaryLabel: "Secretary", revealMembers: true)
        XCTAssertEqual(result.count, 47)
        XCTAssertEqual(Set(result.map(\.id)).count, result.count)
        XCTAssertEqual(result.filter { $0.kind == .member }.count, 41)
    }
}
