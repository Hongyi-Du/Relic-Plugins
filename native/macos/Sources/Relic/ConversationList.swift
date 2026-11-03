import SwiftUI
import RelicCore

/// AppKit-backed List owns row recycling and variable-height placement. The
/// application supplies identities and reading intent, never virtual offsets.
struct ConversationStream: View {
    @EnvironmentObject var m: Model
    @Environment(\.isEnabled) private var enabled
    @FocusState private var viewportFocused: Bool
    @State private var keyboard = ConversationKeyboard()
    @State private var followsLatest = true
    @State private var preservingDisclosure = false
    @State private var mountedViewport = false
    @State private var mountedComposer = false
    @State private var olderAnchor: String?
    private var latestID: String? { m.displayLiveItems.isEmpty ? m.streamRows.last?.id : "live-end" }

    var body: some View {
        ScrollViewReader { proxy in
            VStack(spacing: 0) {
                if mountedViewport {
                    List {
                        Color.clear.frame(height: 8).id("start").accessibilityHidden(true)
                            .background(mount)
                            .listRowInsets(EdgeInsets()).listRowSeparator(.hidden).listRowBackground(Color.clear)
                        let rows = m.streamRows
                        let hasLive = !m.displayLiveItems.isEmpty
                        let compact = m.preferences["density"].text == "compact"
                        let last = hasLive ? "live-end" : rows.last?.id
                        if rows.isEmpty && !hasLive {
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
                                        ReferenceLabel(separator, size: 11.5, color: RelicStyle.muted, alignment: .center)
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
            .task(id: "\(m.selection.key)/\(m.streamVersion)/\(enabled)") {
                guard enabled, !m.isPreparingConversation else { return }
                let ticket = PerformanceRendering.beginSurface()
                defer { PerformanceRendering.endSurface(ticket) }
                for stage in 0..<2 {
                    if stage == 0 ? mountedViewport : mountedComposer { continue }
                    let turn = UUID()
                    guard await RowMountQueue.shared.acquire(turn, label: stage == 0 ? "conversation-viewport" : "composer") else { return }
                    guard !Task.isCancelled else { RowMountQueue.shared.release(turn); return }
                    if stage == 0 { mountedViewport = true } else { mountedComposer = true }
                    do { try await Task.sleep(for: .milliseconds(32)) }
                    catch { RowMountQueue.shared.release(turn); return }
                    RowMountQueue.shared.release(turn)
                }
                // List must receive the changed collection before its one
                // semantic request. It retains the same native viewport.
                await Task.yield()
                guard !Task.isCancelled else { return }
                if let anchor = olderAnchor {
                    proxy.scrollTo(anchor, anchor: .top); olderAnchor = nil
                } else if followsLatest { seekLatest(proxy) }
            }
            .onChange(of: m.selection) {
                keyboard.discardDisclosurePosition(); followsLatest = true
                preservingDisclosure = false; olderAnchor = nil; keyboard.observedHeight = 0
            }
            .onChange(of: m.streamVersion) {
                PerformanceRendering.observed(streamVersion: m.streamVersion)
                keyboard.discardDisclosurePosition(); preservingDisclosure = false
            }
            .onAppear {
                PerformanceRendering.observed(streamVersion: m.streamVersion)
                keyboard.positionObservation = {
                    ["last_row_id": latestID as Any? ?? NSNull(), "follows_latest": followsLatest,
                     "initial": !mountedViewport, "enabled": enabled, "preparing": m.isPreparingConversation]
                }
                keyboard.didUserScroll = { nearBottom in
                    followsLatest = nearBottom; preservingDisclosure = false; olderAnchor = nil
                }
                keyboard.scrollToEdge = { top in
                    followsLatest = !top; preservingDisclosure = false; olderAnchor = nil
                    if top { proxy.scrollTo("start", anchor: .top) }
                    else { seekLatest(proxy) }
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
                    if !followsLatest, geometry.height > geometry.viewportHeight, geometry.topGap < 100,
                       olderAnchor == nil, m.moreChat, !m.loadingOlder, let first = m.streamRows.first?.id {
                        olderAnchor = first
                        m.run {
                            do {
                                try await m.loadOlder()
                                if !m.isPreparingConversation { olderAnchor = nil }
                            } catch { olderAnchor = nil; throw error }
                        }
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
    private func seekLatest(_ proxy: ScrollViewProxy) {
        if let id = latestID { proxy.scrollTo(id, anchor: .bottom) }
    }
}
