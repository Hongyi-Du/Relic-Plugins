import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class ApplicationWindowPlacementTests: XCTestCase {
    private func window() -> NSWindow {
        let window = NSWindow(contentRect: CGRect(x: 10, y: 50, width: 600, height: 400),
            styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        WindowChrome.apply(to: window)
        return window
    }

    func testFreshWindowUsesVisibleScreenPolicyWithoutEnteringFullscreen() throws {
        _ = NSApplication.shared
        let name = "Relic.PlacementTest." + UUID().uuidString
        let window = window()
        defer { window.setFrameAutosaveName(""); window.close(); NSWindow.removeFrame(usingName: name) }
        let placement = ApplicationWindowPlacement(window: window, autosaveName: name)
        let expected = WindowPlacement.defaultFrame(in: placement.initialVisibleFrame)
        XCTAssertEqual(window.frame.minX, expected.minX, accuracy: 1)
        XCTAssertEqual(window.frame.minY, expected.minY, accuracy: 1)
        XCTAssertEqual(window.frame.width, expected.width, accuracy: 1)
        XCTAssertEqual(window.frame.height, expected.height, accuracy: 1)
        XCTAssertEqual(window.minSize, WindowPlacement.minimumSize(in: placement.initialVisibleFrame))
        XCTAssertEqual(window.frameAutosaveName, name)
        XCTAssertFalse(window.styleMask.contains(.fullScreen))
        XCTAssertFalse(window.isRestorable)
        let frame = window.frame
        NotificationCenter.default.post(name: NSWindow.didChangeBackingPropertiesNotification, object: window)
        XCTAssertEqual(window.frame, frame, "A backing-scale change must not resize the point frame")
    }

    func testSavedFrameRestoresInANewNativeWindow() throws {
        _ = NSApplication.shared
        let name = "Relic.PlacementTest." + UUID().uuidString
        defer { NSWindow.removeFrame(usingName: name) }
        let first = window()
        var firstPlacement: ApplicationWindowPlacement? = ApplicationWindowPlacement(window: first, autosaveName: name)
        let visible = try XCTUnwrap(firstPlacement).initialVisibleFrame
        let saved = WindowPlacement.clamped(CGRect(x: visible.minX + 30, y: visible.minY + 40, width: 1000, height: 680), to: visible)
        first.setFrame(saved, display: false)
        first.saveFrame(usingName: name)
        first.setFrameAutosaveName(""); first.close(); firstPlacement = nil
        let second = window()
        defer { second.setFrameAutosaveName(""); second.close() }
        let restored = ApplicationWindowPlacement(window: second, autosaveName: name)
        XCTAssertEqual(restored.initialFrame.origin.x, saved.origin.x, accuracy: 1)
        XCTAssertEqual(restored.initialFrame.origin.y, saved.origin.y, accuracy: 1)
        XCTAssertEqual(restored.initialFrame.width, saved.width, accuracy: 1)
        XCTAssertEqual(restored.initialFrame.height, saved.height, accuracy: 1)
    }

    func testNarrowStartupClosesInspectorWithoutOverwritingWideWindowPreference() {
        let suite = "Relic.PlacementTest." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(true, forKey: "panel")
        let model = Model(defaults: defaults)
        model.prepareInitialWindow(size: CGSize(width: 1024, height: 700))
        XCTAssertFalse(model.panelOpen)
        XCTAssertEqual(defaults.object(forKey: "panel") as? Bool, true)
        XCTAssertEqual(model.windowSize, CGSize(width: 1024, height: 700))
    }
}
