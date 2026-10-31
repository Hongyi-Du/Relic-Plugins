import SwiftUI
import AppKit
import RelicCore

struct Avatar: View {
    @EnvironmentObject var m: Model
    let member: String
    var size: CGFloat = 30
    var secretaryStyle = false
    var showState = false
    var stateBorder: Color = RelicStyle.background
    var borderWidth: CGFloat = 0
    var imageVisibility: ((Bool) -> Void)? = nil
    @State private var image: NSImage?
    @State private var identity = "relic-avatar/" + UUID().uuidString
    @Environment(\.colorScheme) private var scheme
    private var state: String { m.members.first(where: { $0["name"].text == member })?["state"].text ?? "" }
    private var radius: CGFloat { size == 20 ? 6 : size == 28 ? 8 : size == 60 ? 14 : 9 }
    private var fontSize: CGFloat { size == 20 ? 10 : size == 28 || size == 30 ? 12 : size == 60 ? 24 : 14 }
    private var cacheKey: String {
        let avatar = m.members.first(where: { $0["name"].text == member })?["avatar"].text ?? ""
        return [m.organization, member, m.preferences["avatar"].text, avatar].joined(separator: "/")
    }
    var body: some View {
        Group {
            if let image { Image(nsImage: image).resizable().scaledToFill() }
            else if secretaryStyle { ReferenceIcon(name: "sec", size: 16, color: RelicStyle.violet, owner: identity).frame(maxWidth: .infinity, maxHeight: .infinity) }
            else { ReferenceLabel(String(m.name(member).prefix(1)).uppercased(), size: fontSize, weight: 650, color: member == "human" ? RelicStyle.background : RelicStyle.avatar(member, background: false, dark: scheme == .dark), lines: 0, alignment: .center, owner: identity).frame(maxWidth: .infinity, maxHeight: .infinity) }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: max(0, radius - borderWidth))).padding(borderWidth)
            .modifier(RecordedSurface(background: secretaryStyle ? RelicStyle.violetSoft : member == "human" ? RelicStyle.ink : RelicStyle.avatar(member, background: true, dark: scheme == .dark),
                border: borderWidth > 0 ? RelicStyle.background : .clear, borderWidth: borderWidth, radius: radius, kind: "avatar", owner: identity))
            .overlay(alignment: .bottomTrailing) {
                if showState && !["", "idle"].contains(state) { StateDot(state: state, border: stateBorder).offset(x: 2, y: 2) }
            }
            .task(id: cacheKey) {
                guard !member.isEmpty else { image = nil; return }
                let path = member == "human" ? "/api/avatar" : "/api/avatar/" + Client.segment(m.organization) + "/" + Client.segment(member)
                if let data = try? await m.bytes(path) { image = NSImage(data: data) } else { image = nil }
            }.onAppear { imageVisibility?(image != nil) }
            .onChange(of: image != nil) { imageVisibility?(image != nil) }
            .accessibilityElement(children: .contain).accessibilityIdentifier(identity).accessibilityLabel("")
    }
}

