import XCTest
import SwiftUI
import AppKit
@testable import Relic

@MainActor final class SurfaceRasterTests: XCTestCase {
    func testDashedLegendEdgePaintsBothDashesAndGaps() throws {
        let sample = Color.clear.frame(width: 18, height: 1)
            .modifier(RecordedSurface(background: .clear, border: .black,
                edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "divider", borderDash: [3,3]))
            .padding(4).background(Color.white)
        let host = NSHostingView(rootView: sample)
        host.frame = NSRect(x: 0, y: 0, width: 26, height: 9)
        host.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        for x in [5, 11, 17] { XCTAssertLessThan(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: x, y: 4))[0], 2) }
        for x in [8, 14, 20] { XCTAssertGreaterThan(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: x, y: 4))[0], 253) }
    }

    func testDialogShadowMatchesTheActualReferenceEdgeProfile() throws {
        // Actual 56253c7 macOS reference, zh-CN/light/1024x700/member-card.
        // Sample the middle of the straight bottom edge, away from corner and
        // text paint, with each offset measured from the card's own bottom.
        let sample = Color.clear.frame(width: 340, height: 525)
            .modifier(RecordedSurface(background: .white, border: RelicStyle.line, borderWidth: 1,
                radius: 16, shadows: SurfaceShadow.dialog))
            .padding(60).background(Color.white).environment(\.colorScheme, .light)
        let host = NSHostingView(rootView: sample)
        host.appearance = NSAppearance(named: .aqua)
        host.frame = NSRect(x: 0, y: 0, width: 460, height: 645)
        host.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        for (offset, expected) in [(1, [225.0,225,224]), (4, [232.0,232,232]), (8, [237.0,237,237]),
                                   (16, [244.0,244,243]), (24, [249.0,249,249]), (40, [255.0,255,255])] {
            let pixel = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 230, y: 585 + offset))
            print("DIALOG SHADOW offset=\(offset) actual=\(pixel) reference=\(expected)")
            for channel in 0..<3 { XCTAssertEqual(pixel[channel], expected[channel], accuracy: 2) }
        }
    }

    func testCabinetRingsPreserveTheInnerGapAndOriginalAvatarFill() throws {
        let sample = Color.clear.frame(width: 22, height: 22)
            .modifier(RecordedSurface(background: Color(.sRGB, red: 0, green: 0, blue: 1), radius: 6,
                rings: [SurfaceRing(width: 2, color: .white), SurfaceRing(width: 4, color: Color(.sRGB, red: 1, green: 0, blue: 0))]))
            .padding(6).background(Color.black)
        let host = NSHostingView(rootView: sample)
        host.frame = NSRect(x: 0, y: 0, width: 34, height: 34)
        host.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        for (x, expected) in [(3, [255.0, 0, 0, 255]), (5, [255.0, 255, 255, 255]), (8, [0.0, 0, 255, 255])] {
            let pixel = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: x, y: 17))
            for channel in 0..<4 { XCTAssertEqual(pixel[channel], expected[channel], accuracy: 2, "Actual cabinet ring layer at x=\(x)") }
        }
    }

    func testComposerDisabledOpacityIsAppliedExactlyOnce() throws {
        let model = Model(defaults: UserDefaults(suiteName: "send-paint-" + UUID().uuidString)!)
        for enabled in [true, false] {
            let sample = ComposerSendButton(action: {}).environmentObject(model).disabled(!enabled)
                .frame(width: 32, height: 32).background(Color.white).environment(\.colorScheme, .light)
            // ImageRenderer substitutes unsupported-view paint for the AppKit
            // probes behind this transparent button. Cache its actual hosting
            // view, exactly as capture does, rather than testing that substitute.
            let host = NSHostingView(rootView: sample)
            host.appearance = NSAppearance(named: .aqua)
            host.frame = NSRect(x: 0, y: 0, width: 32, height: 32)
            host.layoutSubtreeIfNeeded()
            let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
            XCTAssertEqual(bitmap.colorSpace, .sRGB)
            host.cacheDisplay(in: host.bounds, to: bitmap)
            // Inside the circle, away from its anti-aliased edge and arrow ink.
            let pixel = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 7, y: 16))
            var channels = [Int](repeating: 0, count: 4)
            bitmap.getPixel(&channels, atX: 7, y: 16)
            print("SEND PAINT enabled=\(enabled) colorSpace=\(bitmap.colorSpace.localizedName ?? "unknown") samples=\(bitmap.samplesPerPixel) bits=\(bitmap.bitsPerSample) raw=\(channels) srgb=\(pixel)")
            let expected = enabled ? 27.0 / 255 : 1 - 0.35 + (27.0 / 255) * 0.35
            XCTAssertEqual(pixel[0] / 255, expected, accuracy: 2.0 / 255)
            XCTAssertEqual(pixel[1] / 255, expected, accuracy: 2.0 / 255)
            let composite = try XCTUnwrap(CaptureRaster.composite(width: 32, height: 32) { canvas in
                NSColor.white.setFill(); canvas.fill(); bitmap.draw(in: canvas)
            })
            XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(composite, x: 7, y: 16)), pixel,
                "Final native window composition must preserve the actual opaque source pixels")
            let png = try XCTUnwrap(composite.representation(using: .png, properties: [:]))
            let decoded = try XCTUnwrap(NSBitmapImageRep(data: png))
            let encodedPixel = try XCTUnwrap(CaptureRaster.sRGBPixel(decoded, x: 7, y: 16))
            XCTAssertEqual(encodedPixel, pixel, "The actual PNG must preserve the measured sRGB bytes")
        }
    }

    func testBoxShadowDoesNotCastASecondShadowFromInteriorContent() throws {
        let sample = Rectangle().fill(Color.black).frame(width: 20, height: 20)
            .frame(width: 100, height: 100)
            .modifier(RecordedSurface(background: .white, radius: 10, shadows: [SurfaceShadow(color: .black, radius: 8, x: 0, y: 6)]))
        // The production outline is now an actual AppKit overlay. ImageRenderer
        // substitutes unsupported-view placeholder paint for that layer, so
        // inspect the same real hosting-view cache as the window capture.
        let host = NSHostingView(rootView: sample)
        host.frame = NSRect(x: 0, y: 0, width: 100, height: 100)
        host.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        for point in [(30,50), (50,70), (70,50), (50,30)] {
            let color = try XCTUnwrap(bitmap.colorAt(x: point.0, y: point.1)?.usingColorSpace(.sRGB))
            XCTAssertEqual(color.redComponent, 1, accuracy: 0.01)
            XCTAssertEqual(color.greenComponent, 1, accuracy: 0.01)
            XCTAssertEqual(color.blueComponent, 1, accuracy: 0.01)
        }
        XCTAssertLessThan(try XCTUnwrap(bitmap.colorAt(x: 50, y: 50)).redComponent, 0.01)
    }
}
