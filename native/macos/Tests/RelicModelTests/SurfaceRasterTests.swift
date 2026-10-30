import XCTest
import SwiftUI
import AppKit
@testable import Relic

@MainActor final class SurfaceRasterTests: XCTestCase {
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