struct RichText: View {
    @EnvironmentObject var m: Model
    let text: String
    var pointSize: CGFloat? = nil
    var document = false
    init(_ text: String, pointSize: CGFloat? = nil, document: Bool = false) { self.text = text; self.pointSize = pointSize; self.document = document }
    private var baseSize: CGFloat { pointSize ?? (document ? 13.5 : m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14) }
    private var textLineHeight: CGFloat { baseSize * (document ? 1.7 : 1.65) }
    @State private var prepared: PreparedMarkdown?
    private var parsed: PreparedMarkdown? { prepared?.source == text ? prepared : nil }
    private var blocks: [MarkdownBlock] { parsed?.blocks ?? [] }
    private func attributed(_ value: String) -> AttributedString { parsed?.inline(value) ?? AttributedString(value) }
    private func list(_ block: MarkdownBlock) -> [MarkdownListItem] { parsed?.list(block) ?? [] }
    private func table(_ block: MarkdownBlock) -> [[String]] { parsed?.table(block) ?? [] }
    var body: some View {
        Group {
        if parsed == nil { SelectableText(value: AttributedString(text), pointSize: baseSize, lineHeight: textLineHeight) }
        else { IntrinsicMarkdownLayout(preferredWidth: preferredWidth) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                    blockView(block).padding(.top, blockGap(index))
                }
            }.padding(.bottom, blocks.last.map { blockMargins($0, last: true).bottom } ?? 0)
        } }
        }.task(id: text) {
            let value = await MarkdownPreparation.shared.prepare(text)
            if !Task.isCancelled { prepared = value }
        }.onDisappear { prepared = nil }
        .environment(\.openURL, OpenURLAction { url in
            if url.scheme == "relic-file", let parts = URLComponents(url: url, resolvingAgainstBaseURL: false), let path = parts.queryItems?.first(where: { $0.name == "path" })?.value {
                let line = Int(parts.queryItems?.first(where: { $0.name == "line" })?.value ?? "") ?? 0
                m.run { try await m.openFile(path, line: line) }; return .handled
            }
            if url.isFileURL || url.scheme == nil && url.path.hasPrefix("/") {
                let ref = NativeLinks.file(url.path); m.run { try await m.openFile(ref?.path ?? url.path, line: ref?.line ?? 0) }; return .handled
            }
            return .systemAction
        })
    }
    private func blockMargins(_ block: MarkdownBlock, last: Bool) -> (top: CGFloat, bottom: CGFloat) {
        switch block.kind {
        case "head": return (document ? 10 : 8, 4)
        case "code": return (document ? 12 : 6, document ? 12 : 6)
        case "list": return (2, 8)
        case "quote": return (0, 8)
        case "table": return (0, 0) // Table margins remain inside its overflow container.
        default: return (0, last ? 0 : 8)
        }
    }
    private func blockGap(_ index: Int) -> CGFloat {
        let top = blockMargins(blocks[index], last: index == blocks.count - 1).top
        return index == 0 ? top : max(top, blockMargins(blocks[index - 1], last: false).bottom)
    }
    private var preferredWidth: CGFloat {
        let size = baseSize
        return blocks.map { block -> CGFloat in
            switch block.kind {
            case "code": return NativeTextStyle.preferredWidth(NativeTextStyle.render(AttributedString(block.text), size: document ? 10.8 : 11.25, monospaced: true)) + 24
            case "head": return NativeTextStyle.preferredWidth(NativeTextStyle.render(attributed(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)), size: document ? size * 1.02 : size, weight: .bold))
            case "quote": return NativeTextStyle.preferredWidth(NativeTextStyle.render(quoteText(block), size: size * 0.92)) + 13
            case "list": return list(block).map { NativeTextStyle.preferredWidth(NativeTextStyle.render(attributed($0.text), size: size)) + ($0.indented ? 40 : 22) }.max() ?? 0
            case "table": return tableWidths(block).reduce(0,+)
            default: return NativeTextStyle.preferredWidth(NativeTextStyle.render(attributed(block.text), size: size))
            }
        }.max() ?? 0
    }
    private func inline(_ value: String) -> some View {
        SelectableText(value: attributed(value), pointSize: baseSize, lineHeight: textLineHeight).help(m.t("chat.path_preview"))
    }
    @ViewBuilder private func blockView(_ block: MarkdownBlock) -> some View {
        switch block.kind {
        case "code": ScrollView(.horizontal) {
            SelectableText(value: AttributedString(block.text), pointSize: document ? 10.8 : 11.25, lineHeight: document ? 18.6 : 19.375, monospaced: true).fixedSize(horizontal: true, vertical: true).padding(.horizontal, 12).padding(.vertical, 10)
        }.fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 8, kind: "code"))
        case "head": SelectableText(value: attributed(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)), weight: .bold, pointSize: document ? baseSize * 1.02 : baseSize, lineHeight: textLineHeight * (document ? 1.02 : 1))
        case "quote":
            SelectableText(value: quoteText(block), color: RelicStyle.secondary, pointSize: baseSize * 0.92, lineHeight: textLineHeight * 0.92)
                .padding(.leading, 13).padding(.vertical, 2)
                .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "card"))
                .fixedSize(horizontal: false, vertical: true)
        case "list":
            VStack(alignment: .leading, spacing: 0) { ForEach(Array(list(block).enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 0) {
                    if item.marker == "•" {
                        let metrics = NativeListMarkerMetrics(font: RelicStyle.nativeFont(baseSize, weight: 400))
                        NativeListMarker(size: baseSize).frame(width: metrics.width, height: metrics.height)
                            .offset(x: 22 - metrics.distanceBeforeText, y: (textLineHeight - metrics.height) / 2)
                            .frame(width: 22, height: textLineHeight, alignment: .topLeading)
                    } else {
                        ReferenceLabel(item.marker + " ", size: baseSize, lineHeight: textLineHeight, alignment: .right, textGlyphIcon: true).frame(width: 14, alignment: .trailing).padding(.trailing, 8)
                    }
                    inline(item.text)
                }.padding(.leading, item.indented ? 18 : 0)
            } }
        case "table":
            ScrollView(.horizontal) { Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(Array(table(block).enumerated()), id: \.offset) { index, row in GridRow {
                    ForEach(Array(row.enumerated()), id: \.offset) { column, cell in
                        SelectableText(value: attributed(cell), weight: index == 0 && NativeMarkdown.tableHasHeader(block) ? .semibold : .regular, pointSize: baseSize * 0.93, lineHeight: textLineHeight * 0.93)
                            .padding(.horizontal, 8).padding(.vertical, 3.5).frame(width: tableWidths(block)[column], alignment: .leading)
                            .modifier(RecordedSurface(background: index == 0 && NativeMarkdown.tableHasHeader(block) ? RelicStyle.ink.opacity(0.04) : .clear, border: RelicStyle.border, edges: EdgeInsets(top: 1, leading: 1, bottom: index == table(block).count - 1 ? 1 : 0, trailing: column == row.count - 1 ? 1 : 0), kind: "card"))
                            .accessibilityLabel(String(attributed(cell).characters))
                    }
                } }
            }.padding(.vertical, 6) }.fixedSize(horizontal: false, vertical: true)
        default: inline(block.text)
        }
    }
    private func tableWidths(_ block: MarkdownBlock) -> [CGFloat] {
        let rows = table(block), count = rows.map(\.count).max() ?? 0
        return (0..<count).map { column in
            rows.enumerated().map { index, row in
                guard row.indices.contains(column) else { return CGFloat.zero }
                return NativeTextStyle.preferredWidth(NativeTextStyle.render(attributed(row[column]), size: baseSize * 0.93, weight: index == 0 && NativeMarkdown.tableHasHeader(block) ? .semibold : .regular)) + 17
            }.max() ?? 0
        }
    }
    private func quoteText(_ block: MarkdownBlock) -> AttributedString {
        let value = block.lines.map { $0.replacingOccurrences(of: #"^\s*>\s?"#, with: "", options: .regularExpression) }.joined(separator: "\n")
        if let range = value.range(of: #"^[^\n：:]{1,40}[：:]\s?"#, options: .regularExpression) {
            let head = String(value[range]).trimmingCharacters(in: CharacterSet(charactersIn: ":： "))
            var title = AttributedString(m.t("chat.quote_from", ["name": head])); title.inlinePresentationIntent = .stronglyEmphasized
            title.append(AttributedString(String(value[range.upperBound...]))); return title
        }
        return AttributedString(value)
    }
}

struct IntrinsicMarkdownLayout: Layout {
    let preferredWidth: CGFloat
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = min(proposal.width ?? preferredWidth, preferredWidth)
        return subviews.first?.sizeThatFits(ProposedViewSize(width: max(1, width), height: nil)) ?? .zero
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, proposal: ProposedViewSize(width: bounds.width, height: bounds.height))
    }
}

