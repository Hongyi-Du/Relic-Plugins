import XCTest
import AppKit
import SwiftUI
import RelicAX
@testable import Relic

@MainActor final class MessageReadingOrderTests: XCTestCase {
    private struct Rows: View {
        let ordered: Bool
        var body: some View {
            VStack(spacing: 12) {
                ForEach(0..<2) { index in
                    MessageColumns(mine: true) {
                        ReferenceLabel("Avatar \(index)", size: 12).frame(width: 36, height: 36)
                            .accessibilitySortPriority(ordered ? 1 : 0)
                        ReferenceLabel("Message \(index)", size: 14, lines: 0).frame(maxWidth: .infinity, alignment: .leading)
                    }.accessibilitySortPriority(ordered ? Double(2 - index) : 0)
                }
            }.frame(width: 320)
        }
    }
    func testSourceRowPrioritiesKeepEachAvatarBeforeItsMessageWithoutNewElements() async throws {
        _ = NSApplication.shared
        var inventories: [[String]] = [], orders: [[String]] = []
        for ordered in [false, true] {
            let host = NSHostingView(rootView: Rows(ordered: ordered))
            host.frame = NSRect(x: 0, y: 0, width: 320, height: 120)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
            defer { window.orderOut(nil); window.contentView = nil; window.close() }
            host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); CATransaction.flush()
            try await Task.sleep(for: .milliseconds(80))
            var seen = Set<ObjectIdentifier>(), names: [String] = [], inventory: [String] = []
            func walk(_ object: AnyObject) {
                guard seen.insert(ObjectIdentifier(object)).inserted else { return }
                let values = RelicAXRead(object), role = values["role"] as? String ?? ""
                if values["element"] as? Bool == true {
                    let label = values["label"] as? String ?? ""
                    let value = values["value"] as? String ?? ""
                    let name = label.isEmpty ? value : label
                    inventory.append(role + ":" + name)
                    if name.hasPrefix("Avatar ") || name.hasPrefix("Message ") { names.append(name) }
                }
                for child in RelicAXChildren(object) { walk(child as AnyObject) }
                if let view = object as? NSView { for child in view.subviews { walk(child) } }
            }
            walk(host); inventories.append(inventory.sorted()); orders.append(names)
        }
        XCTAssertEqual(inventories[1], inventories[0], "Priorities must not introduce or hide a native accessible element")
        XCTAssertEqual(orders[1], ["Avatar 0", "Message 0", "Avatar 1", "Message 1"], "Actual baseline and candidate navigation: \(orders)")
    }
}
