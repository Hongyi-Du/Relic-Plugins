import SwiftUI
import RelicCore

/// The contiguous slice of the prepared conversation that the native List
/// holds. Loaded history can be thousands of rows; a chat switch, a history
/// page or a jump to either end must only insert and remove a few dozen rows,
/// never the whole loaded history in one AppKit table update.
struct ConversationWindow: Equatable {
    static let initial = 24, page = 16, maximum = 72
    /// The chat this window belongs to. Another chat starts at its own tail.
    var selection = ""
    /// First shown row while reading history; `nil` keeps the newest rows.
    var anchor: String?
    var count = ConversationWindow.initial

    func range(in rows: [ConversationRow], selection current: String) -> Range<Int> {
        guard !rows.isEmpty else { return 0..<0 }
        guard current == selection else { return max(0, rows.count - Self.initial)..<rows.count }
        let size = min(max(1, count), Self.maximum)
        if let anchor, let start = rows.firstIndex(where: { $0.id == anchor }) {
            return start..<min(rows.count, start + size)
        }
        return max(0, rows.count - size)..<rows.count
    }
    /// Show exactly `range`; a range that ends at the newest row keeps following new rows.
    static func showing(_ range: Range<Int>, in rows: [ConversationRow], selection: String) -> ConversationWindow {
        guard !range.isEmpty else { return ConversationWindow(selection: selection) }
        return ConversationWindow(selection: selection, anchor: range.upperBound == rows.count ? nil : rows[range.lowerBound].id,
                                  count: range.count)
    }
    /// Keep the same rows even when newer rows arrive below them.
    static func pinned(_ range: Range<Int>, in rows: [ConversationRow], selection: String) -> ConversationWindow {
        guard !range.isEmpty else { return ConversationWindow(selection: selection) }
        return ConversationWindow(selection: selection, anchor: rows[range.lowerBound].id, count: range.count)
    }
}

/// AppKit-backed List owns row recycling and variable-height placement. The
/// application supplies a bounded window of identities and reading intent,
/// never virtual offsets.
struct ConversationStream: View {
    @EnvironmentObject var m: Model
    @Environment(\.isEnabled) private var enabled
    @FocusState private var viewportFocused: Bool
    @State private var keyboard = ConversationKeyboard()
    @State private var followsLatest = true
    @State private var preservingDisclosure = false
    @State private var mountedViewport = false
    @State private var mountedRows = false
    @State private var mountedComposer = false
    @State private var window = ConversationWindow()
    /// Where the viewport must be after the next window/content update.
    @State private var reveal: Reveal?
    @State private var revealRequest = 0
    /// The oldest loaded row when an earlier server page was requested.
    @State private var olderRequest: String?
    /// Home keeps the actual first row at the top until the person scrolls or
    /// a page arrives, even when AppKit restores an offset after the update.
    @State private var pinsTop = false
    /// Rows the List holds. They are adopted one turn after the model
    /// publishes them, so a chat switch's sidebar, inspector and header
    /// update and the List's row replacement are separate UI transactions.
    @State private var presented: [ConversationRow] = []
    @State private var presentedKey = ""
    private enum Reveal: Equatable { case top(String), bottom(String), start, latest }
    private struct UpdateKey: Hashable {
        let selection: String, version: Int, enabled: Bool, window: String, request: Int
    }
    private var latestID: String? { m.displayLiveItems.isEmpty ? presented.last?.id : "live-end" }
    private var shownRange: Range<Int> { window.range(in: presented, selection: m.selection.key) }