struct ChatView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if m.organization.isEmpty {
                ReferenceLabel(m.t("common.app_name"), size: 15, weight: 650, lineHeight: 19.5).frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.leading, 20).frame(height: 56)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card"))
                ScrollView {
                    VStack(spacing: 14) {
                        ReferenceLabel(m.t("chat.no_orgs"), size: 18, weight: 650, alignment: .center)
                        ReferenceLabel(m.t("chat.no_orgs_hint"), size: 14, color: RelicStyle.muted, lines: 0, alignment: .center).padding(.bottom, 14)
                    }.padding(30).frame(maxWidth: 880).frame(maxWidth: .infinity).frame(height: m.windowSize.height * 0.7).padding(.horizontal, 20).padding(.top, 8)
                }
                // The empty reference composer retains its 6px top and 16px
                // bottom spacing even before an organization is selected.
                Color.clear.frame(height: 22).measuredRegion("composer")
            } else {
                header
                if m.member.isEmpty && m.digestOpen { DigestCard() }
                if !m.member.isEmpty { ConversationBanner() }
                ConversationStream()
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).modifier(RecordedSurface(background: RelicStyle.background, kind: "region"))
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.chat"))
            .accessibilityIdentifier("relic-region/conversation")
    }
    private var header: some View {
        HStack(spacing: 12) {
            if m.member.isEmpty { SidebarGroupAvatar() } else { Avatar(member: m.member, size: 28, secretaryStyle: m.member == m.secretary, showState: true) }
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 8) {
                    let title = m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("chat.secretary_title", ["name": m.roleName(m.member, "common.secretary")]) : m.name(m.member)
                    ReferenceLabel(title, size: 15, weight: 650, lineHeight: 19.5).help(title)
                    if m.member.isEmpty { ReferenceLabel(m.t("common.members", ["n": String(m.members.count)]), size: 15, color: RelicStyle.muted, lineHeight: 19.5) }
                    else {
                        if !m.selectedMember["display"].text.isEmpty && m.selectedMember["display"].text != m.member { ReferenceLabel(m.member, size: 13.8, color: RelicStyle.muted, lineHeight: 17.94, monospaced: true) }
                        if m.selectedMember["leader"].flag { MemberTag(text: m.t("common.leader"), color: RelicStyle.accent, background: RelicStyle.accent.opacity(0.13)) }
                    }
                }.frame(height: 19.5, alignment: .leading)
                let meta = m.member.isEmpty ? m.t(m.snapshot["org"]["auto_wake"].flag ? "chat.group_meta_on" : "chat.group_meta_off", ["org": m.snapshot["org"]["name"].text]) : [m.snapshot["org"]["name"].text, m.selectedMember["harness_label"].text, m.selectedMember["surface_label"].text, m.selectedMember["model"].text, m.stateLabel(m.selectedMember["state"].text)].filter { !$0.isEmpty }.joined(separator: " · ")
                ReferenceLabel(meta, size: 12, color: RelicStyle.muted, lineHeight: 16.8).help(meta).frame(height: 16.8, alignment: .leading)
            }.frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 2) {
            if m.member.isEmpty {
                ChipButton(title: m.t(m.plainMode ? "chat.plain_on" : "common.plain_words"), help: m.t("chat.plain_title"), icon: "lang", selected: m.plainMode) { m.togglePlain() }.padding(.trailing, 4)
                ChipButton(title: m.t("chat.digest"), help: m.t("chat.digest_title"), icon: "sparkle", selected: m.digestOpen) { m.toggleDigest() }.padding(.trailing, 4)
                IconButton(title: m.t("common.tasks"), icon: "check") { m.openDetails("tasks") }
            } else {
                if m.selectedMember["embedded"].flag && ["running", "waiting"].contains(m.selectedMember["state"].text) { IconButton(title: m.t("chat.stop_turn"), icon: "stop") { m.run { try await m.post(m.path("/cancel"), ["member": m.member]); try await m.refresh() } } }
                IconButton(title: m.t("chat.card"), icon: "card") { m.openCard(m.member) }
                IconButton(title: m.t("common.context_trace"), icon: "trace") { m.openDetails("trace") }
                if m.selectedMember["surface"].text != "chat" { IconButton(title: m.t("chat.workspace"), icon: "work") { m.setPane("workspace") } }
            }
            }.fixedSize()
        }.padding(.leading, 20).padding(.trailing, 14).frame(height: 56)
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card"))
    }
}

private struct StreamMetrics: Equatable {
    var bottom: CGFloat = 0
    var height: CGFloat = 0
    var width: CGFloat = 0
}
private struct StreamBottom: PreferenceKey {
    static var defaultValue = StreamMetrics()
    static func reduce(value: inout StreamMetrics, nextValue: () -> StreamMetrics) {
        let next = nextValue()
        if next.bottom != 0 { value.bottom = next.bottom }
        if next.height != 0 { value.height = next.height }
        if next.width != 0 { value.width = next.width }
    }
}

