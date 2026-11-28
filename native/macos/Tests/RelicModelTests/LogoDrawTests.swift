import XCTest
import AppKit
@testable import Relic

@MainActor final class LogoDrawTests: XCTestCase {
    func testImageReceiptComesFromTheActualNativeDrawAndRetainsLayerOrder() throws {
        let view = NativeLogoView(frame: NSRect(x: 0, y: 0, width: 64, height: 64))
        view.recordDraws = true
        XCTAssertNil(view.lastDraw)
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let receipt = try XCTUnwrap(view.lastDraw)
        let paint = try XCTUnwrap(receipt["paint"] as? [String: Any])
        XCTAssertEqual(paint["source"] as? String, "vector-image-v1")
        let glyph = try XCTUnwrap(paint["glyph"] as? [String: Any])
        let layers = try XCTUnwrap(glyph["layers"] as? [[String: Any]])
        XCTAssertEqual(layers.compactMap { $0["kind"] as? String }, ["rounded-rect", "path", "circle"])
        let gradient = try XCTUnwrap(layers[0]["fill"] as? [String: Any])
        let stops = try XCTUnwrap(gradient["stops"] as? [[String: Any]])
        XCTAssertEqual(stops.compactMap { ($0["offset"] as? NSNumber)?.doubleValue }, [0, 1])
        XCTAssertEqual(gradient["spread"] as? String, "pad")
        XCTAssertFalse(try XCTUnwrap(receipt["parsed_path_elements"] as? [[String: Any]]).isEmpty)
        XCTAssertEqual(receipt["presentation_identity_proven"] as? Bool, false)
        XCTAssertNil(view.currentPaint(), "An offscreen unit-test bitmap is not a current mounted-window binding")
        let white = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 23, y: 23))
        for channel in 0..<4 { XCTAssertEqual(white[channel], 255, accuracy: 1) }
        let orange = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 47, y: 46))
        for (channel, expected) in [217.0, 119, 87, 255].enumerated() {
            XCTAssertEqual(orange[channel], expected, accuracy: 1, "Actual circle pixels must retain image orientation and fill")
        }
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: receipt))
    }
}
