import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class WindowObservationTests: XCTestCase {
    private final class BodyCounter { var reads = 0 }
    private struct MessageCountLabel: View {
        @EnvironmentObject var model: Model
        let counter: BodyCounter
        var body: some View {
            counter.reads += 1
            return ReferenceLabel("Messages: \(model.messages.count)")
        }
    }
    func testDialogFieldChangesDoNotReevaluateAnUnrelatedMountedConversation() async throws {
        _ = NSApplication.shared
        let model = Model(), counter = BodyCounter()
        let host = NSHostingView(rootView: MessageCountLabel(counter: counter).environmentObject(model))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 300, height: 80), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
        let before = counter.reads
        XCTAssertGreaterThan(before, 0)
        model.openMemberForm(mode: "existing", edit: "engineer", secretary: true)
        model.settingsSection = "appearance"
        model.openDetails("tasks", member: "engineer", task: "1")
        try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
        XCTAssertEqual(counter.reads, before, "Dialog state must not reevaluate an unrelated message view")
        model.messages = [Node(["id": 1, "text": "New message"])]
        try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
        XCTAssertGreaterThan(counter.reads, before, "Actual message changes must still update the mounted view")
    }
    func testInspectorKeepsItsNativeControlsAcrossResponsiveBreakpoints() async throws {
        _ = NSApplication.shared
        let suite = "Relic.InspectorPersistence." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let model = Model(defaults: defaults)
        model.ready = true; model.organization = "test"; model.panelOpen = true; model.pane = "files"
        model.snapshot = Node(["org": ["id": "test", "name": "Test"], "members": []] as [String: Any])
        let host = NSHostingView(rootView: MainView().environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func tab(_ view: NSView) -> ReferenceLabelView? {
            if let label = view as? ReferenceLabelView, label.productionOwner == "relic-tab/files" { return label }
            for child in view.subviews { if let label = tab(child) { return label } }
            return nil
        }
        var identity: ObjectIdentifier?
        for width in [CGFloat(1440), 1180, 1024, 1440] {
            window.setContentSize(NSSize(width: width, height: 800))
            let deadline = ProcessInfo.processInfo.systemUptime + 6
            var quiet = 0
            repeat {
                try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
                quiet = RowMountQueue.shared.isIdle && tab(host) != nil ? quiet + 1 : 0
            } while quiet < 3 && ProcessInfo.processInfo.systemUptime < deadline
            XCTAssertGreaterThanOrEqual(quiet, 3)
            let current = ObjectIdentifier(try XCTUnwrap(tab(host)))
            if let identity { XCTAssertEqual(current, identity, "Resizing must reuse the native inspector, not recreate its controls") }
            else { identity = current }
        }
    }
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
