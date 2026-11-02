import XCTest
import AppKit
import SwiftUI
import RelicCore
@testable import Relic

@MainActor final class ConversationNavigationTests: XCTestCase {
    func testNavigationReusesNativeViewportAndShowsEachNewChatTail() async throws {
        _ = NSApplication.shared
        let suite = "Relic.ConversationNavigation." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let model = Model(defaults: defaults)
        model.organization = "first"
        let host = NSHostingView(rootView: NavigationFixture(model: model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 600),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func views(_ root: NSView) -> [NSView] { [root] + root.subviews.flatMap(views) }
        var originalScroll: NSScrollView?, originalEditor: NSTextView?
        for (index, selection) in [ChatSelection("first"), ChatSelection("first", "secretary"),
                                    ChatSelection("second"), ChatSelection("first")].enumerated() {
            model.setSelection(selection)
            // Allow the actual empty/pending snapshot to be laid out between
            // navigation and its asynchronous response, as it is in the app.
            try await Task.sleep(for: .milliseconds(100))
            model.snapshot = Node(["org": ["id": selection.org, "name": selection.org],
                "members": [["name": "secretary", "state": "idle"]]] as [String: Any])
            let tail = "Actual latest message for navigation \(index)"
            let count = [1_063, 24, 1_016, 1_063][index]
            let longPredecessor = String(repeating: "Long **Markdown** paragraph while switching organizations.\n\n", count: 45)
            model.messages = (1...count).map { number in
                Node(["id": index * 10_000 + number, "type": "message", "from": "human", "to": ["all"],
                    "text": number == count ? tail : number == count - 1 ? longPredecessor : "Message \(index)-\(number)",
                    "at": "2026-10-30T12:00:00Z"] as [String: Any])
            }
            let deadline = ProcessInfo.processInfo.systemUptime + 15
            var visibleTail = false, quiet = 0
            repeat {
                try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
                let all = views(host)
                if let scroll = all.compactMap({ $0 as? NSScrollView }).first(where: {
                    $0.accessibilityIdentifier() == ConversationKeyboard.identifier
                }) {
                    visibleTail = all.compactMap { $0 as? QuoteTextView }.contains {
                        $0.string == tail && $0.convert($0.bounds, to: scroll.contentView).intersects(scroll.contentView.bounds)
                    }
                }
                quiet = visibleTail && !model.isPreparingConversation && RowMountQueue.shared.isIdle ? quiet + 1 : 0
            } while quiet < 3 && ProcessInfo.processInfo.systemUptime < deadline
            XCTAssertGreaterThanOrEqual(quiet, 3, "Navigation \(index) must draw its own actual latest text")
            let all = views(host)
            let scroll = try XCTUnwrap(all.compactMap { $0 as? NSScrollView }.first {
                $0.accessibilityIdentifier() == ConversationKeyboard.identifier
            })
            let editor = try XCTUnwrap(all.compactMap { $0 as? NSTextView }.first { $0.isEditable })
            if let originalScroll, let originalEditor {
                XCTAssertTrue(scroll === originalScroll, "Navigation must retain native scrolling and focus handling")
                XCTAssertTrue(editor === originalEditor, "Navigation must retain the native composer")
            } else { originalScroll = scroll; originalEditor = editor }
            XCTAssertEqual(ConversationKeyboardMount.bottomGap(in: window) ?? -1, 0, accuracy: 2)
        }
    }
    private struct NavigationFixture: View {
        let model: Model
        var body: some View {
            ChatView().environmentObject(model).disabled(model.snapshot["org"].isNull)
        }
    }
}
