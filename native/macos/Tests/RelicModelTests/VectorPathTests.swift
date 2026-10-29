import XCTest
import CoreGraphics
@testable import Relic

final class VectorPathTests: XCTestCase {
    func testAllProductionIconAssetsParseIntoNonemptyFinitePaths() throws {
        XCTAssertEqual(ReferenceIcons.paths.count, 41)
        for (name, source) in ReferenceIcons.paths {
            let path = try VectorPath.parse(source), box = path.boundingBoxOfPath
            XCTAssertFalse(path.isEmpty, name)
            XCTAssertTrue(box.minX.isFinite && box.minY.isFinite && box.maxX.isFinite && box.maxY.isFinite, name)
        }
    }
    func testCircularArcsRetainTheSpecifiedBounds() throws {
        let path = try VectorPath.parse("M10 0a10 10 0 1 0 0 20 10 10 0 0 0 0-20z")
        let bounds = path.boundingBoxOfPath
        XCTAssertEqual(bounds.minX, 0, accuracy: 0.001); XCTAssertEqual(bounds.minY, 0, accuracy: 0.001)
        XCTAssertEqual(bounds.width, 20, accuracy: 0.001); XCTAssertEqual(bounds.height, 20, accuracy: 0.001)
    }
    func testRelativeMoveAndReflectedCubicControlRetainTheirEndpoints() throws {
        let path = try VectorPath.parse("M1 2c1 0 2 3 4 5s2 1 3 2m2-1l1 1")
        XCTAssertEqual(path.currentPoint, CGPoint(x: 11, y: 9))
        XCTAssertThrowsError(try VectorPath.parse("M1"))
        XCTAssertThrowsError(try VectorPath.parse("M0 0R2 3"))
    }
    func testChartEdgesPreserveZeroWidthAndActualCubicExtrema() throws {
        let vertical = try VectorPath.parse("M142,104V127H142V150")
        XCTAssertEqual(vertical.boundingBoxOfPath, CGRect(x: 142, y: 104, width: 0, height: 46))
        XCTAssertFalse(vertical.isEmpty)
        let shared = try VectorPath.parse("M260,190C292,190 292,316 260,316")
        XCTAssertEqual(shared.boundingBoxOfPath.minX, 260, accuracy: 0.001)
        XCTAssertEqual(shared.boundingBoxOfPath.width, 24, accuracy: 0.001)
        XCTAssertEqual(shared.boundingBoxOfPath.height, 126, accuracy: 0.001)
    }
}
