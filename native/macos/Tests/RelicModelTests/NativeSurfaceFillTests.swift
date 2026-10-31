import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class NativeSurfaceFillTests: XCTestCase {
    func testOriginalDialogFillDrawsIntoTheActualCaptureBitmap() throws {
        _ = NSApplication.shared
        let directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let root = Color.clear.frame(width: 160, height: 84)
            .modifier(RecordedSurface(background: Color(red: 0.93, green: 0.91, blue: 0.88),
                border: .black.opacity(0.2), borderWidth: 1, radius: 16,
                shadows: SurfaceShadow.dialog, nativeFill: true)).padding(56)
        let host = NSHostingView(rootView: root)
        host.frame = NSRect(x: 0, y: 0, width: 272, height: 196)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        host.layoutSubtreeIfNeeded()
        let actual = try XCTUnwrap(NativeSurfaceFill.mountedViews(in: window).first)
        actual.recordDraws = true; actual.needsDisplay = true; actual.layer?.setNeedsDisplay()
        host.displayIfNeeded(); CATransaction.flush()
        let original = try XCTUnwrap(CaptureRaster.forView(host))
        host.cacheDisplay(in: host.bounds, to: original)
        let baseline = try XCTUnwrap(original.representation(using: .png, properties: [:]))
        let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
        let record = CaptureRaster.cache(host, into: bitmap)
        let buffer = try XCTUnwrap(bitmap.bitmapData)
        let expected = "0x" + String(UInt(bitPattern: UnsafeMutableRawPointer(buffer)), radix: 16)
        let observed = (actual.lastDraw?["context_bitmap"] as? [String: Any])?["data_address"] as? String
        let bindings = try XCTUnwrap(record["native_fill_destinations"] as? [[String: Any]])
        XCTAssertEqual(bindings.count, 1)
        XCTAssertEqual(bindings.first?["draw_destination_bound"] as? Bool, true)
        XCTAssertEqual(bindings.first?["final_png_attribution_proven"] as? Bool, false)
        XCTAssertEqual(bindings.first?["occlusion_proven"] as? Bool, false)
        XCTAssertEqual(observed, expected, "Bind the original fill to the actual destination, without a new rendering path")
        XCTAssertEqual(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])), baseline,
            "Observing the current draw destination must retain the complete original PNG bytes")
        try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
            .write(to: directory.appendingPathComponent("dialog-original-draw-buffer.json"))
    }
    func testOwnedFillImageRetainsTheHostedFillAndShadowPixels() throws {
        _ = NSApplication.shared
        func fill(in view: NSView) -> NativeSurfaceFillView? {
            if let fill = view as? NativeSurfaceFillView { return fill }
            return view.subviews.lazy.compactMap { fill(in: $0) }.first
        }
        let fixtures: [(Color, [CGFloat])] = [(.white, [16,16,16,16]),
            (Color(red: 0.12, green: 0.11, blue: 0.10), [8,16,4,12]), (.black.opacity(0.32), [0,0,0,0])]
        for (index, fixture) in fixtures.enumerated() {
            var images: [Data] = []
            for owned in [false, true] {
                let root = NativeSurfaceFill(color: fixture.0, corners: fixture.1, owner: nil, ownedLayer: owned)
                    .frame(width: 160, height: 84).shadow(color: .black.opacity(0.12), radius: 12, x: 0, y: 6).padding(36)
                let host = NSHostingView(rootView: root)
                host.frame = NSRect(x: 0, y: 0, width: 232, height: 156)
                let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
                defer { window.orderOut(nil); window.contentView = nil; window.close() }
                host.layoutSubtreeIfNeeded()
                let native = try XCTUnwrap(fill(in: host)); native.recordDraws = true
                native.needsDisplay = true; native.layer?.setNeedsDisplay()
                host.displayIfNeeded(); CATransaction.flush()
                let bitmap = try XCTUnwrap(CaptureRaster.forView(host)); host.cacheDisplay(in: host.bounds, to: bitmap)
                XCTAssertGreaterThan(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: bitmap.pixelsWide / 2, y: bitmap.pixelsHigh / 2))[3], 0)
                XCTAssertNotNil(native.observation()["current_draw"] as? [String: Any])
                if owned {
                    XCTAssertEqual(native.backingPaintObservation()["current"] as? Bool, true)
                    XCTAssertTrue((native.layer?.sublayers ?? []).isEmpty)
                    native.configure(color: .red, corners: fixture.1, owner: nil, region: "window")
                    XCTAssertEqual(native.backingPaintObservation()["current"] as? Bool, false)
                }
                images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            }
            if images[0] != images[1] {
                let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try images[0].write(to: directory.appendingPathComponent("fill-layer-\(index)-original.png"))
                try images[1].write(to: directory.appendingPathComponent("fill-layer-\(index)-owned.png"))
            }
            XCTAssertEqual(images[0], images[1], "The owned fill image must preserve the native host's fill and surrounding shadow")
        }
    }
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
        let fixtures: [(radius: CGFloat, shadows: [SurfaceShadow])] = [(0, []), (8, []), (16, []), (16, SurfaceShadow.dialog)]
        var nativeContexts: [[String: Any]] = []
        for (index, fixture) in fixtures.enumerated() {
            var images: [Data] = []
            let margin: CGFloat = fixture.shadows.isEmpty ? 0 : 56
            for native in [false, true] {
                let root = Color.clear.frame(width: 160, height: 84)
                    .modifier(RecordedSurface(background: Color(red: 0.93, green: 0.91, blue: 0.88),
                        border: .black.opacity(0.2), borderWidth: 1, radius: fixture.radius,
                        shadows: fixture.shadows, nativeFill: native)).padding(margin)
                let host = NSHostingView(rootView: root)
                host.frame = NSRect(x: 0, y: 0, width: 160 + 2 * margin, height: 84 + 2 * margin)
                let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                window.contentView = host; window.orderFront(nil)
                host.layoutSubtreeIfNeeded(); host.display(); CATransaction.flush()
                if native {
                    func fills(_ view: NSView) -> [NativeSurfaceFillView] {
                        (view as? NativeSurfaceFillView).map { [$0] } ?? view.subviews.flatMap(fills)
                    }
                    let fill = try XCTUnwrap(fills(host).first)
                    fill.recordDraws = true; fill.needsDisplay = true; fill.layer?.setNeedsDisplay()
                    XCTAssertEqual(fill.usesOwnedBackingImage, fixture.shadows.isEmpty,
                        "A shadowed surface must retain the pixel-validated AppKit composition path")
                }
                host.displayIfNeeded(); CATransaction.flush()
                let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
                host.cacheDisplay(in: host.bounds, to: bitmap)
                if native {
                    nativeContexts.append(["fixture": index, "shadowed": !fixture.shadows.isEmpty,
                        "fills": NativeSurfaceFill.observations(in: window)])
                }
                images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
                XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: bitmap.pixelsWide / 2, y: bitmap.pixelsHigh / 2))[3], 255)
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
        let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: nativeContexts, options: [.sortedKeys])
            .write(to: directory.appendingPathComponent("surface-render-contexts.json"))
        let formats: [[String: Any]] = nativeContexts.map { fixture in
            ["fixture": fixture["fixture"]!, "shadowed": fixture["shadowed"]!,
             "contexts": (fixture["fills"] as? [[String: Any]] ?? []).map {
                ($0["current_draw"] as? [String: Any])?["context_bitmap"] ?? NSNull()
             }]
        }
        let summary = try JSONSerialization.data(withJSONObject: formats, options: [.sortedKeys])
        print("Actual native fill context formats: " + String(decoding: summary, as: UTF8.self))
    }
}