struct ConversationStream: View {
    @EnvironmentObject var m: Model
    @Environment(\.isEnabled) private var enabled
    @FocusState private var viewportFocused: Bool
    @State private var following = ConversationScrollFollowing()
    @State private var initialLoad = true
    @State private var olderAnchor: String?
    @State private var keyboard = ConversationKeyboard()
    var body: some View {
        ScrollViewReader { proxy in
            VStack(spacing: 0) {
                GeometryReader { viewport in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            let rows = m.streamRows
                            if rows.isEmpty && m.displayLiveItems.isEmpty {
                                NoticeLayout {
                                    ReferenceLabel(m.t(m.member.isEmpty ? "chat.empty_group" : "chat.empty_private"),
                                        size: 12, color: RelicStyle.muted, lines: 0, alignment: .center)
                                        .padding(.horizontal, 10).padding(.vertical, 2)
                                        .modifier(RecordedSurface(background: RelicStyle.sidebar, radius: 10, kind: "card"))
                                }.padding(.top, 40).padding(.bottom, 8)
                            }
                            ForEach(rows) { row in
                                VStack(alignment: .leading, spacing: 0) {
                                if let separator = row.separator {
                                    ReferenceLabel(separator, size: 11.5, color: RelicStyle.muted, alignment: .center).frame(maxWidth: .infinity).padding(.top, 18)
                                        .padding(.bottom, ConversationSpacing.separatorBottom(kind: row.item["type"].text, continued: row.continued, compact: m.preferences["density"].text == "compact"))
                                }
                                MessageView(item: row.item, continued: row.continued)
                                    .padding(.top, ["notice", "acts"].contains(row.item["type"].text) ? 0 : ConversationSpacing.messageTop(kind: row.item["type"].text, continued: row.continued, compact: m.preferences["density"].text == "compact"))
                                }.id(row.id)
                            }
                            if !m.displayLiveItems.isEmpty { LiveTurnView() }
                            // Include the reference's 24px trailing space in
                            // the scroll target. Padding outside the target is
                            // scrolled offscreen by scrollTo(anchor: .bottom).
                            Color.clear.frame(height: 24).id("end")
                        }.frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 8)
                            .environment(\.conversationDisclosure, { keyboard.preserveDisclosurePosition(); following.disclosureChanged() })
                            .background(GeometryReader { content in Color.clear.preference(key: StreamBottom.self, value: StreamMetrics(bottom: content.frame(in: .named("conversation")).maxY, height: content.size.height, width: content.size.width)) })
                            .background(ConversationKeyboardMount(keyboard: keyboard, enabled: enabled, focused: viewportFocused))
                    }.defaultScrollAnchor(.bottom).modifier(RecordedSurface(background: .clear, kind: "region"))
                        .scrollDisabled(!enabled).focusable(enabled).focused($viewportFocused).focusEffectDisabled()
                        .onKeyPress(phases: [.down, .repeat]) { keyboard.handle($0.key, modifiers: $0.modifiers) }
                        .coordinateSpace(name: "conversation")
                        .onPreferenceChange(StreamBottom.self) { metrics in
                            keyboard.finishDisclosureLayout()
                            // Lazy height estimates change during scrolling.
                            // Observe them, but never feed a layout change back
                            // into scrollTo; only new content requests anchoring.
                            _ = following.observe(content: CGSize(width: metrics.width, height: metrics.height), bottom: metrics.bottom, viewport: viewport.size)
                            if metrics.height > viewport.size.height, metrics.bottom - metrics.height >= -100,
                               !initialLoad, !following.followsBottom, olderAnchor == nil, m.moreChat, !m.loadingOlder,
                               let first = m.streamRows.first?.id {
                                olderAnchor = first
                                m.run {
                                    do { try await m.loadOlder() }
                                    catch { olderAnchor = nil; throw error }
                                }
                            }
                        }
                }
                ComposerView { following.followsBottom = true; m.run { try await m.send(); proxy.scrollTo("end", anchor: .bottom) } }.measuredRegion("composer")
            }.onChange(of: m.selection) { keyboard.discardDisclosurePosition(); initialLoad = true; olderAnchor = nil; following = ConversationScrollFollowing() }
                .onChange(of: m.streamVersion) {
                    keyboard.discardDisclosurePosition()
                    following.contentChanged()
                    if let anchor = olderAnchor { proxy.scrollTo(anchor, anchor: .top); olderAnchor = nil }
                    else if !m.streamRows.isEmpty && (initialLoad || following.followsBottom) { proxy.scrollTo("end", anchor: .bottom); initialLoad = false }
                }
                .onAppear { proxy.scrollTo("end", anchor: .bottom) }
        }
    }
}

