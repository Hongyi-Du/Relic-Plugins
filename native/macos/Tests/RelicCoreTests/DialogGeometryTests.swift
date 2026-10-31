import XCTest
@testable import RelicCore

final class DialogGeometryTests: XCTestCase {
    func testSettingsFitsEverySupportedWindowAndStaysCentered() {
        for size in [CGSize(width: 1440, height: 900), CGSize(width: 1280, height: 800), CGSize(width: 1024, height: 700)] {
            let layout = DialogGeometry(kind: "settings", window: size)
            XCTAssertEqual(layout.width, 920)
            XCTAssertEqual(layout.height, 640)
            XCTAssertGreaterThanOrEqual((size.width - layout.width) / 2, 20)
            XCTAssertGreaterThanOrEqual((size.height - layout.height!) / 2, 24)
        }
        let compact = DialogGeometry(kind: "settings", window: CGSize(width: 700, height: 500))
        XCTAssertEqual(compact.width, 660); XCTAssertEqual(compact.height, 452)
    }
    func testFormsGrowFromContentWhileLargeViewsUseTheWindow() {
        let window = CGSize(width: 1280, height: 800)
        XCTAssertNil(DialogGeometry(kind: "create", window: window).height)
        XCTAssertEqual(DialogGeometry(kind: "forward", window: window).width, 620)
        XCTAssertEqual(DialogGeometry(kind: "details", window: window).width, 1180)
        XCTAssertEqual(DialogGeometry(kind: "chart", window: window).width, 1240)
        XCTAssertEqual(DialogGeometry(kind: "chart", window: window).height, 744)
    }
    func testMemberCardClampsTheClickedAnchorToVisibleEdges() {
        let layout = DialogGeometry(kind: "card", window: CGSize(width: 1024, height: 700))
        XCTAssertEqual(layout.width, 340)
        XCTAssertEqual(layout.cardOrigin(anchor: CGRect(x: 10, y: 50, width: 100, height: 40)), CGPoint(x: 118, y: 38))
        XCTAssertEqual(layout.cardOrigin(anchor: CGRect(x: 1000, y: 680, width: 24, height: 20)), CGPoint(x: 668, y: 180))
    }
}
