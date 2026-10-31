import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class WindowObservationTests: XCTestCase {
    private struct GeometryLabel: View {
        @EnvironmentObject var model: Model
        var body: some View {
            ReferenceLabel("\(Int(model.windowSize.width)) x \(Int(model.windowSize.height))")
        }
    }
    func testEnvironmentObjectViewTracksNestedGeometryWithoutGlobalPublication() async throws {
        _ = NSApplication.shared
        let model = Model()
        let host = NSHostingView(rootView: GeometryLabel().environmentObject(model))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 240, height: 60), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        func label(_ root: NSView) -> ReferenceLabelView? {
            if let view = root as? ReferenceLabelView { return view }
            for child in root.subviews { if let view = label(child) { return view } }
            return nil
        }
        for size in [CGSize(width: 1440, height: 900), CGSize(width: 1024, height: 700), CGSize(width: 1024, height: 800)] {
            model.windowSize = size
            try await Task.sleep(for: .milliseconds(50)); host.layoutSubtreeIfNeeded()
            XCTAssertEqual(try XCTUnwrap(label(host)).string, "\(Int(size.width)) x \(Int(size.height))")
        }
    }
}
