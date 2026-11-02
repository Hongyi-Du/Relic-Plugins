import AppKit
import RelicCore

enum PerformancePhase: String {
    case legacy, openEveryChat = "open-every-chat", history, idle, switchChats = "switch-chats", workflows, monkey
    init(manifest: Node) throws {
        let value = manifest["phase"].text
        if !value.isEmpty && manifest["version"].integer != 2 || value.isEmpty && manifest["version"].integer >= 2 {
            throw RelicError.message("Native phase execution requires manifest version 2 and an explicit phase")
        }
        let parsed: PerformancePhase? = value.isEmpty ? .legacy : Self(rawValue: value)
        guard let phase = parsed else {
            throw RelicError.message("Unknown native performance phase: " + value)
        }
        self = phase
    }
    var usesPointerNavigation: Bool { self == .openEveryChat || self == .switchChats }
    var continuesFailedActions: Bool { usesPointerNavigation }
    var runsMonkey: Bool { self == .legacy || self == .monkey }
}

/// CI drives the real sidebar and observes existing native content. There is
/// deliberately no select/load/scroll-to-latest fallback in this driver.
@MainActor enum PerformanceNavigation {
    static let openLimitMilliseconds = 1000.0
    static func open(_ action: Node, phase: PerformancePhase, model: Model, window: NSWindow) async -> [String: Any] {
        let started = ProcessInfo.processInfo.systemUptime
        var result = action.object
        var setup: [[String: Any]] = [], errors: [String] = []
        var handled: PerformancePointer.HandledClick?
        var observation: LatestObservation?
        var before = model.selection
        let target = ChatSelection(action["org"].text, action["kind"].text == "private" ? action["member"].text : "")
        let truth = action["latest_message_id"].text, expectedEmpty = action["expected_empty"].flag
        let independentTruth = !action["expected_empty"].isNull && (expectedEmpty || !truth.isEmpty && truth != "0")
        result["expected_latest_id"] = truth
        result["expected_latest_source"] = independentTruth ? "fixture_manifest" : "missing_fixture_truth"
        result["amendment9_eligible"] = independentTruth
        do {
            guard !target.org.isEmpty else { throw RelicError.message("Sidebar navigation requires an organization") }
            if !model.sidebarOpen { _ = try await inject(window, target: "sidebar") }
            model.appMenu = nil; model.sheet = nil
            guard model.search.isEmpty else { throw RelicError.message("Sidebar search must be empty before the navigation phase") }
            if phase == .switchChats, !action["warmup"].flag, model.selection == target {
                throw RelicError.message("A measured switch-chats action must change the actual selected chat")
            }
            // The active organization button folds its tree. An already-open
            // target cannot be counted as a zero-millisecond successful open.
            if action["kind"].text == "organization" && model.organization == target.org {
                guard let alternate = model.organizations.first(where: { $0["id"].text != target.org })?["id"].text else {
                    throw RelicError.message("No different organization is available to prepare a real navigation")
                }
                try await revealOrganization(alternate, model: model, window: window, receipts: &setup)
                try await setupOrganization(alternate, model: model, window: window, receipts: &setup)
            }
            try await revealOrganization(target.org, model: model, window: window, receipts: &setup)
            let pointerTarget: String
            if action["kind"].text == "organization" {
                pointerTarget = PerformancePointer.organization(target.org)
            } else {
                if model.organization != target.org {
                    try await setupOrganization(target.org, model: model, window: window, receipts: &setup)
                }
                if model.folded.contains(target.org) {
                    try await revealTarget(PerformancePointer.organization(target.org), in: window)
                    let opened = try await inject(window, target: PerformancePointer.organization(target.org))
                    setup.append(["pointer_target": PerformancePointer.organization(target.org), "click_events": 1,
                                  "handled_unix_ms": opened.unixMilliseconds, "purpose": "expand-selected-organization"])
                }
                if target.member.isEmpty, model.selection == target,
                   let alternate = model.members.first(where: { !$0["name"].text.isEmpty })?["name"].text {
                    // The group row is a separate control from its organization
                    // header. Reveal it, then leave the group via an actual
                    // private-row click so the measured group click really opens it.
                    let privateTarget = PerformancePointer.chat(target.org, alternate)
                    try await revealTarget(privateTarget, in: window)
                    let version = model.selectedChatLoadVersion
                    let opened = try await inject(window, target: privateTarget)
                    let deadline = ProcessInfo.processInfo.systemUptime + 15
                    while model.selection != ChatSelection(target.org, alternate) || model.selectedChatLoadVersion <= version || model.isLoadingSelectedChat || model.isPreparingConversation {
                        guard ProcessInfo.processInfo.systemUptime < deadline else { throw RelicError.message("Private-row setup for the separate group-row click did not complete") }
                        try await Task.sleep(for: .milliseconds(20))
                    }
                    setup.append(["pointer_target": privateTarget, "click_events": 1, "handled_unix_ms": opened.unixMilliseconds,
                        "purpose": "prepare-separate-group-row", "elapsed_ms": (ProcessInfo.processInfo.systemUptime - opened.uptime) * 1000])
                }
                pointerTarget = PerformancePointer.chat(target.org, target.member)
            }
            let positioningStarted = ProcessInfo.processInfo.systemUptime
            try await revealTarget(pointerTarget, in: window)
            result["sidebar_positioning_ms"] = (ProcessInfo.processInfo.systemUptime - positioningStarted) * 1000
            result["preparation_ms"] = (ProcessInfo.processInfo.systemUptime - started) * 1000
            before = model.selection
            if phase == .switchChats, !action["warmup"].flag, before == target {
                throw RelicError.message("The measured sidebar click must switch away from a different actual chat")
            }
            let loadVersion = model.selectedChatLoadVersion
            result["pointer_target"] = pointerTarget
            handled = try await inject(window, target: pointerTarget)
            let click = handled!
            result["click_events"] = 1
            result["click_handled_unix_ms"] = click.unixMilliseconds
            // Observe promptly; waiting for unrelated inspector/surface tasks
            // or a fixed quiet period would change this into a settle metric.
            let deadline = click.uptime + 15
            repeat {
                if model.selection == target, model.selectedChatLoadVersion > loadVersion,
                   !model.isLoadingSelectedChat, !model.isPreparingConversation,
                   let latest = observeLatest(model: model, window: window, expected: truth, expectedEmpty: expectedEmpty) {
                    observation = latest
                    if latest.ready {
                        let elapsed = (ProcessInfo.processInfo.systemUptime - click.uptime) * 1000
                        result["open_ms"] = elapsed
                        if elapsed > openLimitMilliseconds { errors.append("Actual latest content appeared after 1000 ms: \(elapsed) ms") }
                        break
                    }
                }
                try await Task.sleep(for: .milliseconds(10))
            } while ProcessInfo.processInfo.systemUptime < deadline
            if observation?.ready != true { throw RelicError.message("The requested chat's actual latest content did not become visible") }
            if !independentTruth { errors.append("Missing independent fixture latest_message_id/expected_empty; projection alone cannot prove Amendment 9 acceptance") }
        } catch { errors.append(String(describing: error)) }
        if let observation {
            result["visible_latest_id"] = observation.messageID
            result["visible_latest_row_id"] = observation.rowID
            result["visible_latest_markdown"] = observation.markdown
            result["visible_latest_text_views"] = observation.textViews
            if let gap = observation.bottomGap { result["visible_latest_bottom_gap_pt"] = Double(gap) }
            else { result["visible_latest_bottom_gap_pt"] = NSNull() }
        }
        result["latest_visible"] = observation?.ready == true
        if handled == nil { result["click_events"] = 0 }
        result["preparation_clicks"] = setup
        result["selection_before"] = before.key; result["selection_after"] = model.selection.key
        result["did_switch"] = handled != nil && before != target && model.selection == target
        result["passed"] = errors.isEmpty
        result["errors"] = errors
        result["elapsed_ms"] = (ProcessInfo.processInfo.systemUptime - started) * 1000
        return result
    }

