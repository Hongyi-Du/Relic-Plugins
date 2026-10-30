import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class NativeSurfaceGeometryTests: XCTestCase {
    func testPaddedCardUsesItsMountedSurfaceWhileRetainingAXContentBounds() throws {
        let owner = "relic-card/geometry-test"
        let sample = ReferenceLabel("A padded card", size: 13)
            .frame(width: 150, height: 20).padding(.horizontal, 10).padding(.vertical, 8)
            .modifier(RecordedSurface(background: .white, radius: 8, kind: "card", owner: owner))
        let host = NSHostingView(rootView: sample)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 170, height: 36),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        let content = window.convertToScreen(host.convert(host.bounds, to: nil))
        let surface = try XCTUnwrap(SurfacePaintProbe.snapshots(in: content).first { $0["owner"] as? String == owner })
        let measured = try XCTUnwrap(surface["rectValue"] as? NSValue).rectValue
        XCTAssertEqual(measured.width, 170, accuracy: 0.01)
        XCTAssertEqual(measured.height, 36, accuracy: 0.01)
        let contentBounds = ElementCapture.box(NSRect(x: 10, y: 8, width: 150, height: 20))
        var element: [String: Any] = ["kind": "card", "identifier": owner, "rect": contentBounds]
        NativeSurfaceGeometry.attach(to: &element, surface: surface, viewport: host.bounds)
        XCTAssertEqual(ElementCapture.rect(element["rect"]), measured)
        XCTAssertEqual(ElementCapture.rect(element["ax_content_rect"]), ElementCapture.rect(contentBounds))
        XCTAssertNotNil(element["native_surface_geometry"])
        // An unrelated but geometrically identical owner cannot lend its box.
        var unrelated: [String: Any] = ["kind": "card", "identifier": "different", "rect": contentBounds]
        NativeSurfaceGeometry.attach(to: &unrelated, surface: surface, viewport: host.bounds)
        XCTAssertNil(unrelated["native_surface_geometry"])
        XCTAssertEqual(ElementCapture.rect(unrelated["rect"]), ElementCapture.rect(contentBounds))
    }
}
