import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeOpaqueCoverageTests: XCTestCase {
    func testMountedOpaqueFillRequiresActualFrontOrderImageAlphaAndFinalPixels() async throws {
        _ = NSApplication.shared
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 240, height: 160)); root.wantsLayer = true
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 240, height: 160),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = root
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let target = ReferenceLabel("Covered text", size: 14).makeLabelView()
        target.frame = NSRect(x: 60, y: 60, width: 100, height: 24)
        let fill = NativeSurfaceFillView(frame: NSRect(x: 30, y: 30, width: 180, height: 100))
        fill.recordDraws = true; fill.configure(color: .white, corners: [8,8,8,8], owner: "actual-dialog", region: "dialog")
        fill.enableOwnedBackingImage()
        root.addSubview(target); root.addSubview(fill); window.orderFront(nil)
        func capture() async throws -> (NSBitmapImageRep, NSRect, NSRect) {
            root.layoutSubtreeIfNeeded(); fill.needsDisplay = true; fill.layer?.setNeedsDisplay()
            root.displayIfNeeded(); CATransaction.flush()
            try await Task.sleep(for: .milliseconds(80))
            let bitmap = try XCTUnwrap(CaptureRaster.forView(root)); root.cacheDisplay(in: root.bounds, to: bitmap)
            return (bitmap, window.convertToScreen(root.convert(root.bounds, to: nil)),
                    window.convertToScreen(target.convert(target.bounds.insetBy(dx: 2, dy: 2), to: nil)))
        }
        let (bitmap, canvas, bounds) = try await capture()
        let covered = NativeOpaqueCoverage.inspect(target: target, screenRect: bounds, fill: fill, bitmap: bitmap, canvas: canvas)
        XCTAssertEqual(covered["candidate_opaque_cover"] as? Bool, true, String(describing: covered))
        XCTAssertEqual(covered["changes_visibility"] as? Bool, false)
        XCTAssertGreaterThan(covered["pixel_count"] as? Int ?? 0, 0)
        XCTAssertEqual((covered["capture_root"] as? [String: Any])?["view_identity"] as? String,
            String(describing: ObjectIdentifier(root)))

        // Unknown blend paint inside the cached view must remain a failure,
        // even when it does not visibly change the sampled opaque white pixels.
        let filtered = CALayer(); filtered.frame = CGRect(x: 0, y: 0, width: 1, height: 1)
        filtered.compositingFilter = "multiplyBlendMode"
        root.layer?.addSublayer(filtered); CATransaction.flush()
        try await Task.sleep(for: .milliseconds(80))
        XCTAssertEqual(NativeOpaqueCoverage.inspect(target: target, screenRect: bounds, fill: fill,
            bitmap: bitmap, canvas: canvas)["candidate_opaque_cover"] as? Bool, false)
        filtered.removeFromSuperlayer(); CATransaction.flush()
        try await Task.sleep(for: .milliseconds(80))

        // Even with the same valid native order/image, altered final pixels
        // cannot serve as evidence of that image's final visible coverage.
        let point = ElementCapture.topLeft(bounds, in: canvas).origin
        var black = [0,0,0,255]
        bitmap.setPixel(&black, atX: Int(point.x) + 1, y: Int(point.y) + 1)
        XCTAssertEqual(NativeOpaqueCoverage.inspect(target: target, screenRect: bounds, fill: fill, bitmap: bitmap, canvas: canvas)["candidate_opaque_cover"] as? Bool, false)

        fill.removeFromSuperview(); root.addSubview(fill, positioned: .below, relativeTo: target)
        let (behindBitmap, behindCanvas, behindBounds) = try await capture()
        XCTAssertEqual(NativeOpaqueCoverage.inspect(target: target, screenRect: behindBounds, fill: fill, bitmap: behindBitmap, canvas: behindCanvas)["candidate_opaque_cover"] as? Bool, false)

        fill.removeFromSuperview(); root.addSubview(fill)
        fill.configure(color: NSColor.white.withAlphaComponent(0.5), corners: [8,8,8,8], owner: "actual-dialog", region: "dialog")
        let (alphaBitmap, alphaCanvas, alphaBounds) = try await capture()
        XCTAssertEqual(NativeOpaqueCoverage.inspect(target: target, screenRect: alphaBounds, fill: fill, bitmap: alphaBitmap, canvas: alphaCanvas)["candidate_opaque_cover"] as? Bool, false)

        fill.configure(color: .white, corners: [8,8,8,8], owner: "actual-dialog", region: "dialog")
        let (cornerBitmap, cornerCanvas, _) = try await capture()
        let corner = window.convertToScreen(fill.convert(NSRect(x: 0, y: 0, width: 3, height: 3), to: nil))
        XCTAssertEqual(NativeOpaqueCoverage.inspect(target: target, screenRect: corner, fill: fill, bitmap: cornerBitmap, canvas: cornerCanvas)["candidate_opaque_cover"] as? Bool, false,
            "A rounded corner's transparent pixels cannot establish opaque coverage")
    }
}
