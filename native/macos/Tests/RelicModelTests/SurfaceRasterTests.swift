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
            let renderer = ImageRenderer(content: sample); renderer.scale = 1
            let bitmap = NSBitmapImageRep(cgImage: try XCTUnwrap(renderer.cgImage))
            // Inside the circle, away from its anti-aliased edge and arrow ink.
            let color = try XCTUnwrap(bitmap.colorAt(x: 7, y: 16)?.usingColorSpace(.sRGB))
            let expected = enabled ? 27.0 / 255 : 1 - 0.35 + (27.0 / 255) * 0.35
            XCTAssertEqual(Double(color.redComponent), expected, accuracy: 2.0 / 255)
            XCTAssertEqual(Double(color.greenComponent), expected, accuracy: 2.0 / 255)
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
