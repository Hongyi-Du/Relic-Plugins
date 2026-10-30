import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class OutlineDrawTests: XCTestCase {
    func testRecordedDashPhaseIsUsedByTheActualNativeRaster() throws {
        let view = SurfacePaintProbe.SurfaceView(frame: NSRect(x: 0, y: 0, width: 22, height: 22))
        view.recordDraws = true
        var rasters: [Data] = []
        for phase in [CGFloat(0), CGFloat(3)] {
            view.configureOutline(SurfaceOutline(width: 1.5, color: .black, dash: [3, 3], phase: phase), corners: [6, 6, 6, 6])
            let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let receipt = try XCTUnwrap(view.lastOutlineDraw)
            XCTAssertEqual(receipt.phase, phase)
            XCTAssertEqual(receipt.revision, view.outlineRevision)
            XCTAssertEqual(receipt.path.boundingBoxOfPath.minX, 0.75, accuracy: 0.001)
            XCTAssertEqual(receipt.path.boundingBoxOfPath.maxX, 21.25, accuracy: 0.001)
            XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 11, y: 11))[3], 0,
                "An independent outline must not fill the avatar interior")
            XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0,
                "The actual rounded path must preserve its clear corner")
            rasters.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            XCTAssertTrue(view.outlineReceipt(in: view.bounds).paint is NSNull,
                "A unit bitmap is not proof of a mounted window's current outline")
            XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: receipt.raw))
        }
        XCTAssertNotEqual(rasters[0], rasters[1], "The receipt's changed phase must change the real native paint")
    }

    func testClearingOutlineDoesNotReuseTheEarlierDrawOrClaimOwnerAbsence() throws {
        let view = SurfacePaintProbe.SurfaceView(frame: NSRect(x: 0, y: 0, width: 22, height: 22))
        view.recordDraws = true
        view.configureOutline(SurfaceOutline(width: 1.5, color: .black, dash: [3, 3]), corners: [6, 6, 6, 6])
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let previous = try XCTUnwrap(view.lastOutlineDraw)
        view.configureOutline(nil, corners: [6, 6, 6, 6])
        XCTAssertGreaterThan(view.outlineRevision, previous.revision)
        let receipt = view.outlineReceipt(in: view.bounds)
        XCTAssertTrue(receipt.paint is NSNull)
        XCTAssertEqual(receipt.evidence["absence_proven"] as? Bool, false)
        XCTAssertEqual(view.lastOutlineDraw?.sequence, previous.sequence, "Retain earlier raw evidence without projecting it as current paint")
    }
}
