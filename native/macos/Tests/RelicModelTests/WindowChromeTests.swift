import XCTest
import AppKit
@testable import Relic

@MainActor final class WindowChromeTests: XCTestCase {
    func testUnifiedChromeKeepsActualTrafficLightsInsideTheApplicationRow() throws {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1024, height: 700),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.orderOut(nil); window.close() }
        window.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 1024, height: 700))
        WindowChrome.apply(to: window); window.makeKeyAndOrderFront(nil)
        for size in [NSSize(width: 1024, height: 700), NSSize(width: 1440, height: 900)] {
            window.setFrame(NSRect(origin: window.frame.origin, size: size), display: true)
            WindowChrome.positionButtons(in: window)
            XCTAssertTrue(window.titlebarAppearsTransparent)
            XCTAssertEqual(window.titleVisibility, .hidden)
            XCTAssertTrue(window.styleMask.contains(.fullSizeContentView))
            XCTAssertEqual(window.titlebarSeparatorStyle, .none)
            XCTAssertNil(window.toolbar)
            for type in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
                let button = try XCTUnwrap(window.standardWindowButton(type))
                let screen = window.convertToScreen(button.convert(button.bounds, to: nil))
                XCTAssertFalse(button.isHidden)
                XCTAssertNotNil(button.action)
                XCTAssertEqual(window.frame.maxY - screen.midY, WindowChrome.rowHeight / 2, accuracy: 0.5)
                XCTAssertLessThanOrEqual(screen.maxX - window.frame.minX, WindowChrome.controlsWidth)
            }
        }
    }
    func testDragRegionLeavesControlsAndTrafficLightsClickable() {
        let parent = NSView(frame: NSRect(x: 0, y: 0, width: 1024, height: 40))
        let drag = WindowDragRegion.DragView(frame: parent.bounds); parent.addSubview(drag)
        drag.excluded = [NSRect(x: 78, y: 6, width: 310, height: 28), NSRect(x: 800, y: 6, width: 216, height: 28)]
        XCTAssertNil(drag.hitTest(NSPoint(x: 22, y: 20)))
        XCTAssertNil(drag.hitTest(NSPoint(x: 110, y: 20)))
        XCTAssertNil(drag.hitTest(NSPoint(x: 900, y: 20)))
        XCTAssertTrue(drag.hitTest(NSPoint(x: 560, y: 20)) === drag)
        XCTAssertFalse(drag.isAccessibilityElement())
    }
}
