import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class MessageReflowTests: XCTestCase {
    private struct Header: View {
        let title: String
        var body: some View {
            FlowLayout(spacing: 6, centerRows: true) {
                ReferenceLabel(title, size: 14, lines: 0)
                ReferenceLabel("secretary-coordinator", size: 14, lines: 0)
                ReferenceLabel("12:00", size: 14, lines: 0)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
    }
    private func descendants<T: NSView>(_ view: NSView, as type: T.Type) -> [T] {
        ((view as? T).map { [$0] } ?? []) + view.subviews.flatMap { descendants($0, as: type) }
    }
    func testCachedHeaderWrapsAfterWidthAndTextChanges() async throws {
        _ = NSApplication.shared
        let host = NSHostingView(rootView: Header(title: "Secretariat coordinator"))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 230, height: 700), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        func labels() async throws -> [ReferenceLabelView] {
            try await Task.sleep(for: .milliseconds(80)); host.layoutSubtreeIfNeeded()
            return descendants(host, as: ReferenceLabelView.self)
        }
        let narrow = try await labels()
        let narrowFirst = try XCTUnwrap(narrow.first { $0.string == "Secretariat coordinator" })
        let narrowLast = try XCTUnwrap(narrow.first { $0.string == "12:00" })
        XCTAssertGreaterThan(abs(narrowFirst.convert(narrowFirst.bounds, to: host).midY - narrowLast.convert(narrowLast.bounds, to: host).midY), 10)
        window.setContentSize(NSSize(width: 700, height: 700))
        let wide = try await labels()
        let first = try XCTUnwrap(wide.first { $0.string == "Secretariat coordinator" })
        let last = try XCTUnwrap(wide.first { $0.string == "12:00" })
        XCTAssertEqual(first.convert(first.bounds, to: host).midY, last.convert(last.bounds, to: host).midY, accuracy: 1)
        let shortHeight = first.bounds.height
        let long = String(repeating: "Changed long author title ", count: 40)
        host.rootView = Header(title: long)
        let changed = try await labels()
        XCTAssertGreaterThan(try XCTUnwrap(changed.first { $0.string == long }).bounds.height, shortHeight * 3)
    }
    func testCachedMarkdownReflowsAndReplacesItsActualNativeText() async throws {
        _ = NSApplication.shared
        let model = Model()
        let passage = String(repeating: "Actual Markdown content wraps when the window changes. ", count: 35)
        let host = NSHostingView(rootView: RichText(passage).environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 300, height: 900), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func text(_ expected: String) async throws -> QuoteTextView {
            let deadline = ProcessInfo.processInfo.systemUptime + 5
            repeat {
                try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
                if RowMountQueue.shared.isIdle, let view = descendants(host, as: QuoteTextView.self).first(where: { $0.string == expected }) { return view }
            } while ProcessInfo.processInfo.systemUptime < deadline
            return try XCTUnwrap(descendants(host, as: QuoteTextView.self).first { $0.string == expected })
        }
        let narrowHeight = try await text(passage).bounds.height
        window.setContentSize(NSSize(width: 700, height: 900))
        let wideHeight = try await text(passage).bounds.height
        XCTAssertGreaterThan(narrowHeight, wideHeight)
        host.rootView = RichText("Changed short paragraph").environmentObject(model)
        let changed = try await text("Changed short paragraph")
        XCTAssertLessThan(changed.bounds.height, wideHeight)
    }
}
