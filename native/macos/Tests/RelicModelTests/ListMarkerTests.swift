import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ListMarkerTests: XCTestCase {
    func testOwnedDiscImagePreservesMountedPixelsAtFractionalOriginsInBothThemes() throws {
        _ = NSApplication.shared
        func marker(in root: NSView) -> NativeListMarkerView? {
            if let marker = root as? NativeListMarkerView { return marker }
            return root.subviews.lazy.compactMap { marker(in: $0) }.first
        }
        let metrics = NativeListMarkerMetrics(font: RelicStyle.nativeFont(13.5, weight: 400))
        for dark in [false, true] { for fraction in [0.0, 0.25, 0.5, 0.75] {
            var images: [Data] = []
            for owned in [false, true] {
                let root = ZStack(alignment: .topLeading) {
                    Color.clear
                    NativeListMarker(size: 13.5, ownedLayer: owned)
                        .frame(width: metrics.width, height: metrics.height).offset(x: 12 + fraction, y: 10 + fraction)
                }.frame(width: 40, height: 42).environment(\.colorScheme, dark ? .dark : .light)
                let host = NSHostingView(rootView: root); host.frame = NSRect(x: 0, y: 0, width: 40, height: 42)
                let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
                window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
                defer { window.orderOut(nil); window.contentView = nil; window.close() }
                host.layoutSubtreeIfNeeded()
                let actual = try XCTUnwrap(marker(in: host)); actual.recordDraws = true
                actual.needsDisplay = true; actual.layer?.setNeedsDisplay()
                host.displayIfNeeded(); CATransaction.flush()
                let bitmap = try XCTUnwrap(CaptureRaster.forView(host)); host.cacheDisplay(in: host.bounds, to: bitmap)
                images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
                if owned {
                    let evidence = actual.backingPaintObservation()
                    XCTAssertEqual(evidence["current"] as? Bool, true)
                    XCTAssertTrue((actual.layer?.sublayers ?? []).isEmpty)
                    XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: evidence))
                    actual.configure(font: RelicStyle.nativeFont(13.5, weight: 400), color: .red, region: "window")
                    XCTAssertEqual(actual.backingPaintObservation()["current"] as? Bool, false)
                }
            }
            if images[0] != images[1] {
                let directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
                    .deletingLastPathComponent().appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                for index in images.indices {
                    try images[index].write(to: directory.appendingPathComponent("disc-owned-\(dark)-\(fraction)-\(index).png"))
                }
            }
            XCTAssertEqual(images[0], images[1], "The actual circle image must preserve the existing native pixels at \(fraction), dark=\(dark)")
        } }
    }
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
        let basis = try XCTUnwrap(view.observation()["content_screen_frame"] as? [String: Any])
        XCTAssertEqual(basis["window_identity"] as? String, String(describing: ObjectIdentifier(window)))
        XCTAssertEqual(ElementCapture.rect(basis["bounds"]), window.convertToScreen(view.convert(view.bounds, to: nil)))
        view.configure(font: font, color: .red, region: "right-pane")
        XCTAssertTrue(view.observation()["current_draw"] is NSNull, "A changed marker paint must not reuse the earlier draw")
    }
}
