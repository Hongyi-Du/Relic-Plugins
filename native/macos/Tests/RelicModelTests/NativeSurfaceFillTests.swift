import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class NativeSurfaceFillTests: XCTestCase {
    func testActualNativeFillRetainsItsCurrentPathColorAndWindowBinding() throws {
        _ = NSApplication.shared
        let view = NativeSurfaceFillView(frame: NSRect(x: 0, y: 0, width: 160, height: 84))
        view.configure(color: .white, corners: [16,16,16,16], owner: "panel", region: "dialog")
        view.recordDraws = true
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 80, y: 42)), [255,255,255,255])
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0)
        XCTAssertFalse(try XCTUnwrap(view.lastDraw?["local_path"] as? String).isEmpty)
        XCTAssertTrue(view.observation()["current_draw"] is NSNull)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view; window.orderFront(nil); defer { window.orderOut(nil) }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let observation = view.observation()
        XCTAssertNotNil(observation["current_draw"] as? [String: Any])
        XCTAssertEqual(observation["occlusion_proven"] as? Bool, false)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: observation))
        view.configure(color: .black, corners: [16,16,16,16], owner: "panel", region: "dialog")
        XCTAssertTrue(view.observation()["current_draw"] is NSNull)
    }

    func testNativeFillCandidatePreservesTheExistingSurfaceBitmap() throws {
        _ = NSApplication.shared
        for (index, radius) in [CGFloat(0), 8, 16].enumerated() {
            var images: [Data] = []
            for native in [false, true] {
                let root = Color.clear.frame(width: 160, height: 84)
                    .modifier(RecordedSurface(background: Color(red: 0.93, green: 0.91, blue: 0.88),
                        border: .black.opacity(0.2), borderWidth: 1, radius: radius, nativeFill: native))
                let host = NSHostingView(rootView: root)
                host.frame = NSRect(x: 0, y: 0, width: 160, height: 84)
                let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                window.contentView = host; window.orderFront(nil)
                host.layoutSubtreeIfNeeded(); host.display(); CATransaction.flush()
                let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
                host.cacheDisplay(in: host.bounds, to: bitmap)
                images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
                XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 80, y: 42))[3], 255)
                window.orderOut(nil)
            }
            if images[0] != images[1] {
                let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try images[0].write(to: directory.appendingPathComponent("surface-\(index)-swiftui.png"))
                try images[1].write(to: directory.appendingPathComponent("surface-\(index)-native.png"))
            }
            XCTAssertEqual(images[0], images[1], "The measured fill must preserve the production background pixels")
        }
    }
}
