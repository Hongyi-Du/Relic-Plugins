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

    func testLatestTruthRequiresIndependentMessageAndTailFieldsIncludingExplicitNulls() {
        let message: [String: Any] = ["latest_message_id": 81, "latest_item_id": 81, "latest_item_kind": "message", "expected_empty": false]
        XCTAssertTrue(PerformanceNavigation.hasIndependentLatestTruth(Node(message)))
        let notice: [String: Any] = ["latest_message_id": 81, "latest_item_id": "e82", "latest_item_kind": "notice", "expected_empty": false]
        XCTAssertTrue(PerformanceNavigation.hasIndependentLatestTruth(Node(notice)))
        XCTAssertTrue(PerformanceNavigation.hasIndependentLatestTruth(Node([
            "latest_message_id": NSNull(), "latest_item_id": "e82", "latest_item_kind": "notice", "expected_empty": false])))
        XCTAssertTrue(PerformanceNavigation.hasIndependentLatestTruth(Node([
            "latest_message_id": NSNull(), "latest_item_id": NSNull(), "latest_item_kind": NSNull(), "expected_empty": true])))
        for field in message.keys {
            var missing = message; missing.removeValue(forKey: field)
            XCTAssertFalse(PerformanceNavigation.hasIndependentLatestTruth(Node(missing)), "Missing truth field: " + field)
        }
        for invalid in ["", "e81", "0"] {
            var bad = notice; bad["latest_message_id"] = invalid
            XCTAssertFalse(PerformanceNavigation.hasIndependentLatestTruth(Node(bad)))
        }
        var inconsistentEmpty = message; inconsistentEmpty["expected_empty"] = true
        XCTAssertFalse(PerformanceNavigation.hasIndependentLatestTruth(Node(inconsistentEmpty)))
    }

    func testLatestObservationRequiresMatchingVisibleBodyAndReadyMarkdown() throws {
        _ = NSApplication.shared
        let suite = "Relic.LatestObservation." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let model = Model(defaults: defaults)
        defer { model.stop(); defaults.removePersistentDomain(forName: suite) }
        let message = Node(["id": 81, "type": "message", "text": "Actual latest body"])
        model.messages = [message]
        model.streamRows = [ConversationRow(id: "id:81#0", item: message, separator: nil, continued: false)]
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 400, height: 240), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let scroll = NSScrollView(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        let document = FlippedDocument(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        scroll.documentView = document; window.contentView = scroll; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let row = RenderReadiness.Probe(frame: CGRect(x: 0, y: 30, width: 350, height: 170))
        row.kind = "conversation-row"; row.identity = "id:81#0"; row.ready = true; document.addSubview(row)
        func observe() -> PerformanceNavigation.LatestObservation? {
            PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "81", expectedItemID: "81", expectedItemKind: "message")
        }
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "81", expectedItemID: "82", expectedItemKind: "message"))
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "81", expectedItemID: "81", expectedItemKind: "notice"))
        XCTAssertFalse(try XCTUnwrap(observe()).ready,
            "A visible admitted row without a body must not satisfy first-content timing")
        let markdown = RenderReadiness.Probe(frame: CGRect(x: 30, y: 70, width: 290, height: 90))
        markdown.kind = "markdown"; markdown.ready = false; document.addSubview(markdown)
        let storage = NSTextStorage(string: "Actual latest body"), manager = NSLayoutManager(), container = NSTextContainer(containerSize: CGSize(width: 290, height: 90))
        storage.addLayoutManager(manager); manager.addTextContainer(container)
        let body = QuoteTextView(frame: CGRect(x: 30, y: 70, width: 290, height: 90), textContainer: container)
        body.isEditable = false; document.addSubview(body)
        XCTAssertFalse(try XCTUnwrap(observe()).ready,
            "Unprepared visible Markdown must not satisfy timing")
        markdown.ready = true
        let ready = try XCTUnwrap(observe())
        XCTAssertTrue(ready.ready); XCTAssertEqual(ready.messageID, "81"); XCTAssertEqual(ready.rowID, "id:81#0")
        XCTAssertEqual(ready.itemID, "81"); XCTAssertEqual(ready.itemKind, "message")
        XCTAssertTrue(ready.messageLoaded); XCTAssertTrue(ready.itemLoaded)
        model.messages = []
        XCTAssertFalse(try XCTUnwrap(observe()).ready, "A native row alone cannot prove the expected message is in the loaded server page")
        model.messages = [message]
        XCTAssertEqual(try XCTUnwrap(ready.bottomGap), 0, accuracy: 0.01)
        document.setFrameSize(CGSize(width: 400, height: 313))
        row.frame = CGRect(x: 0, y: 197, width: 350, height: 99)
        markdown.frame = CGRect(x: 30, y: 232, width: 290, height: 47)
        body.frame = markdown.frame
        scroll.contentView.scroll(to: .zero); scroll.reflectScrolledClipView(scroll.contentView)
        let clipped = try XCTUnwrap(observe())
        XCTAssertEqual(clipped.markdown, 1); XCTAssertGreaterThan(clipped.textViews, 0)
        XCTAssertEqual(try XCTUnwrap(clipped.bottomGap), 73, accuracy: 0.01)
        XCTAssertFalse(clipped.ready, "A thin intersection with ready Markdown must not pass while the latest body is clipped below the viewport")
        scroll.contentView.scroll(to: CGPoint(x: 0, y: 73)); scroll.reflectScrolledClipView(scroll.contentView)
        XCTAssertTrue(try XCTUnwrap(observe()).ready)
        document.setFrameSize(CGSize(width: 400, height: 1200))
        scroll.contentView.scroll(to: CGPoint(x: 0, y: 700)); scroll.reflectScrolledClipView(scroll.contentView)
        XCTAssertNil(observe(),
            "An offscreen latest row must not pass just because its native view still exists")
    }

    func testLaterNoticeRequiresItsExactVisibleNativeLabelAndLoadedNumericMessage() throws {
        _ = NSApplication.shared
        let suite = "Relic.NoticeObservation." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        let model = Model(defaults: defaults)
        defer { model.stop(); defaults.removePersistentDomain(forName: suite) }
        let message = Node(["id": 81, "type": "message", "text": "Earlier latest message"])
        let notice = Node(["id": "e82", "type": "notice", "text": "A later quiet event"])
        model.messages = [message, notice]
        model.streamRows = [ConversationRow(id: "id:81#0", item: message, separator: nil, continued: false),
                            ConversationRow(id: "id:e82#0", item: notice, separator: nil, continued: false)]
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 400, height: 240), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let scroll = NSScrollView(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        let document = FlippedDocument(frame: CGRect(x: 0, y: 0, width: 400, height: 240))
        scroll.documentView = document; window.contentView = scroll; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let row = RenderReadiness.Probe(frame: CGRect(x: 0, y: 180, width: 350, height: 36))
        row.kind = "conversation-row"; row.identity = "id:e82#0"; row.ready = true; document.addSubview(row)
        func observe(_ messageID: String = "81") -> PerformanceNavigation.LatestObservation? {
            PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: messageID, expectedItemID: "e82", expectedItemKind: "notice")
        }
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "81", expectedItemID: "81", expectedItemKind: "message"),
            "The earlier numeric message cannot stand in for the actual displayed tail")
        XCTAssertNil(PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "81", expectedItemID: "e82", expectedItemKind: "message"))
        XCTAssertFalse(try XCTUnwrap(observe()).ready, "An admitted notice row alone is not visible notice text")
        let generic = NSTextView(frame: CGRect(x: 20, y: 184, width: 300, height: 24))
        generic.string = "A later quiet event"; generic.isEditable = false; document.addSubview(generic)
        XCTAssertFalse(try XCTUnwrap(observe()).ready, "A generic text view must not substitute for the production ReferenceLabelView")
        generic.removeFromSuperview()
        let label = ReferenceLabel("Wrong event text").makeLabelView()
        label.productionRegion = "conversation"; label.frame = CGRect(x: 20, y: 184, width: 300, height: 24); document.addSubview(label)
        XCTAssertFalse(try XCTUnwrap(observe()).ready, "A date, header or other notice must not satisfy the tail text check")
        label.string = "A later quiet event"
        let ready = try XCTUnwrap(observe())
        XCTAssertTrue(ready.ready); XCTAssertEqual(ready.messageID, "81")
        XCTAssertEqual(ready.itemID, "e82"); XCTAssertEqual(ready.itemKind, "notice"); XCTAssertEqual(ready.rowID, "id:e82#0")
        XCTAssertEqual(ready.markdown, 0); XCTAssertEqual(ready.noticeLabels, 1)
        XCTAssertTrue(ready.messageLoaded); XCTAssertTrue(ready.itemLoaded)
        XCTAssertEqual(try XCTUnwrap(ready.bottomGap), 0, accuracy: 0.01)
        label.isHidden = true
        XCTAssertFalse(try XCTUnwrap(observe()).ready)
        label.isHidden = false
        model.messages = [notice]
        let missingMessage = try XCTUnwrap(observe())
        XCTAssertFalse(missingMessage.ready); XCTAssertFalse(missingMessage.messageLoaded); XCTAssertTrue(missingMessage.itemLoaded)
        XCTAssertTrue(try XCTUnwrap(observe("")).ready, "Explicit fixture null is valid for a notice-only page")
        model.messages = [message, notice]
        XCTAssertFalse(try XCTUnwrap(observe("")).ready, "Explicit no-message truth must reject a page containing a numeric message")
        model.messages = [message]
        let missingNotice = try XCTUnwrap(observe())
        XCTAssertFalse(missingNotice.ready); XCTAssertTrue(missingNotice.messageLoaded); XCTAssertFalse(missingNotice.itemLoaded)
        model.messages = [message, notice]
        document.setFrameSize(CGSize(width: 400, height: 313))
        row.frame = CGRect(x: 0, y: 224, width: 350, height: 36)
        label.frame = CGRect(x: 20, y: 232, width: 300, height: 24)
        scroll.contentView.scroll(to: .zero); scroll.reflectScrolledClipView(scroll.contentView)
        let clipped = try XCTUnwrap(observe())
        XCTAssertEqual(clipped.noticeLabels, 1); XCTAssertEqual(try XCTUnwrap(clipped.bottomGap), 73, accuracy: 0.01)
        XCTAssertFalse(clipped.ready, "A partially visible notice cannot pass while the native viewport has not reached the end")
        scroll.contentView.scroll(to: CGPoint(x: 0, y: 73)); scroll.reflectScrolledClipView(scroll.contentView)
        XCTAssertTrue(try XCTUnwrap(observe()).ready)
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
        func observe() -> PerformanceNavigation.LatestObservation? {
            PerformanceNavigation.observeLatest(model: model, window: window, expectedMessageID: "", expectedItemID: "", expectedItemKind: "", expectedEmpty: true)
        }
        XCTAssertFalse(try XCTUnwrap(observe()).ready)
        let empty = ReferenceLabel("No group messages").makeLabelView()
        empty.productionRegion = "conversation"; empty.frame = CGRect(x: 20, y: 30, width: 260, height: 30); root.addSubview(empty)
        XCTAssertTrue(try XCTUnwrap(observe()).ready)
        empty.isHidden = true
        XCTAssertFalse(try XCTUnwrap(observe()).ready)
    }

    private final class FlippedDocument: NSView { override var isFlipped: Bool { true } }
}
