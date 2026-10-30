import XCTest
import AppKit
@testable import Relic

@MainActor final class IconDrawTests: XCTestCase {
    func testIconReceiptRequiresTheExecutedNativePathStroke() throws {
        // A 48px icon has a 3.4px stroke: the sampled center pixel is fully
        // covered. At 24px its 1.7px crossing is partially antialiased (250/255),
        // so it cannot test full-opacity paint. Keep the opacity assertion.
        let view = ElementPaintProbe.PaintView(frame: NSRect(x: 0, y: 0, width: 48, height: 48))
        view.recordDraws = true
        view.configure(name: "plus", size: 48, color: NSColor(srgbRed: 1, green: 0, blue: 0, alpha: 1))
        XCTAssertNil(view.lastDraw)
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let draw = try XCTUnwrap(view.lastDraw)
        XCTAssertEqual(draw["draw_returned"] as? Bool, true)
        XCTAssertEqual(draw["source_path"] as? String, ReferenceIcons.paths["plus"])
        XCTAssertEqual((draw["stroke_width"] as? NSNumber)?.doubleValue, 3.4)
        XCTAssertEqual(draw["line_cap"] as? String, "round")
        XCTAssertEqual(draw["line_join"] as? String, "round")
        let commands = try XCTUnwrap(draw["rendered_path_commands"] as? [[String: Any]])
        XCTAssertEqual(commands.count, 4)
        XCTAssertEqual(ElementCapture.rect(draw["rendered_path_bounds"]), NSRect(x: 10, y: 10, width: 28, height: 28))
        let center = try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 24, y: 24))
        XCTAssertGreaterThan(center[0], 250); XCTAssertLessThan(center[1], 1); XCTAssertLessThan(center[2], 1)
        XCTAssertGreaterThan(center[3], 250)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0)
        XCTAssertNil(view.currentDraw(), "An isolated bitmap does not prove a current mounted-window draw")
        XCTAssertTrue(IconOutlineCapture.inspect(view).paint is NSNull)
        XCTAssertEqual(draw["presentation_identity_proven"] as? Bool, false)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: draw))
    }

    func testMountedIconRejectsStaleColorResourceAndBoundsWithoutDiscardingRawDraws() throws {
        _ = NSApplication.shared
        let view = ElementPaintProbe.PaintView(frame: NSRect(x: 0, y: 0, width: 24, height: 24))
        view.recordDraws = true; view.configure(name: "plus", size: 24, color: .black)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        func draw() throws {
            let bitmap = try XCTUnwrap(CaptureRaster.forView(view)); view.cacheDisplay(in: view.bounds, to: bitmap)
        }
        try draw()
        XCTAssertNotNil(view.currentDraw())
        let outline = IconOutlineCapture.inspect(view)
        let nativeChildren = view.layer?.sublayers?.count ?? 0
        let presentedChildren = view.layer?.presentation()?.sublayers?.count ?? 0
        if nativeChildren == 0 && presentedChildren == 0 && (view.layer == nil || view.layer?.presentation() != nil) {
            XCTAssertEqual(outline.paint as? String, "none", String(describing: outline.evidence))
        } else { XCTAssertTrue(outline.paint is NSNull) }
        view.focusRingType = .exterior
        XCTAssertTrue(IconOutlineCapture.inspect(view).paint is NSNull)
        view.focusRingType = .none
        let child = NSView(frame: .zero); view.addSubview(child)
        XCTAssertTrue(IconOutlineCapture.inspect(view).paint is NSNull)
        child.removeFromSuperview()
        let first = try XCTUnwrap(view.lastDraw?["sequence"] as? Int)
        view.configure(name: "plus", size: 24, color: .systemRed)
        XCTAssertNil(view.currentDraw())
        XCTAssertEqual(view.lastDraw?["sequence"] as? Int, first)
        try draw(); XCTAssertNotNil(view.currentDraw())
        view.configure(name: "down", size: 24, color: .systemRed)
        XCTAssertNil(view.currentDraw())
        try draw(); XCTAssertNotNil(view.currentDraw())
        view.bounds.size.width = 20
        XCTAssertNil(view.currentDraw())
        try draw(); XCTAssertNotNil(view.currentDraw())
        window.orderOut(nil)
        XCTAssertNil(view.currentDraw())
    }
}