    struct LatestObservation {
        let messageID: String, rowID: String
        let markdown: Int, textViews: Int
        let bottomGap: CGFloat?
        let ready: Bool
    }
    static func observeLatest(model: Model, window: NSWindow, expected: String, expectedEmpty: Bool = false) -> LatestObservation? {
        guard let root = window.contentView else { return nil }
        if expectedEmpty {
            guard model.messages.isEmpty, model.streamRows.isEmpty, model.displayLiveItems.isEmpty else { return nil }
            let label = model.t(model.member.isEmpty ? "chat.empty_group" : "chat.empty_private")
            let actual = descendants(root).compactMap { $0 as? ReferenceLabelView }.filter {
                $0.productionRegion == "conversation" && !label.isEmpty && $0.string == label && visible($0)
            }
            return LatestObservation(messageID: "", rowID: "", markdown: 0, textViews: actual.count, bottomGap: nil, ready: !actual.isEmpty)
        }
        guard let row = model.streamRows.last else { return nil }
        let messageID = row.item["id"].text
        guard !messageID.isEmpty, expected.isEmpty || expected == messageID else { return nil }
        let native = descendants(root)
        guard let probe = native.compactMap({ $0 as? RenderReadiness.Probe }).first(where: {
            $0.kind == "conversation-row" && $0.identity == row.id && $0.visibleInViewport
        }) else { return nil }
        let rowBounds = probe.convert(probe.bounds, to: root)
        let markdown = native.compactMap { $0 as? RenderReadiness.Probe }.filter {
            $0.kind == "markdown" && $0.visibleInViewport && intersects($0, row: rowBounds, root: root)
        }
        let text = native.compactMap { $0 as? NSTextView }.filter {
            !$0.isEditable && !$0.string.isEmpty && visible($0) && intersects($0, row: rowBounds, root: root)
        }
        let body = row.item["body"].text.isEmpty ? row.item["text"].text : row.item["body"].text
        let requiresMarkdown = !body.isEmpty && !["notice", "acts", "receipt"].contains(row.item["type"].text)
        // A header or an admitted row placeholder is not message content.
        let actualBody = requiresMarkdown ? !markdown.isEmpty && text.contains(where: { $0 is QuoteTextView }) : !text.isEmpty
        var bottomGap: CGFloat?
        if let scroll = probe.enclosingScrollView, let document = scroll.documentView {
            let clip = scroll.contentView.bounds
            let gap = document.isFlipped ? document.bounds.maxY - clip.maxY : clip.minY - document.bounds.minY
            if gap.isFinite { bottomGap = max(0, gap) }
        }
        // A few pixels of a ready text view can intersect the viewport while
        // its readable body remains behind the composer. Require the actual
        // native end as well as the independent ID and native content checks.
        return LatestObservation(messageID: messageID, rowID: row.id, markdown: markdown.count, textViews: text.count,
            bottomGap: bottomGap, ready: actualBody && markdown.allSatisfy(\.ready) && bottomGap.map { $0 <= 2 } == true)
    }
    private static func intersects(_ view: NSView, row: CGRect, root: NSView) -> Bool {
        let overlap = view.convert(view.bounds, to: root).intersection(row)
        return !overlap.isNull && overlap.width > 1 && overlap.height > 1
    }
    private static func visible(_ view: NSView) -> Bool {
        guard !view.isHiddenOrHasHiddenAncestor else { return false }
        var rect = view.bounds, ancestor = view.superview
        while let parent = ancestor {
            if parent is NSClipView || parent.clipsToBounds { rect = rect.intersection(view.convert(parent.bounds, from: parent)) }
            ancestor = parent.superview
        }
        if let root = view.window?.contentView { rect = rect.intersection(view.convert(root.bounds, from: root)) }
        return !rect.isNull && rect.width > 1 && rect.height > 1
    }
    private static func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }

    private static func revealOrganization(_ id: String, model: Model, window: NSWindow, receipts: inout [[String: Any]]) async throws {
        var ancestors: [String] = [], cursor = id, visited: Set<String> = []
        while let parent = model.organizations.first(where: { $0["id"].text == cursor })?["parent"].text,
              !parent.isEmpty, visited.insert(parent).inserted { ancestors.insert(parent, at: 0); cursor = parent }
        for ancestor in ancestors where model.folded.contains(ancestor) {
            try await setupOrganization(ancestor, model: model, window: window, receipts: &receipts)
        }
    }
    private static func setupOrganization(_ id: String, model: Model, window: NSWindow, receipts: inout [[String: Any]]) async throws {
        let target = PerformancePointer.organization(id)
        try await revealTarget(target, in: window)
        let click = try await inject(window, target: target)
        let deadline = ProcessInfo.processInfo.systemUptime + 15
        repeat {
            if model.organization == id, !model.snapshot["org"].isNull, !model.isPreparingConversation, !model.folded.contains(id) { break }
            guard ProcessInfo.processInfo.systemUptime < deadline else { throw RelicError.message("Sidebar organization setup did not complete: " + id) }
            try await Task.sleep(for: .milliseconds(20))
        } while true
        receipts.append(["pointer_target": target, "click_events": 1, "handled_unix_ms": click.unixMilliseconds,
                         "purpose": "prepare-sidebar-target", "elapsed_ms": (ProcessInfo.processInfo.systemUptime - click.uptime) * 1000])
    }
    static func revealTarget(_ target: String, in window: NSWindow) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + 15
        var searchingFromTop = false
        repeat {
            if let probe = PerformancePointer.mount(target, in: window) {
                if probe.clippedBounds.height >= min(20, probe.bounds.height), probe.clippedBounds.width > 20 { return }
                _ = probe.scrollToVisible(probe.bounds)
            } else if let root = window.contentView,
                      let scroll = descendants(root).compactMap({ $0 as? NSScrollView }).first(where: { $0.accessibilityIdentifier() == "relic-performance-sidebar" }),
                      let document = scroll.documentView {
                // Let the actual lazy rows at this viewport finish mounting
                // before paging past them. This is untimed target positioning,
                // not an extension of the one-second post-click requirement.
                if !RowMountQueue.shared.isIdle {
                    try await Task.sleep(for: .milliseconds(50)); continue
                }
                let clip = scroll.contentView, maximum = max(0, document.frame.height - clip.bounds.height)
                var offset = clip.bounds.origin.y
                if !searchingFromTop { offset = document.isFlipped ? 0 : maximum; searchingFromTop = true }
                else { offset += (document.isFlipped ? 1 : -1) * max(40, clip.bounds.height * 0.65) }
                offset = max(0, min(maximum, offset))
                clip.scroll(to: NSPoint(x: clip.bounds.origin.x, y: offset)); scroll.reflectScrolledClipView(clip)
            }
            try await Task.sleep(for: .milliseconds(50))
        } while ProcessInfo.processInfo.systemUptime < deadline
        throw RelicError.message("Native sidebar target did not become visible: " + target)
    }
    static func inject(_ window: NSWindow, target: String) async throws -> PerformancePointer.HandledClick {
        guard let probe = PerformancePointer.mount(target, in: window), probe.clippedBounds.width > 1, probe.clippedBounds.height > 1 else {
            throw RelicError.message("Native pointer target is not actually visible: " + target)
        }
        let before = PerformancePointer.clicks[target, default: 0]
        let visible = probe.clippedBounds
        let point = probe.convert(NSPoint(x: visible.midX, y: visible.midY), to: nil)
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            guard let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0) else {
                throw RelicError.message("Could not create native sidebar mouse event")
            }
            NSApp.postEvent(event, atStart: false)
        }
        let deadline = ProcessInfo.processInfo.systemUptime + 2
        repeat {
            if let click = PerformancePointer.handled[target], click.count > before { return click }
            try await Task.sleep(for: .milliseconds(5))
        } while ProcessInfo.processInfo.systemUptime < deadline
        throw RelicError.message("The production sidebar Button did not handle the injected click: " + target)
    }
}