struct MessageView: View {
    @EnvironmentObject var m: Model
    @Environment(\.conversationDisclosure) private var preserveScroll
    let item: Node
    var inThread = false
    var continued = false
    @State private var threadIdentity = "relic-row/thread/" + UUID().uuidString
    @State private var hovering = false
    @State private var originalExpanded = false
    @State private var threadAvatarImages: Set<String> = []
    private var mine: Bool { item["from"].text == "human" }
    private var bodyText: String { item["body"].text.isEmpty ? item["text"].text : item["body"].text }
    private var groupPlain: Bool { m.plainMode && m.member.isEmpty && !inThread }
    private var wantsPlain: Bool { (groupPlain || m.plainOne.contains(item["id"].text)) && item["from"].text != "human" && Int(item["id"].text) != nil }
    private var threadAccessibilityName: String {
        let initials = item["thread"]["people"].rows.prefix(3).filter { !threadAvatarImages.contains($0.text) }
            .map { String(m.name($0.text).prefix(1)).uppercased() }.joined(separator: " ")
        return [initials, m.t("thread.replies", ["n": item["thread"]["count"].text]),
            m.t("thread.last_reply", ["when": m.shortWhen(item["thread"]["last_at"])])].filter { !$0.isEmpty }.joined(separator: " ")
    }
    private var recipientLabel: String {
        let recipients = Set(item["to"].rows.map(\.text))
        let everyone = m.members.map { $0["name"].text }.filter { $0 != item["from"].text }
        return m.t("msg.to", ["names": !everyone.isEmpty && everyone.allSatisfy(recipients.contains) ? m.t("msg.everyone") : m.list(item["to"].rows.map { m.name($0.text) })])
    }
    var body: some View {
        if item["type"].text == "notice" {
            NoticeLayout {
                ReferenceLabel(item["text"].text, size: 12, color: RelicStyle.muted, lines: 0, alignment: .center)
                    .padding(.horizontal, 10).padding(.vertical, 2).modifier(RecordedSurface(background: RelicStyle.sidebar, radius: 10, kind: "card"))
            }.padding(.top, 8)
        }
        else if item["type"].text == "acts" {
            ActivityGroup(item: item).padding(.leading, inThread ? 40 : 46).padding(.top, 4)
        } else {
            MessageColumns(mine: mine) {
                if continued { Color.clear.frame(width: inThread ? 30 : 36, height: 0) }
                else if mine { Avatar(member: "human", size: inThread ? 30 : 36).accessibilitySortPriority(1) }
                else { MemberCardButton(member: item["from"].text) { Avatar(member: item["fromParent"].text.isEmpty ? item["from"].text : item["fromParent"].text, size: inThread ? 30 : 36) }.buttonStyle(.plain).accessibilityLabel("").accessibilitySortPriority(1) }
                VStack(alignment: mine ? .trailing : .leading, spacing: 4) {
                    if !continued { FlowLayout(spacing: 6, centerRows: true, rowAlignment: mine ? .trailing : .leading) {
                        ReferenceLabel(item["fromLabel"].text.isEmpty ? m.name(item["from"].text) : item["fromLabel"].text, size: 12.5, weight: 600, color: RelicStyle.secondary, lineHeight: 16.25, lines: 0)
                        if item["type"].text != "receipt" && m.member.isEmpty && !inThread && m.members.contains(where: { $0["name"].text == item["from"].text }) { ReferenceLabel(item["from"].text, size: 11, color: RelicStyle.muted, lineHeight: 14.3, lines: 0, monospaced: true) }
                        if item["type"].text == "receipt" { ReferenceLabel(m.t("msg.auto_receipt_to", ["names": m.list(item["to"].rows.map { m.name($0.text) })]), size: 12, color: RelicStyle.muted, lineHeight: 15.6, lines: 0) }
                        else if m.member.isEmpty && !inThread && !item["to"].rows.isEmpty { ReferenceLabel(recipientLabel, size: 12, color: RelicStyle.muted, lineHeight: 15.6, lines: 0).help(recipientLabel) }
                        ReferenceLabel(m.clock(item["at"]), size: 12, color: RelicStyle.muted, lineHeight: 15.6, lines: 0).fixedSize().help(m.day(item["at"]) + " " + m.clock(item["at"]))
                    } }
                    if item["type"].text == "receipt" {
                        MessageReceipt(text: bodyText.replacingOccurrences(of: #"^\[Relic auto-receipt\]\s*"#, with: "", options: .regularExpression))
                    } else if wantsPlain, let plain = m.plain[item["id"].text] {
                        messageBubble(plain["text"].text.isEmpty ? plain.text : plain["text"].text, plain: true)
                        VStack(alignment: .leading, spacing: 0) {
                            OriginalDisclosureButton(title: m.t("msg.original"), expanded: originalExpanded) { preserveScroll(); originalExpanded.toggle() }
                            if originalExpanded { messageBubble(bodyText).padding(.top, 4) }
                        }
                    } else {
                        messageBubble(bodyText)
                        if wantsPlain {
                            if m.plainFailed.contains(item["id"].text) { TextButton(m.t("plain.retry"), size: 11.5, weight: 400, color: RelicStyle.red) { m.run { try await m.requestPlain([item["id"].text]) } }.buttonStyle(.plain) }
                            else { HStack(spacing: 6) {
                                if m.plainPending.contains(item["id"].text) { ProgressView().controlSize(.mini).frame(width: 10, height: 10) }
                                ReferenceLabel(m.t(m.plainPending.contains(item["id"].text) ? "plain.pending" : "plain.waiting"), size: 11.5, color: RelicStyle.muted)
                            } }
                        }
                    }
                    if item["from"].text == "human" && !item["read_by"].isNull && !item["to"].isNull {
                        ReferenceLabel(m.readReceipt(item), size: 11, color: RelicStyle.muted, lines: 0)
                    }
                    if !inThread, !item["thread"].isNull {
                        Button { m.run { try await m.openThread(item["id"].text) } } label: {
                            HStack(spacing: 6) {
                                HStack(spacing: -4) { Rows(Array(item["thread"]["people"].rows.prefix(3))) { person in
                                    Avatar(member: person.text, size: 20, borderWidth: 2, imageVisibility: { visible in
                                        if visible { threadAvatarImages.insert(person.text) } else { threadAvatarImages.remove(person.text) }
                                    })
                                } }.padding(.trailing, -4)
                                ReferenceLabel(m.t("thread.replies", ["n": item["thread"]["count"].text]), size: 12.5, weight: 600, color: RelicStyle.accent, lines: 0, owner: threadIdentity, controlLabel: true)
                                ReferenceLabel(m.t("thread.last_reply", ["when": m.shortWhen(item["thread"]["last_at"])]), size: 12.5, color: RelicStyle.muted, lines: 0, owner: threadIdentity)
                            }.padding(.leading, 4).padding(.trailing, 8).padding(.vertical, 3).environment(\.nativeElementParent, threadIdentity)
                        }.buttonStyle(QuietButtonStyle()).accessibilityIdentifier(threadIdentity).accessibilityLabel(threadAccessibilityName)
                    }
                }.frame(maxWidth: 720, alignment: mine ? .trailing : .leading)
            }.contentShape(Rectangle()).overlay(alignment: mine ? .topLeading : .topTrailing) {
                if hovering { hoverActions.offset(x: mine ? 8 : -8, y: -12) }
            }.background(MessageInteractionAnchor(messageID: item["id"].text))
                .onHover { hovering = $0 }.environment(\.selectedAuthor, item["from"].text).task(id: wantsPlain) { if wantsPlain { m.enqueuePlain(item["id"].text) } }
        }
    }
    private var hoverActions: some View {
        HStack(spacing: 2) {
            if !groupPlain, item["from"].text != "human", Int(item["id"].text) != nil {
                MessageActionButton(title: m.t(wantsPlain ? "msg.original" : "msg.plain"), hint: m.t(wantsPlain ? "msg.hide_plain" : "common.plain_words"), icon: "lang") {
                    if m.plainOne.contains(item["id"].text) { m.plainOne.remove(item["id"].text) }
                    else { m.plainOne.insert(item["id"].text); m.run { try await m.requestPlain([item["id"].text]) } }
                }
            }
            MessageActionButton(title: m.t("common.quote"), hint: m.t("common.quote"), icon: "quote") { m.setQuote(bodyText, from: item["fromLabel"].text.isEmpty ? item["from"].text : item["fromLabel"].text, stripExisting: true) }
            if !inThread, Int(item["id"].text) != nil { MessageActionButton(title: m.t("common.reply"), hint: m.t("msg.reply_in_thread"), icon: "thread") { m.run { try await m.openThread(item["id"].text) } } }
            MessageActionButton(title: "", hint: m.t("common.copy"), icon: "copy", controlID: "message-copy/" + item["id"].text) {
                NSPasteboard.general.clearContents(); m.notice = m.t(NSPasteboard.general.setString(bodyText, forType: .string) ? "msg.copied" : "msg.copy_failed")
            }
        }.padding(3).modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 8, kind: "card", shadows: SurfaceShadow.small))
    }
    private func messageBubble(_ text: String, plain: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            if plain { HStack(spacing: 4) { ReferenceIcon(name: "lang", size: 13, color: RelicStyle.violet); ReferenceLabel(m.t("msg.plain"), size: 11, weight: 650, color: RelicStyle.violet) } }
            RichText(text)
        }.padding(.horizontal, plain ? 14 : 13).padding(.vertical, plain ? 10 : 9)
            .modifier(RecordedSurface(background: mine ? RelicStyle.mine : plain ? RelicStyle.violetSoft : RelicStyle.bubble,
                border: plain ? RelicStyle.violet.opacity(0.22) : .clear, borderWidth: plain ? 1 : 0, radius: 14, kind: "card",
                cornerRadii: mine ? [14,4,14,14] : [4,14,14,14], insetLeadingWidth: item["from"].text == m.secretary && m.member.isEmpty && !inThread ? 3 : 0, insetLeadingColor: RelicStyle.violet))
    }
}

