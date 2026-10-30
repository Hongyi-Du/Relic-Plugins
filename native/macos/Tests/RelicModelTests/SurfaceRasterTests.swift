import XCTest
import SwiftUI
import AppKit
@testable import Relic

@MainActor final class SurfaceRasterTests: XCTestCase {
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
            let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            let decoded = try XCTUnwrap(NSBitmapImageRep(data: png))
            let encodedPixel = try XCTUnwrap(CaptureRaster.sRGBPixel(decoded, x: 7, y: 16))
            XCTAssertEqual(encodedPixel, pixel, "The actual PNG must preserve the measured sRGB bytes")
        }
    }

    func testBoxShadowDoesNotCastASecondShadowFromInteriorContent() throws {
        let sample = Rectangle().fill(Color.black).frame(width: 20, height: 20)
            .frame(width: 100, height: 100)
            .modifier(RecordedSurface(background: .white, radius: 10, shadows: [SurfaceShadow(color: .black, radius: 8, x: 0, y: 6)]))
        let renderer = ImageRenderer(content: sample)
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.cgImage), bitmap = NSBitmapImageRep(cgImage: image)
        for point in [(30,50), (50,70), (70,50), (50,30)] {
            let color = try XCTUnwrap(bitmap.colorAt(x: point.0, y: point.1)?.usingColorSpace(.sRGB))
            XCTAssertEqual(color.redComponent, 1, accuracy: 0.01)
            XCTAssertEqual(color.greenComponent, 1, accuracy: 0.01)
            XCTAssertEqual(color.blueComponent, 1, accuracy: 0.01)
        }
        XCTAssertLessThan(try XCTUnwrap(bitmap.colorAt(x: 50, y: 50)).redComponent, 0.01)
    }
}
