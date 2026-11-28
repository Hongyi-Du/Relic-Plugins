import XCTest
@testable import RelicCore

final class OverviewOutlineTests: XCTestCase {
    func testLargeCollectionsRemainIndividualRowsWithoutDroppingContent() {
        let snapshot = Node([
            "members": (0..<42).map { ["name": "person-\($0)"] },
            "decisions": (0..<100).map { ["id": "decision-\($0)"] },
            "protocols": (0..<40).map { ["id": "p-\($0)", "status": "active"] },
            "inherited_protocols": [["id": "p-0"]], "replaced_protocols": [["id": "p-0"]]
        ])
        let rows = OverviewOutline.rows(snapshot: snapshot, liaison: false)
        XCTAssertEqual(rows.filter { $0.kind == "member" }.count, 42)
        XCTAssertEqual(rows.filter { $0.kind == "decision" }.count, 100)
        XCTAssertEqual(rows.filter { $0.kind == "protocol" }.count, 42)
        XCTAssertEqual(Set(rows.map(\.id)).count, rows.count)
        let people = rows.filter { $0.id.hasPrefix("people/") }
        XCTAssertTrue(people.first!.first); XCTAssertTrue(people.last!.last)
        XCTAssertEqual(people.filter(\.first).count, 1); XCTAssertEqual(people.filter(\.last).count, 1)
        XCTAssertEqual(people.dropFirst().map { $0.node["name"].text }, (0..<42).map { "person-\($0)" })
    }
    func testTaskAndEpisodeLimitsPreserveReferenceOrderAndNavigation() {
        let snapshot = Node([
            "tasks": (0..<12).map { ["id": "open-\($0)", "status": "working"] } +
                (0..<5).map { ["id": "done-\($0)", "status": "done", "report": "Complete", "done_at": "2026-10-\(20 + $0)"] },
            "episodes": (0..<5).map { ["id": "closed-\($0)", "status": "closed"] } + [["id": "live", "status": "open"]]
        ])
        let rows = OverviewOutline.rows(snapshot: snapshot, liaison: false)
        XCTAssertEqual(rows.filter { $0.kind == "task" && $0.source.isEmpty }.map { $0.node["id"].text }, (0..<8).map { "open-\($0)" })
        XCTAssertEqual(rows.filter { $0.kind == "more-tasks" }.count, 1)
        XCTAssertEqual(rows.filter { $0.kind == "task" && $0.source == "report" }.map { $0.node["id"].text }, ["done-4", "done-3", "done-2"])
        XCTAssertEqual(rows.filter { $0.kind == "episode" }.map { $0.node["id"].text }, ["live", "closed-4", "closed-3", "closed-2"])
        let liaison = OverviewOutline.rows(snapshot: snapshot, liaison: true)
        XCTAssertFalse(liaison.contains { ["member", "protocol", "episode"].contains($0.kind) })
        XCTAssertEqual(liaison.suffix(2).map(\.source), ["org.liaison_note", ""])
    }
}
