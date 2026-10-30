import XCTest
@testable import Relic

final class ElementOwnershipTests: XCTestCase {
    func testMeasuredNativeAncestryOrdersIgnoredAvatarAndDotInsideTheirActualRow() {
        func measured(_ id: String, _ path: [Int], parent: String = "row-owner") -> [String: Any] {
            ["id": id, "native_structure": ["parent_identifier": parent, "native_subview_path": path]]
        }
        var nodes: [[String: Any]] = [
            ["id": "row", "identifier": "row-owner"], measured("title", [0, 12]),
            ["id": "following-row"], measured("dot", [0, 9]),
            measured("avatar", [0, 8]), ["id": "avatar-icon", "parent": "avatar"],
            measured("time", [0, 13])]
        XCTAssertTrue(ElementOwnership.attachMeasuredChildren(to: &nodes).isEmpty)
        XCTAssertEqual(nodes.compactMap { $0["id"] as? String }, ["row", "avatar", "avatar-icon", "dot", "title", "time", "following-row"])
        XCTAssertEqual(nodes[3]["parent"] as? String, "row")
        XCTAssertEqual(nodes[2]["parent"] as? String, "avatar")
    }
    func testUnknownNativeParentDoesNotGuessFromTextOrGeometry() {
        var nodes: [[String: Any]] = [["id": "before"],
            ["id": "unowned", "native_structure": ["parent_identifier": "missing", "native_subview_path": [0, 1]]],
            ["id": "after"]]
        XCTAssertEqual(ElementOwnership.attachMeasuredChildren(to: &nodes).count, 1)
        XCTAssertEqual(nodes.compactMap { $0["id"] as? String }, ["before", "unowned", "after"])
        XCTAssertNil(nodes[1]["parent"])
    }
    // Regression: SwiftUI exposes a row Button but ignores its nested avatar;
    // the real TextKit label arrives before the separately measured surface.
    func testLaterPaintSurfaceOwnsItsActualLabelWithoutDiscardingRawEvidence() {
        let label: [String: Any] = ["id": "actual-label", "production_owner": "relic-avatar/live-1", "text": "H",
            "style": ["fontSize": 12, "fontWeight": 600, "color": [27, 27, 26, 255]],
            "layout": ["line_count": 1], "text_bounds": [["x": 25.4, "y": 857.0, "width": 9.2, "height": 19.2]]]
        let surface: [String: Any] = ["id": "actual-surface", "identifier": "relic-avatar/live-1", "kind": "avatar", "name": "",
            "text": "", "style": ["backgroundColor": [27, 27, 26, 255], "borderRadius": 8]]
        var nodes = [label, surface]
        XCTAssertTrue(ElementOwnership.attachLabels(to: &nodes).isEmpty)
        XCTAssertEqual(nodes.count, 1)
        XCTAssertEqual(nodes[0]["text"] as? String, "H")
        XCTAssertEqual(nodes[0]["name"] as? String, "", "An ignored paint surface must not acquire an invented AX name")
        XCTAssertEqual((nodes[0]["style"] as? [String: Any])?["borderRadius"] as? Int, 8)
        XCTAssertEqual((nodes[0]["owned_text_evidence"] as? [String: Any])?["id"] as? String, "actual-label")
    }
    func testUnknownOrAmbiguousOwnersRetainLabelsAndTheirOriginalOrder() {
        for count in [0, 2] {
            var nodes: [[String: Any]] = [["id": "before"], ["id": "label", "production_owner": "relic-badge/live", "text": "1"], ["id": "after"]]
            nodes += (0..<count).map { ["id": "surface-\($0)", "identifier": "relic-badge/live"] }
            let before = nodes.compactMap { $0["id"] as? String }
            XCTAssertEqual(ElementOwnership.attachLabels(to: &nodes).count, 1)
            XCTAssertEqual(nodes.compactMap { $0["id"] as? String }, before)
        }
    }
    func testCompoundRowKeepsDistinctLabelsInMeasuredOrder() {
        var nodes: [[String: Any]] = [["id": "row", "identifier": "relic-list-row/live"],
            ["id": "name", "production_owner": "relic-list-row/live", "text": "Designer"],
            ["id": "time", "production_owner": "relic-list-row/live", "text": "11:00"]]
        XCTAssertTrue(ElementOwnership.attachLabels(to: &nodes).isEmpty)
        XCTAssertEqual(nodes.compactMap { $0["id"] as? String }, ["row", "name", "time"])
        XCTAssertEqual(nodes[1]["parent"] as? String, "row")
        XCTAssertEqual(nodes[2]["parent"] as? String, "row")
    }
}
