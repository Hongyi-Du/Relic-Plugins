import XCTest
import AppKit
import SwiftUI
import RelicAX
import RelicCore
@testable import Relic

@MainActor final class MessageReadingOrderTests: XCTestCase {
    private struct CompleteMessages: View {
        var body: some View {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(0..<2) { index in
                        let priority = Double((2 - index) * 2)
                        MessageView(item: Node(["id": "test-\(index)", "type": "message", "from": "human",
                            "fromLabel": "Metadata \(index)", "text": "Body \(index)"]),
                            readingOrderPriority: priority).accessibilitySortPriority(priority)
                    }
                }.padding(20)
            }.frame(width: 600, height: 280)
        }
    }
    func testCompleteMessageViewsKeepTheAvatarBeforeTheirMetadataAndRichText() async throws {
        _ = NSApplication.shared
        let model = Model(); model.preferences = Node(["name": "Hongyi Du", "avatar": "initials"])
        let host = NSHostingView(rootView: CompleteMessages().environmentObject(model))
        host.frame = NSRect(x: 0, y: 0, width: 600, height: 280)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); CATransaction.flush()
        try await Task.sleep(for: .milliseconds(80))
        var seen = Set<ObjectIdentifier>(), names: [String] = []
        func walk(_ object: AnyObject) {
            guard seen.insert(ObjectIdentifier(object)).inserted else { return }
            let values = RelicAXRead(object)
            if values["element"] as? Bool == true {
                let label = values["label"] as? String ?? "", value = values["value"] as? String ?? ""
                let name = label.isEmpty ? value : label
                if name == "H" || name.hasPrefix("Metadata ") || name.hasPrefix("Body ") { names.append(name) }
            }
            for child in RelicAXChildren(object) { walk(child as AnyObject) }
            if let view = object as? NSView { for child in view.subviews { walk(child) } }
        }
        walk(host)
        if names != ["H", "Metadata 0", "Body 0", "H", "Metadata 1", "Body 1"] {
            var diagnostics: [[String: Any]] = []
            for anchor in MessageInteractionAnchor.live.allObjects where anchor.window === window {
                let scroll = anchor.enclosingScrollView
                var record: [String: Any] = ["message": anchor.messageID,
                    "avatar_identifier": anchor.avatarNavigationID as Any? ?? NSNull(),
                    "metadata_identifier": anchor.metadataNavigationID as Any? ?? NSNull(),
                    "attempts": anchor.navigationAttempts, "setter_accepted": anchor.navigationSucceeded as Any? ?? NSNull(),
                    "mounted_scroll": scroll.map { String(describing: type(of: $0)) } as Any? ?? NSNull()]
                if let scroll {
                    let snapshot = RelicAXChildSnapshot(scroll)
                    record["order_evidence"] = snapshot["evidence"]
                    record["children"] = (snapshot["children"] as? [Any] ?? []).map { child -> [String: Any] in
                        let value = RelicAXRead(child as AnyObject)
                        return ["class": String(describing: type(of: child as AnyObject)),
                            "identifier": value["identifier"] ?? NSNull(), "label": value["label"] ?? NSNull()]
                    }
                }
                diagnostics.append(record)
            }
            let directory = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
                .deletingLastPathComponent().appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: diagnostics, options: [.sortedKeys])
                .write(to: directory.appendingPathComponent("complete-message-navigation.json"))
            print("Complete message navigation: " + String(decoding: try JSONSerialization.data(withJSONObject: diagnostics, options: [.sortedKeys]), as: UTF8.self))
        }
        XCTAssertEqual(names, ["H", "Metadata 0", "Body 0", "H", "Metadata 1", "Body 1"],
            "Exercise the complete production row, RichText, interaction modifiers and ScrollView, not a label-only proxy")
    }
    private struct ProductionRows: View {
        let absoluteAvatarPriority: Bool
        var body: some View {
            VStack(spacing: 12) {
                ForEach(0..<2) { index in
                    let priority = Double((2 - index) * 2)
                    MessageColumns(mine: true) {
                        Avatar(member: "human", size: 36)
                            .accessibilitySortPriority(absoluteAvatarPriority ? priority + 0.5 : 1)
                        VStack(alignment: .trailing, spacing: 4) {
                            ReferenceLabel("Metadata \(index)", size: 12.5, lines: 0)
                            ReferenceLabel("Body \(index)", size: 14, lines: 0).padding(8)
                                .modifier(RecordedSurface(background: RelicStyle.bubble, radius: 14, kind: "card"))
                        }.frame(maxWidth: .infinity, alignment: .trailing)
                    }.accessibilitySortPriority(priority)
                }
            }.frame(width: 320)
        }
    }
    func testProductionAvatarContainerUsesItsSourceRowPriorityWithoutChangingInventory() async throws {
        _ = NSApplication.shared
        let model = Model(); model.preferences = Node(["name": "Hongyi Du", "avatar": "initials"])
        var inventories: [[String]] = [], orders: [[String]] = []
        for absolute in [false, true] {
            let host = NSHostingView(rootView: ProductionRows(absoluteAvatarPriority: absolute).environmentObject(model))
            host.frame = NSRect(x: 0, y: 0, width: 320, height: 150)
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
                    let label = values["label"] as? String ?? "", value = values["value"] as? String ?? ""
                    let name = label.isEmpty ? value : label
                    inventory.append(role + ":" + name)
                    if name == "H" || name.hasPrefix("Metadata ") || name.hasPrefix("Body ") { names.append(name) }
                }
                for child in RelicAXChildren(object) { walk(child as AnyObject) }
                if let view = object as? NSView { for child in view.subviews { walk(child) } }
            }
            walk(host); inventories.append(inventory.sorted()); orders.append(names)
        }
        XCTAssertEqual(inventories[1], inventories[0])
        XCTAssertEqual(orders[1], ["H", "Metadata 0", "Body 0", "H", "Metadata 1", "Body 1"],
            "Actual Avatar/metadata/card navigation, baseline and candidate: \(orders)")
    }
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