struct MessageReceipt: View {
    @Environment(\.conversationDisclosure) private var preserveScroll
    let text: String
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button { preserveScroll(); expanded.toggle() } label: {
                ReferenceLabel((expanded ? "▾ " : "▸ ") + ReferenceText.clip(text, to: 90), size: 12.5, color: RelicStyle.muted, lines: 0)
                    .modifier(RecordedSurface(background: .clear, expanded: expanded))
            }.buttonStyle(.plain)
            if expanded { SelectableText(value: AttributedString(text), color: RelicStyle.secondary, pointSize: 12, lineHeight: 18.6) }
        }.padding(.horizontal, 11).padding(.vertical, 7).frame(maxWidth: 640, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, borderWidth: 1, radius: 10, kind: "card"))
    }
}

struct ActivityRow: View {
    @EnvironmentObject var m: Model
    @Environment(\.conversationDisclosure) private var preserveScroll
    let row: ToolActivity
    let member: String
    @State private var expanded = false
    @State private var full: [String: Node] = [:]
    @State private var hovering = false
    @State private var identity = "relic-row/activity/" + UUID().uuidString
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { preserveScroll(); expanded.toggle() } label: {
                HStack(spacing: 8) {
                    Color.clear.frame(width: 7, height: 7).modifier(RecordedSurface(background: row.failed ? RelicStyle.red : row.result != nil ? RelicStyle.green : RelicStyle.faint, radius: 3.5, kind: "badge"))
                    ReferenceLabel(row.call == nil ? m.t("common.result") : row.title, size: 12.5, weight: 600, lineHeight: 20, owner: identity).fixedSize()
                    ReferenceLabel(row.argument, size: 11.5, color: RelicStyle.muted, owner: identity, monospaced: true).frame(maxWidth: .infinity, alignment: .leading)
                    ReferenceLabel(m.clock((row.call ?? row.result ?? Node())["at"]), size: 11, color: RelicStyle.muted, owner: identity).fixedSize()
                }.padding(.leading, 12).padding(.trailing, 10).padding(.vertical, 3).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: hovering ? RelicStyle.sidebar : .clear, owner: identity, hovered: hovering, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity).onHover { hovering = $0 }
            if expanded {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array([row.call, row.result].compactMap { $0 }.enumerated()), id: \.offset) { _, step in
                        ActivityOutput(text: (full[step["i"].text] ?? step)["text"].text)
                    }
                }.padding(.leading, 27).padding(.trailing, 10).padding(.top, 2).padding(.bottom, 8)
            }
        }.task(id: expanded) {
            guard expanded else { return }
            for step in [row.call, row.result].compactMap({ $0 }) where step["cut"].flag && !step["i"].isNull && full[step["i"].text] == nil {
                if let result = try? await m.get(m.path("/step?member=" + Client.segment(member) + "&i=" + step["i"].text)) { full[step["i"].text] = result }
            }
        }
    }
}

