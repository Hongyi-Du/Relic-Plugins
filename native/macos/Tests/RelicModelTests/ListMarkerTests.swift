import XCTest
import AppKit
@testable import Relic

@MainActor final class ListMarkerTests: XCTestCase {
    func testNativeDiscUsesFontMetricsAndPaintsItsCircleInsteadOfABulletGlyph() throws {
        _ = NSApplication.shared
        let font = RelicStyle.nativeFont(13.5, weight: 400)
        let metrics = NativeListMarkerMetrics(font: font)
        XCTAssertEqual(metrics.width, 7)
        XCTAssertEqual(metrics.height, 19)
        XCTAssertEqual(metrics.distanceBeforeText, 17)
        let view = NativeListMarkerView(frame: NSRect(x: 0, y: 0, width: metrics.width, height: metrics.height))
        view.configure(font: font, color: .black, region: "right-pane")
        view.recordDraws = true
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let draw = try XCTUnwrap(view.lastDraw)
        XCTAssertEqual(draw["symbol"] as? String, "disc")
        XCTAssertEqual(draw["alternative_text"] as? String, "• ")
        XCTAssertEqual(ElementCapture.rect(draw["local_ellipse"]), NSRect(x: 1, y: 7, width: 5, height: 5))
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 3, y: 9))[3], 255)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 9))[3], 0)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 3, y: 6))[3], 0)
        XCTAssertTrue(view.observation()["current_draw"] is NSNull, "A detached bitmap is not a mounted capture")
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: draw))
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view; window.orderFront(nil); defer { window.orderOut(nil) }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        XCTAssertNotNil(view.observation()["current_draw"] as? [String: Any])
        view.configure(font: font, color: .red, region: "right-pane")
        XCTAssertTrue(view.observation()["current_draw"] is NSNull, "A changed marker paint must not reuse the earlier draw")
    }
}
