import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class PerformanceNavigationTests: XCTestCase {
    func testPhaseContractDoesNotPromoteLegacyOrMisspelledPhases() throws {
        XCTAssertEqual(try PerformancePhase(manifest: Node()), .legacy)
        XCTAssertFalse(try PerformancePhase(manifest: Node()).usesPointerNavigation)
        for phase in ["open-every-chat", "history", "idle", "switch-chats", "workflows", "monkey"] {
            XCTAssertEqual(try PerformancePhase(manifest: Node(["phase": phase, "version": 2])).rawValue, phase)
        }
        XCTAssertThrowsError(try PerformancePhase(manifest: Node(["phase": "open-chat", "version": 2])))
        XCTAssertThrowsError(try PerformancePhase(manifest: Node(["phase": "history", "version": 1])))
        XCTAssertThrowsError(try PerformancePhase(manifest: Node(["version": 2])))
        XCTAssertTrue(PerformancePhase.openEveryChat.continuesFailedActions)
        XCTAssertTrue(PerformancePhase.switchChats.continuesFailedActions)
        XCTAssertFalse(PerformancePhase.history.runsMonkey)
        XCTAssertFalse(PerformancePhase.idle.runsMonkey)
        XCTAssertTrue(PerformancePhase.monkey.runsMonkey)
    }

    func testLatestObservationRequiresMatchingVisibleBodyAndReadyMarkdown() throws {
        _ = NSApplication.shared
        let suite = "Relic.LatestObservation." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let model = Model(defaults: defaults)
        defer { model.stop(); defaults.removePersistentDomain(forName: suite) }
        model.streamRows = [ConversationRow(id: "id:81#0", item: Node(["id": 81, "type": "message", "text": "Actual latest body"]), separator: nil, continued: false)]
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 400, height: 240), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let scroll = NSScrollView(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        let document = FlippedDocument(frame: CGRect(x: 0, y: 0, width: 400, height: 1200))
        scroll.documentView = document; window.contentView = scroll; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let row = RenderReadiness.Probe(frame: CGRect(x: 0, y: 30, width: 350, height: 170))
        row.kind = "conversation-row"; row.identity = "id:81#0"; row.ready = true; document.addSubview(row)
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expected: "82"))
        XCTAssertFalse(try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "81")).ready,
            "A visible admitted row without a body must not satisfy first-content timing")
        let markdown = RenderReadiness.Probe(frame: CGRect(x: 30, y: 70, width: 290, height: 90))
        markdown.kind = "markdown"; markdown.ready = false; document.addSubview(markdown)
        let storage = NSTextStorage(string: "Actual latest body"), manager = NSLayoutManager(), container = NSTextContainer(containerSize: CGSize(width: 290, height: 90))
        storage.addLayoutManager(manager); manager.addTextContainer(container)
        let body = QuoteTextView(frame: CGRect(x: 30, y: 70, width: 290, height: 90), textContainer: container)
        body.isEditable = false; document.addSubview(body)
        XCTAssertFalse(try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "81")).ready,
            "Unprepared visible Markdown must not satisfy timing")
        markdown.ready = true
        let ready = try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "81"))
        XCTAssertTrue(ready.ready); XCTAssertEqual(ready.messageID, "81"); XCTAssertEqual(ready.rowID, "id:81#0")
        scroll.contentView.scroll(to: CGPoint(x: 0, y: 700)); scroll.reflectScrolledClipView(scroll.contentView)
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expected: "81"),
            "An offscreen latest row must not pass just because its native view still exists")
    }

    func testPointerInjectionRequiresTheActualButtonToHandleMouseInput() async throws {
        _ = NSApplication.shared
        let previous = ProcessInfo.processInfo.environment["RELIC_PERF_MANIFEST"]
        setenv("RELIC_PERF_MANIFEST", "native-unit-fixture", 1)
        defer { if let previous { setenv("RELIC_PERF_MANIFEST", previous, 1) } else { unsetenv("RELIC_PERF_MANIFEST") } }
        let target = "test-native-pointer-" + UUID().uuidString
        var actualActions = 0
        let host = NSHostingView(rootView: Button {
            PerformancePointer.observed(target); actualActions += 1
        } label: { Text("Native button").frame(width: 180, height: 40) }
            .modifier(PerformancePointerTarget(identity: target)).frame(width: 280, height: 140))
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 280, height: 140), styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let deadline = ProcessInfo.processInfo.systemUptime + 3
        while (PerformancePointer.mount(target, in: window)?.clippedBounds.height ?? 0) < 1 && ProcessInfo.processInfo.systemUptime < deadline {
            try await Task.sleep(for: .milliseconds(20))
        }
        // swift test has no NSApplication.run() loop. Dequeue the same posted
        // native events through NSApplication, never invoke Button actions or
        // the observed callback as a substitute for actual mouse dispatch.
        let pump = Task { @MainActor in
            while !Task.isCancelled {
                while let event = NSApp.nextEvent(matching: [.leftMouseDown, .leftMouseUp], until: Date(), inMode: .default, dequeue: true) {
                    NSApp.sendEvent(event)
                }
                do { try await Task.sleep(for: .milliseconds(5)) } catch { return }
            }
        }
        defer { pump.cancel() }
        let started = ProcessInfo.processInfo.systemUptime
        let handled = try await PerformanceNavigation.inject(window, target: target)
        XCTAssertEqual(actualActions, 1)
        XCTAssertEqual(handled.count, 1)
        XCTAssertGreaterThanOrEqual(handled.uptime, started)
        XCTAssertGreaterThan(handled.unixMilliseconds, 0)
        XCTAssertNotNil(PerformancePointer.mount(target, in: window))
    }

    func testEmptyChatRequiresItsActualVisibleLocalizedEmptyState() throws {
        _ = NSApplication.shared
        let suite = "Relic.EmptyObservation." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let model = Model(defaults: defaults)
        defer { model.stop(); defaults.removePersistentDomain(forName: suite) }
        model.words.load(Node(["lang": "en-US", "strings": ["chat.empty_group": "No group messages"]]))
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 400, height: 240), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let root = NSView(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        window.contentView = root; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        XCTAssertFalse(try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "", expectedEmpty: true)).ready)
        let empty = ReferenceLabel("No group messages").makeLabelView()
        empty.productionRegion = "conversation"; empty.frame = CGRect(x: 20, y: 30, width: 260, height: 30); root.addSubview(empty)
        XCTAssertTrue(try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "", expectedEmpty: true)).ready)
        empty.isHidden = true
        XCTAssertFalse(try XCTUnwrap(PerformanceNavigation.observeLatest(model: model, window: window, expected: "", expectedEmpty: true)).ready)
    }

    private final class FlippedDocument: NSView { override var isFlipped: Bool { true } }
}