struct StepView: View {
    @EnvironmentObject var m: Model
    @Environment(\.conversationDisclosure) private var preserveScroll
    let step: Node
    let member: String
    @State private var expanded = false
    @State private var identity = "relic-row/step/" + UUID().uuidString
    private var title: String {
        if step["role"].text == "tool_call" { return ToolActivity.toolName(step["tool"].text) }
        return m.t(["user": "trace.user", "assistant": "common.reply", "thinking": "trace.thinking", "context": "trace.injected"][step["role"].text] ?? "common.result")
    }
    private var summary: String { step["role"].text == "tool_call" ? ToolActivity.pair([step]).first?.argument ?? "" : ReferenceText.clip(step["text"].text, to: 120) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { preserveScroll(); expanded.toggle() } label: {
                HStack(spacing: 8) {
                    Circle().fill(step["error"].flag ? RelicStyle.red : step["role"].text == "tool_result" ? RelicStyle.green : RelicStyle.faint).frame(width: 7, height: 7)
                    ReferenceLabel(title, size: 12.5, weight: 600, owner: identity).fixedSize()
                    ReferenceLabel(summary, size: 11.5, color: RelicStyle.muted, owner: identity, monospaced: true).frame(maxWidth: .infinity, alignment: .leading)
                    ReferenceLabel(m.clock(step["at"]), size: 11, color: RelicStyle.muted, owner: identity).fixedSize()
                }.padding(.leading, 12).padding(.trailing, 10).padding(.vertical, 3).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: .clear, owner: identity, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity)
                .accessibilityLabel([title, summary, m.clock(step["at"])].filter { !$0.isEmpty }.joined(separator: " "))
            if expanded {
                SelectableText(value: AttributedString(step["text"].text), pointSize: 11.5, lineHeight: 17.825, monospaced: true)
                    .padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 7, kind: "code"))
                    .padding(.leading, 27).padding(.trailing, 10).padding(.top, 2).padding(.bottom, 8)
            }
        }.onAppear { expanded = ["assistant", "user"].contains(step["role"].text) }
    }
}

struct PermissionCard: View {
    @EnvironmentObject var m: Model
    let item: Node
    @State private var sending = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) { ReferenceIcon(name: "bell", size: 14, color: RelicStyle.amber); ReferenceLabel(m.t("perm.ask"), size: 12, weight: 700, color: RelicStyle.amber, lineHeight: 19.2) }
            ReferenceLabel(item["title"].text, size: 12.5, lineHeight: 20, lines: 0)
            FlowLayout(spacing: 6) {
                Rows(item["options"].rows) { option in
                    TextButton(option["name"].text.isEmpty ? option["kind"].text : option["name"].text, size: 12, color: option["kind"].text.hasPrefix("allow") ? RelicStyle.background : RelicStyle.ink) {
                        sending = true
                        m.run { defer { sending = false }; try await m.post("/api/permission/" + Client.segment(item["id"].text), ["option": option["id"].text]); try await m.refresh() }
                    }.buttonStyle(ReferenceButtonStyle(primary: option["kind"].text.hasPrefix("allow"), small: true))
                }
            }
        }.padding(.vertical, 11).padding(.horizontal, 13).frame(maxWidth: 620, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.amberSoft, border: RelicStyle.amber.opacity(0.45), borderWidth: 1, radius: 12, kind: "card")).disabled(sending)
    }
}

struct ComposerView: View {
    @EnvironmentObject var m: Model
    let send: () -> Void
    @State private var focused = false
    @State private var recipientIdentity = "relic-text-button/recipients"
    @StateObject private var recipientAnchor = NativeControlAnchor()
    @State private var recipientHovered = false
    @FocusState private var recipientFocused: Bool
    private var placeholder: String { m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)]) }
    private var recipientLabel: String { m.t("composer.send_to", ["to": ReferenceText.clip(m.recipients.contains("all") ? m.t("msg.everyone") : m.list(m.recipients.map { m.name($0) }), to: 24)]) }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !m.quote.isEmpty {
                ComposerQuote()
            }
            MentionEditor(text: $m.draft, placeholder: placeholder, focusChanged: { focused = $0 }, members: m.member.isEmpty ? m.members : [], onMention: { who in m.recipients.removeAll { $0 == "all" }; if !m.recipients.contains(who) { m.recipients.append(who) } }, send: send)
                .accessibilityLabel(placeholder)
            HStack(spacing: 6) {
                if m.member.isEmpty {
                    Button {
                        recipientFocused = true
                        if m.recipientPicker { m.recipientPicker = false }
                        else if let anchor = recipientAnchor.contentBounds {
                            m.recipientAnchor = anchor; m.recipientPicker = true
                        }
                    } label: {
                        HStack(spacing: 5) {
                            ReferenceLabel(recipientLabel, size: 12.5, color: recipientHovered ? RelicStyle.ink : RelicStyle.secondary, lines: 0, owner: recipientIdentity)
                            ReferenceIcon(name: "down", size: 14, color: recipientHovered ? RelicStyle.ink : RelicStyle.secondary, owner: recipientIdentity)
                        }.padding(.horizontal, 12).frame(height: 28)
                            .modifier(RecordedSurface(background: recipientHovered ? RelicStyle.hover : RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 14, owner: recipientIdentity, hovered: recipientHovered))
                    }.buttonStyle(.plain).accessibilityIdentifier(recipientIdentity)
                        .focusable().focused($recipientFocused).focusEffectDisabled()
                        .onHover { recipientHovered = $0 }
                        .background(NativeControlAnchorMount(anchor: recipientAnchor))
                }
                Spacer(minLength: 0)
                VoiceButton(text: $m.draft, size: 32)
                ComposerSendButton(action: send).keyboardShortcut(.return, modifiers: .command)
                    .disabled(m.sending || m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty)
            }
        }.padding(.leading, 15).padding(.trailing, 11).padding(.top, 11).padding(.bottom, 9)
            .modifier(RecordedSurface(background: RelicStyle.card, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.45) : RelicStyle.border, borderWidth: 1, radius: 18, kind: "card", shadows: SurfaceShadow.small))
            .frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 16)
            .modifier(RecordedSurface(background: .clear, kind: "region"))
            .onChange(of: m.draft) { m.persistDraft() }.onChange(of: m.quote) { m.persistDraft() }
    }
}

struct ComposerSendButton: View {
    @EnvironmentObject var m: Model
    @Environment(\.isEnabled) private var enabled
    @State private var identity = "relic-icon-button/" + UUID().uuidString
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            ReferenceIcon(name: "up", size: 17, color: RelicStyle.background, owner: identity).frame(width: 32, height: 32)
                .modifier(RecordedSurface(background: RelicStyle.ink, radius: 16, owner: identity))
                .recordedOpacity(enabled ? 1 : 0.35)
        }.buttonStyle(ContentButtonStyle()).accessibilityIdentifier(identity).accessibilityLabel(m.t("common.send")).help(m.t("composer.send_title"))
    }
}

