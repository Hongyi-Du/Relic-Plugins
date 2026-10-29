import XCTest
@testable import RelicCore

final class InspectorGeometryTests: XCTestCase {
    func testNarrowWindowsKeepConversationWidthAndOverlayTheInspector() {
        XCTAssertTrue(InspectorGeometry.overlaysConversation(window: 1024))
        XCTAssertTrue(InspectorGeometry.overlaysConversation(window: 1180))
        XCTAssertFalse(InspectorGeometry.overlaysConversation(window: 1181))
        XCTAssertFalse(InspectorGeometry.overlaysConversation(window: 1280))
    }
    func testRestoresInspectorAndFileWidthsWithoutNativeSplitViewMinimums() {
        XCTAssertEqual(InspectorGeometry.width(window: 1440, saved: 340, files: false), 340)
        XCTAssertEqual(InspectorGeometry.width(window: 1024, saved: 520, files: true), 520)
        XCTAssertEqual(InspectorGeometry.width(window: 1440, saved: 0, files: false), 320)
        XCTAssertEqual(InspectorGeometry.width(window: 1440, saved: 0, files: true), 520)
    }
    func testDragIsClampedToReferenceViewportBounds() {
        XCTAssertEqual(InspectorGeometry.width(window: 1024, saved: 900, files: false), 614)
        XCTAssertEqual(InspectorGeometry.width(window: 1440, saved: 100, files: false), 280)
        XCTAssertEqual(InspectorGeometry.width(window: 1440, saved: .infinity, files: false), 320)
    }
}
