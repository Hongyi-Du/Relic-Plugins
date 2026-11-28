import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class MessageColumnsLayoutTests: XCTestCase {
    private struct Row: View {
        let text: String
        var body: some View {
            MessageColumns {
                Color.clear.frame(width: 36, height: 36)
                ReferenceLabel(text, size: 14, lineHeight: 22, lines: 0)
            }.frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }
    func testCachedColumnsReflowWhenTextAndViewportChange() async throws {
        _ = NSApplication.shared
        let host = NSHostingView(rootView: Row(text: "Short"))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 300, height: 700), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        func label(_ root: NSView) -> ReferenceLabelView? {
            if let text = root as? ReferenceLabelView { return text }
            for child in root.subviews { if let text = label(child) { return text } }
            return nil
        }
        func height() async throws -> CGFloat {
            try await Task.sleep(for: .milliseconds(50)); host.layoutSubtreeIfNeeded()
            return try XCTUnwrap(label(host)).bounds.height
        }
        let short = try await height()
        let passage = String(repeating: "A longer message wraps naturally. ", count: 20)
        host.rootView = Row(text: passage)
        let narrow = try await height()
        XCTAssertGreaterThan(narrow, short * 3)
        window.setContentSize(NSSize(width: 600, height: 700))
        let wide = try await height()
        XCTAssertLessThan(wide, narrow)
        XCTAssertGreaterThan(wide, short)
        host.rootView = Row(text: "Short")
        let restored = try await height()
        XCTAssertEqual(restored, short, accuracy: 0.01)
    }
}