struct ThreadView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if !m.threadData["error"].text.isEmpty || m.threadData["root"].isNull {
                    OverviewBlock { ReferenceLabel(m.threadData["error"].text.isEmpty ? m.t("common.loading") : m.t("common.load_failed", ["error": m.threadData["error"].text]), size: 12.5, color: RelicStyle.muted, lines: 0) }
                } else {
                    let rows = m.conversationRows(m.threadData["replies"].rows, separators: false)
                    MessageView(item: m.threadData["root"], inThread: true).padding(.horizontal, 16).padding(.top, 18).padding(.bottom, 11)
                        .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
                        .accessibilitySortPriority(Double(rows.count * 2 + 4))
                    ReferenceLabel(m.t(m.threadData["replies"].rows.isEmpty ? "thread.no_replies" : "thread.replies", ["n": String(m.threadData["replies"].rows.count)]), size: 12, color: RelicStyle.muted).padding(.horizontal, 16).padding(.top, 10)
                        .accessibilitySortPriority(Double(rows.count * 2 + 3))
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                            MessageView(item: row.item, inThread: true, continued: row.continued).padding(.top, row.continued ? 4 : m.preferences["density"].text == "compact" ? 7 : 14)
                                .accessibilitySortPriority(Double((rows.count - index) * 2))
                        }
                    }.padding(.horizontal, 16).padding(.bottom, 16)
                    ThreadComposer().padding(.horizontal, 12).padding(.top, 10).padding(.bottom, 14)
                }
            }
        }
    }
}

struct ThreadComposer: View {
    @EnvironmentObject var m: Model
    @State private var focused = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !m.quote.isEmpty { ComposerQuote() }
            MentionEditor(text: $m.threadDraft, contextID: "thread", placeholder: m.t("thread.reply_placeholder"), focusChanged: { focused = $0 }, members: [], onMention: { _ in }, send: send).accessibilityLabel(m.t("thread.reply_placeholder"))
            HStack(spacing: 6) { Spacer(minLength: 0); VoiceButton(text: $m.threadDraft, size: 32); ComposerSendButton(action: send).disabled(m.threadSending || m.threadDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty) }
        }.padding(.leading, 15).padding(.trailing, 11).padding(.top, 11).padding(.bottom, 9)
            .modifier(RecordedSurface(background: RelicStyle.card, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.45) : RelicStyle.border, borderWidth: 1, radius: 18, kind: "card", shadows: SurfaceShadow.small))
            .onChange(of: m.threadDraft) { m.defaults.set(m.threadDraft, forKey: "thread." + m.organization + "/" + m.threadID) }
    }
    private func send() { m.run { try await m.sendThread() } }
}

struct ComposerQuote: View {
    @EnvironmentObject var m: Model
    private var text: AttributedString {
        var value = AttributedString(m.quoteAuthor.isEmpty ? "" : m.t("composer.quoting", ["who": m.quoteAuthor]))
        value.inlinePresentationIntent = .stronglyEmphasized
        value.append(AttributedString(m.quotePreviewText))
        return value
    }
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            SelectableText(value: text, color: RelicStyle.secondary, pointSize: 12.5, lineHeight: 20, maximumLines: 3)
                .frame(maxWidth: .infinity, alignment: .leading)
            IconButton(title: m.t("composer.cancel_quote"), icon: "x", size: 14, height: 22, width: 22) { m.quote = "" }
        }.padding(.leading, 13).padding(.trailing, 8).padding(.vertical, 6)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.accent, radius: 10, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "card"))
    }
}

struct DigestCard: View {
    @EnvironmentObject var m: Model
    private var hasDigest: Bool { !m.digest["text"].text.isEmpty }
    var body: some View {
        FittingScroll(maxHeight: m.windowSize.height * 0.4) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    ReferenceIcon(name: "sparkle", size: 15, color: RelicStyle.violet)
                    ReferenceLabel(m.t("digest.title"), size: 13.5, weight: 700).fixedSize()
                    if hasDigest {
                        let newer = m.messages.filter { $0["id"].integer > m.digest["last_id"].integer }.count
                        ReferenceLabel(m.t(newer > 0 ? "digest.read_newer" : "digest.read", ["n": m.digest["count"].text, "when": m.ago(m.digest["at"]), "newer": String(newer)]), size: 12.5, color: RelicStyle.muted, lines: 0)
                    }
                    Spacer(minLength: 0)
                    if m.digestPending { HStack(spacing: 6) { ProgressView().controlSize(.mini).frame(width: 10, height: 10); ReferenceLabel(m.t("digest.pending"), size: 11.5, color: RelicStyle.muted) } }
                    else { TextButton(m.t(hasDigest ? "digest.update" : "chat.digest"), size: 12) { m.run { try await m.loadDigest(true) } }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).fixedSize() }
                    if !m.secretary.isEmpty { TextButton(m.t("digest.ask"), size: 12) { m.run { try await m.askSecretary() } }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).fixedSize().help(m.t("digest.ask_title")) }
                    IconButton(title: m.t("common.collapse"), icon: "x", size: 14, height: 24, width: 24) { m.toggleDigest() }
                }
                if hasDigest { RichText(m.digest["text"].text, document: true).frame(maxWidth: .infinity, alignment: .leading) }
                else { ReferenceLabel(m.t(m.digestPending ? "digest.reading" : "digest.none"), size: 12.5, color: RelicStyle.muted, lines: 0) }
            }.padding(.horizontal, 15).padding(.top, 11).padding(.bottom, 13)
        }.modifier(RecordedSurface(background: RelicStyle.violetSoft, border: RelicStyle.violet.opacity(0.28), borderWidth: 1, radius: 12, kind: "card"))
            .frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 10)
    }
}
