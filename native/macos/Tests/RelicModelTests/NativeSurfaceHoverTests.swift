import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class NativeSurfaceHoverTests: XCTestCase {
    func testAnUnobservedSurfaceDoesNotInventAnExitEvent() throws {
        let observer = NativeSurfaceHover()
        XCTAssertNil(observer.value)
        XCTAssertEqual(observer.observation()["callback_count"] as? Int, 0)
        XCTAssertTrue(observer.observation()["last_event"] is NSNull)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: observer.observation()))
    }

    func testActualHoverCallbacksRespectTheFrontSurfaceAndRetainTheExit() async throws {
        _ = NSApplication.shared
        let originalPointer = NSEvent.mouseLocation
        let root = ZStack {
            Color.white.frame(width: 200, height: 140)
                .modifier(RecordedSurface(background: .white, kind: "card", owner: "hover-test-back"))
            Color.gray.frame(width: 100, height: 60)
                .modifier(RecordedSurface(background: .gray, kind: "card", owner: "hover-test-front"))
        }.frame(width: 200, height: 140)
        let host = NSHostingView(rootView: root)
        host.frame = NSRect(x: 0, y: 0, width: 200, height: 140)
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 200, height: 140),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host
        window.acceptsMouseMovedEvents = true; window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        defer {
            try? VisualCapture.movePointer(to: originalPointer)
            window.orderOut(nil); window.contentView = nil; window.close()
        }
        host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); CATransaction.flush()
        func observation(_ owner: String) -> [String: Any]? {
            SurfacePaintProbe.snapshots(in: window.frame).first { $0["owner"] as? String == owner }
        }
        func move(_ point: NSPoint, until condition: () -> Bool) async throws {
            try VisualCapture.movePointer(to: point)
            let deadline = ProcessInfo.processInfo.systemUptime + 2
            repeat {
                // Deliver real queued WindowServer events to the mounted views;
                // never invoke the observer or its callback from the test.
                while let event = NSApp.nextEvent(matching: .any, until: .distantPast, inMode: .default, dequeue: true) {
                    NSApp.sendEvent(event)
                }
                if condition() { return }
                try await Task.sleep(for: .milliseconds(20))
            } while ProcessInfo.processInfo.systemUptime < deadline
        }
        try await move(NSPoint(x: 10, y: 10)) { false }
        let frontBefore = try XCTUnwrap(observation("hover-test-front"))
        let frontBounds = ElementCapture.rect(frontBefore["bounds"])
        try await move(window.convertPoint(toScreen: NSPoint(x: 100, y: 70))) {
            observation("hover-test-front")?["hovered"] as? Bool == true
        }
        let front = try XCTUnwrap(observation("hover-test-front"))
        XCTAssertEqual(front["hovered"] as? Bool, true, String(describing: front["native_hover_callbacks"]))
        XCTAssertNotEqual(observation("hover-test-back")?["hovered"] as? Bool, true,
            "A covered sibling must not receive hover merely because its rectangle contains the pointer")
        XCTAssertEqual(ElementCapture.rect(front["bounds"]), frontBounds)
        try await move(NSPoint(x: 10, y: 10)) { observation("hover-test-front")?["hovered"] as? Bool == false }
        let exited = try XCTUnwrap(observation("hover-test-front"))
        XCTAssertEqual(exited["hovered"] as? Bool, false)
        let evidence = try XCTUnwrap(exited["native_hover_callbacks"] as? [String: Any])
        XCTAssertGreaterThanOrEqual(evidence["callback_count"] as? Int ?? 0, 2)
        XCTAssertEqual(evidence["infers_from_geometry_or_ax_hit"] as? Bool, false)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: evidence))
    }
}
