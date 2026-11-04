import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeLayerOrderTests: XCTestCase {
    func testSiblingOrderAndZPositionRemainIndependentActualObservations() throws {
        let parent = CALayer(), back = CALayer(), front = CALayer()
        parent.addSublayer(back); parent.addSublayer(front)
        back.zPosition = 10
        let initial = NativeLayerOrder.observation(parent)
        XCTAssertEqual(initial["ordered_children"] as? [String], [NativeLayerOrder.identifier(back), NativeLayerOrder.identifier(front)])
        let child = NativeLayerOrder.observation(back)
        XCTAssertEqual(child["sibling_index"] as? Int, 0)
        XCTAssertEqual(child["parent"] as? String, NativeLayerOrder.identifier(parent))
        XCTAssertEqual((child["model"] as? [String: Any])?["z_position"] as? CGFloat, 10)
        parent.insertSublayer(front, at: 0)
        XCTAssertEqual(NativeLayerOrder.observation(parent)["ordered_children"] as? [String], [NativeLayerOrder.identifier(front), NativeLayerOrder.identifier(back)])
        XCTAssertEqual(NativeLayerOrder.observation(back)["sibling_index"] as? Int, 1)
        XCTAssertEqual(child["drawing_duty_proven"] as? Bool, false)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: child))
    }

    func testWindowObservationBindsActualViewsWithoutInventingOcclusion() throws {
        _ = NSApplication.shared
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 120, height: 90))
        let child = NSView(frame: NSRect(x: 10, y: 10, width: 40, height: 20))
        root.wantsLayer = true; root.addSubview(child); child.wantsLayer = true
        let window = NSWindow(contentRect: root.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = root
        let result = NativeLayerOrder.capture(in: window)
        let views = try XCTUnwrap(result["views"] as? [String: Any])
        XCTAssertEqual(views[String(describing: ObjectIdentifier(child))] as? String, NativeLayerOrder.identifier(try XCTUnwrap(child.layer)))
        XCTAssertEqual(result["occlusion_proven"] as? Bool, false)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: result))
    }
}