    var body: some View {
        ScrollViewReader { proxy in
            VStack(spacing: 0) {
                if mountedViewport {
                    let all = presented
                    let range = window.range(in: all, selection: m.selection.key)
                    List {
                        Color.clear.frame(height: 8).id("start").accessibilityHidden(true)
                            .background(mount)
                            .listRowInsets(EdgeInsets()).listRowSeparator(.hidden).listRowBackground(Color.clear)
                        let rows = mountedRows ? Array(all[range]) : []
                        let hasLive = mountedRows && range.upperBound == all.count && !m.displayLiveItems.isEmpty
                        let compact = m.preferences["density"].text == "compact"
                        let last = hasLive ? "live-end" : all.last?.id
                        if mountedRows && all.isEmpty && m.streamRows.isEmpty && !hasLive {
                            NoticeLayout {
                                ReferenceLabel(m.t(m.member.isEmpty ? "chat.empty_group" : "chat.empty_private"),
                                    size: 12, color: RelicStyle.muted, lines: 0, alignment: .center)
                                    .padding(.horizontal, 10).padding(.vertical, 2)
                                    .modifier(RecordedSurface(background: RelicStyle.sidebar, radius: 10, kind: "card"))
                            }.padding(.top, 40).padding(.bottom, 32).background(mount)
                                .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 0, trailing: 20))
                                .listRowSeparator(.hidden).listRowBackground(Color.clear)
                        }
                        ForEach(rows) { row in
                            // List can discover all IDs without evaluating the
                            // conditional admission content for every message.
                            // One explicit container always means one row;
                            // ForEach already supplies its scroll identity.
                            VStack(alignment: .leading, spacing: 0) {
                            ProgressiveRow(estimatedHeight: row.item["type"].text == "notice" ? 32 : 100) {
                                VStack(alignment: .leading, spacing: 0) {
                                    if let separator = row.separator {
                                        PlainLabel(separator, size: 11.5, color: RelicStyle.muted).lineLimit(1)
                                            .frame(maxWidth: .infinity).padding(.top, 18)
                                            .padding(.bottom, ConversationSpacing.separatorBottom(kind: row.item["type"].text, continued: row.continued, compact: compact))
                                    }
                                    MessageView(item: row.item, continued: row.continued, preparedBody: row.preparedBody,
                                                clockLabel: row.clockLabel, dayTooltip: row.dayTooltip, timestampContext: row.timestampContext)
                                        .padding(.top, ["notice", "acts"].contains(row.item["type"].text) ? 0 : ConversationSpacing.messageTop(kind: row.item["type"].text, continued: row.continued, compact: compact))
                                }
                                .background { if RenderReadiness.enabled { RenderReadiness(kind: "conversation-row", identity: row.id) } }
                                .onAppear { PerformanceRendering.rowAppeared() }
                                .onDisappear { PerformanceRendering.rowDisappeared() }
                            }
                            }
                            .padding(.bottom, row.id == last ? 24 : 0)
                            .frame(maxWidth: 880).frame(maxWidth: .infinity)
                            .environment(\.rowMountPriority, row.id == last ? 20 : 10)
                            .background(mount)
                            .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 0, trailing: 20))
                            .listRowSeparator(.hidden).listRowBackground(Color.clear)
                        }
                        if hasLive {
                            LiveTurnView().padding(.bottom, 24).frame(maxWidth: 880).frame(maxWidth: .infinity)
                                .background(mount).id("live-end")
                                .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 0, trailing: 20))
                                .listRowSeparator(.hidden).listRowBackground(Color.clear)
                        }
                    }
                    .listStyle(.plain)
                    // AppKit rejects a zero rowHeight. Eight is the smallest
                    // real row here (the leading space), not a content cap.
                    .environment(\.defaultMinListRowHeight, 8)
                    .scrollContentBackground(.hidden)
                    .contentMargins(.all, 0, for: .scrollContent)
                    .modifier(RecordedSurface(background: .clear, kind: "region"))
                    .scrollDisabled(!enabled).focusable(enabled).focused($viewportFocused).focusEffectDisabled()
                    .onKeyPress(phases: [.down, .repeat]) { keyboard.handle($0.key, modifiers: $0.modifiers) }
                    .environment(\.conversationDisclosure, {
                        keyboard.preserveDisclosurePosition(); preservingDisclosure = true
                    })
                } else { Color.clear.frame(maxWidth: .infinity, maxHeight: .infinity) }
                if mountedComposer {
                    ComposerView {
                        followsLatest = true
                        m.run { try await m.send(); seekLatest(proxy) }
                    }.measuredRegion("composer")
                } else { Color.clear.frame(height: 100).accessibilityHidden(true) }
            }
            .task(id: UpdateKey(selection: m.selection.key, version: m.streamVersion, enabled: enabled,
                                window: (window.anchor ?? "latest") + "/\(window.count)/" + window.selection, request: revealRequest)) {
                guard enabled, !m.isPreparingConversation else { return }
                let ticket = PerformanceRendering.beginSurface()
                defer { PerformanceRendering.endSurface(ticket) }
                // Create the native table in its own turn before adopting the
                // first page. Cold AppKit list setup and the initial collection
                // diff otherwise share one uninterruptible display transaction.
                // Later chat switches retain both the table and row collection.
                for stage in 0..<3 {
                    if stage == 0 ? mountedViewport : stage == 1 ? mountedRows : mountedComposer { continue }
                    let turn = UUID()
                    guard await RowMountQueue.shared.acquire(turn, label: stage == 0 ? "conversation-viewport" : stage == 1 ? "conversation-rows" : "composer") else { return }
                    guard !Task.isCancelled else { RowMountQueue.shared.release(turn); return }
                    if stage == 0 { mountedViewport = true } else if stage == 1 { mountedRows = true } else { mountedComposer = true }
                    do { try await Task.sleep(for: .milliseconds(32)) }
                    catch { RowMountQueue.shared.release(turn); return }
                    RowMountQueue.shared.release(turn)
                }
                // Adopt the published rows in this later turn, then let the
                // List receive the changed collection before its one semantic
                // request. It retains the same native viewport.
                let key = m.selection.key + "#" + String(m.streamVersion) + "#" + String(m.streamRows.count)
                if presentedKey != key { presented = m.streamRows; presentedKey = key; await Task.yield() }
                await Task.yield()
                guard !Task.isCancelled else { return }
                // An earlier server page arrived above the oldest shown row:
                // show one page of it while the same row stays at the top.
                if revealRequestedOlderRows() { return }
                let target = reveal; reveal = nil
                switch target {
                case .top(let id): proxy.scrollTo(id, anchor: .top)
                case .bottom(let id): proxy.scrollTo(id, anchor: .bottom)
                case .start: proxy.scrollTo("start", anchor: .top)
                case .latest: seekLatest(proxy)
                case nil: if followsLatest { seekLatest(proxy) }
                }
            }
            .onChange(of: m.selection) {
                keyboard.discardDisclosurePosition(); followsLatest = true
                preservingDisclosure = false; keyboard.observedHeight = 0
                window = ConversationWindow(selection: m.selection.key); reveal = nil; olderRequest = nil; pinsTop = false
            }
            .onChange(of: m.streamVersion) {
                PerformanceRendering.observed(streamVersion: m.streamVersion)
                keyboard.discardDisclosurePosition(); preservingDisclosure = false
            }
            .onAppear {
                PerformanceRendering.observed(streamVersion: m.streamVersion)
                window = ConversationWindow(selection: m.selection.key)
                keyboard.positionObservation = {
                    let range = shownRange
                    return ["last_row_id": latestID as Any? ?? NSNull(), "follows_latest": followsLatest,
                            "initial": !mountedViewport, "enabled": enabled, "preparing": m.isPreparingConversation,
                            "window_start": range.lowerBound, "window_end": range.upperBound, "loaded_rows": m.streamRows.count]
                }
                keyboard.didUserScroll = { nearBottom in
                    let all = presented, range = window.range(in: all, selection: m.selection.key)
                    followsLatest = nearBottom && range.upperBound == all.count
                    preservingDisclosure = false; pinsTop = false
                    if followsLatest, window.anchor != nil {
                        window = .showing(range, in: all, selection: m.selection.key)
                    } else if !followsLatest, window.anchor == nil, !range.isEmpty {
                        // A person reading earlier rows keeps them in place;
                        // arrivals below are shown when they reach the end.
                        window = .pinned(range, in: all, selection: m.selection.key)
                    }
                }
                keyboard.scrollToEdge = { top in
                    preservingDisclosure = false; olderRequest = nil
                    let all = presented, key = m.selection.key
                    if top {
                        followsLatest = false; pinsTop = true
                        let end = min(all.count, ConversationWindow.initial)
                        request(.start, window: end < all.count ? ConversationWindow.pinned(0..<end, in: all, selection: key) : ConversationWindow.showing(0..<end, in: all, selection: key))
                    } else {
                        followsLatest = true; pinsTop = false
                        request(.latest, window: ConversationWindow(selection: key))
                    }
                }
                keyboard.geometryChanged = { geometry in
                    let changed = abs(keyboard.observedHeight - geometry.height) > 1
                        || abs(keyboard.observedViewportHeight - geometry.viewportHeight) > 1
                    keyboard.observedHeight = geometry.height
                    keyboard.observedViewportHeight = geometry.viewportHeight
                    keyboard.finishDisclosureLayout()
                    // List can preserve the actual bottom itself while a row
                    // replaces its placeholder or changes height. Reissuing a
                    // semantic seek there starts another row/layout update.
                    if changed, geometry.bottomGap > 1, followsLatest, !preservingDisclosure, !m.isPreparingConversation {
                        seekLatest(proxy)
                    }
                    if pinsTop, reveal == nil, geometry.topGap > 1 { proxy.scrollTo("start", anchor: .top); return }
                    guard !followsLatest, reveal == nil, olderRequest == nil, !m.isPreparingConversation,
                          geometry.height > geometry.viewportHeight else { return }
                    let all = presented, range = window.range(in: all, selection: m.selection.key)
                    guard !range.isEmpty else { return }
                    if geometry.topGap < 100 {
                        if range.lowerBound > 0 { showOlder(all, above: range) }
                        else if m.moreChat, !m.loadingOlder { requestOlderPage(all[range.lowerBound].id) }
                    } else if !pinsTop, geometry.bottomGap < 100, range.upperBound < all.count {
                        showNewer(all, below: range)
                    }
                }
            }
            .onDisappear {
                keyboard.scrollToEdge = nil; keyboard.didUserScroll = nil
                keyboard.positionObservation = nil; keyboard.geometryChanged = nil
            }
        }
    }
    private var mount: some View {
        ConversationKeyboardMount(keyboard: keyboard, enabled: enabled, focused: viewportFocused)
    }
    private func request(_ target: Reveal, window next: ConversationWindow) {
        window = next; reveal = target; revealRequest &+= 1
    }
    /// Page one bounded step toward older loaded rows, keeping the current
    /// first row at the top. Newer rows beyond the window size are released.
    private func showOlder(_ all: [ConversationRow], above range: Range<Int>) {
        pinsTop = false
        let anchor = all[range.lowerBound].id
        let start = max(0, range.lowerBound - ConversationWindow.page)
        let end = min(range.upperBound, start + ConversationWindow.maximum)
        request(.top(anchor), window: end < all.count ? ConversationWindow.pinned(start..<end, in: all, selection: m.selection.key)
                                                      : ConversationWindow.showing(start..<end, in: all, selection: m.selection.key))
    }
    /// Page one bounded step toward the newest rows, keeping the current last
    /// row at the bottom. Reaching the newest row follows new rows again.
    private func showNewer(_ all: [ConversationRow], below range: Range<Int>) {
        pinsTop = false
        let anchor = all[range.upperBound - 1].id
        let end = min(all.count, range.upperBound + ConversationWindow.page)
        let start = max(range.lowerBound, end - ConversationWindow.maximum)
        request(.bottom(anchor), window: end < all.count ? ConversationWindow.pinned(start..<end, in: all, selection: m.selection.key)
                                                         : ConversationWindow.showing(start..<end, in: all, selection: m.selection.key))
    }
    private func requestOlderPage(_ anchor: String) {
        olderRequest = anchor
        m.run {
            do {
                try await m.loadOlder()
                // Nothing was added above the anchor: allow the next request.
                if olderRequest == anchor, !m.isPreparingConversation, m.streamRows.first?.id == anchor { olderRequest = nil }
            } catch { if olderRequest == anchor { olderRequest = nil }; throw error }
        }
    }
    private func revealRequestedOlderRows() -> Bool {
        guard let anchor = olderRequest else { return false }
        let all = presented, range = window.range(in: all, selection: m.selection.key)
        guard !range.isEmpty, all[range.lowerBound].id == anchor else { olderRequest = nil; return false }
        guard range.lowerBound > 0 else {
            if !m.loadingOlder { olderRequest = nil }
            return false
        }
        olderRequest = nil
        showOlder(all, above: range)
        return true
    }
    private func seekLatest(_ proxy: ScrollViewProxy) {
        let all = presented
        if shownRange.upperBound < all.count {
            // The newest rows are outside the window: show them first, then
            // scroll after the List has received that bounded collection.
            pinsTop = false
            request(.latest, window: ConversationWindow(selection: m.selection.key)); return
        }
        if let id = latestID { proxy.scrollTo(id, anchor: .bottom) }
    }
}
