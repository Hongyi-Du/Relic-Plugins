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
            else if secretaryStyle { ReferenceIcon(name: "sec", size: 16, color: RelicStyle.violet).frame(maxWidth: .infinity, maxHeight: .infinity) }
            else { ReferenceLabel(String(m.name(member).prefix(1)).uppercased(), size: fontSize, weight: 650, color: member == "human" ? RelicStyle.background : RelicStyle.avatar(member, background: false, dark: scheme == .dark), alignment: .center, owner: identity).frame(maxWidth: .infinity, maxHeight: .infinity) }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: radius))
            .modifier(RecordedSurface(background: secretaryStyle ? RelicStyle.violetSoft : member == "human" ? RelicStyle.ink : RelicStyle.avatar(member, background: true, dark: scheme == .dark), radius: radius, kind: "avatar", owner: identity))
            .overlay(alignment: .bottomTrailing) {
                if showState && !["", "idle"].contains(state) { StateDot(state: state, border: stateBorder).offset(x: 2, y: 2) }
            }
            .task(id: cacheKey) {
                guard !member.isEmpty else { image = nil; return }
                let path = member == "human" ? "/api/avatar" : "/api/avatar/" + Client.segment(m.organization) + "/" + Client.segment(member)
                if let data = try? await m.bytes(path) { image = NSImage(data: data) } else { image = nil }
            }.accessibilityElement(children: .contain).accessibilityIdentifier(identity).accessibilityLabel(m.name(member))
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
    private var blocks: [MarkdownBlock] { NativeMarkdown.blocks(text) }
    var body: some View {
        IntrinsicMarkdownLayout(preferredWidth: preferredWidth) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                    blockView(block).padding(.top, blockGap(index))
                }
            }.padding(.bottom, blocks.last.map { blockMargins($0, last: true).bottom } ?? 0)
        }.environment(\.openURL, OpenURLAction { url in
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
        return NativeMarkdown.blocks(text).map { block -> CGFloat in
            switch block.kind {
            case "code": return NativeTextStyle.preferredWidth(NativeTextStyle.render(AttributedString(block.text), size: document ? 10.8 : 11.25, monospaced: true)) + 24
            case "head": return NativeTextStyle.preferredWidth(NativeTextStyle.render(NativeMarkdown.attributed(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)), size: document ? size * 1.02 : size, weight: .bold))
            case "quote": return NativeTextStyle.preferredWidth(NativeTextStyle.render(quoteText(block), size: size * 0.92)) + 13
            case "list": return NativeMarkdown.list(block).map { NativeTextStyle.preferredWidth(NativeTextStyle.render(NativeMarkdown.attributed($0.text), size: size)) + ($0.indented ? 40 : 22) }.max() ?? 0
            case "table": return tableWidths(block).reduce(0,+)
            default: return NativeTextStyle.preferredWidth(NativeTextStyle.render(NativeMarkdown.attributed(block.text), size: size))
            }
        }.max() ?? 0
    }
    private func inline(_ value: String) -> some View {
        SelectableText(value: NativeMarkdown.attributed(value), pointSize: baseSize, lineHeight: textLineHeight).help(m.t("chat.path_preview"))
    }
    @ViewBuilder private func blockView(_ block: MarkdownBlock) -> some View {
        switch block.kind {
        case "code": ScrollView(.horizontal) {
            SelectableText(value: AttributedString(block.text), pointSize: document ? 10.8 : 11.25, lineHeight: document ? 18.6 : 19.375, monospaced: true).fixedSize(horizontal: true, vertical: true).padding(.horizontal, 12).padding(.vertical, 10)
        }.fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 8, kind: "code"))
        case "head": SelectableText(value: NativeMarkdown.attributed(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)), weight: .bold, pointSize: document ? baseSize * 1.02 : baseSize, lineHeight: textLineHeight * (document ? 1.02 : 1))
        case "quote":
            SelectableText(value: quoteText(block), color: RelicStyle.secondary, pointSize: baseSize * 0.92, lineHeight: textLineHeight * 0.92)
                .padding(.leading, 13).padding(.vertical, 2)
                .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "card"))
                .fixedSize(horizontal: false, vertical: true)
        case "list":
            VStack(alignment: .leading, spacing: 0) { ForEach(Array(NativeMarkdown.list(block).enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 8) {
                    ReferenceLabel(item.marker, size: baseSize, lineHeight: textLineHeight, alignment: .right).frame(width: 14, alignment: .trailing)
                    inline(item.text)
                }.padding(.leading, item.indented ? 18 : 0)
            } }
        case "table":
            ScrollView(.horizontal) { Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(Array(NativeMarkdown.table(block).enumerated()), id: \.offset) { index, row in GridRow {
                    ForEach(Array(row.enumerated()), id: \.offset) { column, cell in
                        SelectableText(value: NativeMarkdown.attributed(cell), weight: index == 0 && NativeMarkdown.tableHasHeader(block) ? .semibold : .regular, pointSize: baseSize * 0.93, lineHeight: textLineHeight * 0.93)
                            .padding(.horizontal, 8).padding(.vertical, 3.5).frame(width: tableWidths(block)[column], alignment: .leading)
                            .modifier(RecordedSurface(background: index == 0 && NativeMarkdown.tableHasHeader(block) ? RelicStyle.ink.opacity(0.04) : .clear, border: RelicStyle.border, edges: EdgeInsets(top: 1, leading: 1, bottom: index == NativeMarkdown.table(block).count - 1 ? 1 : 0, trailing: column == row.count - 1 ? 1 : 0), kind: "card"))
                    }
                } }
            }.padding(.vertical, 6) }.fixedSize(horizontal: false, vertical: true)
        default: inline(block.text)
        }
    }
    private func tableWidths(_ block: MarkdownBlock) -> [CGFloat] {
        let rows = NativeMarkdown.table(block), count = rows.map(\.count).max() ?? 0
        return (0..<count).map { column in
            rows.enumerated().map { index, row in
                guard row.indices.contains(column) else { return CGFloat.zero }
                return NativeTextStyle.preferredWidth(NativeTextStyle.render(NativeMarkdown.attributed(row[column]), size: baseSize * 0.93, weight: index == 0 && NativeMarkdown.tableHasHeader(block) ? .semibold : .regular)) + 17
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
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
                ScrollView {
                    VStack(spacing: 14) {
                        ReferenceLabel(m.t("chat.no_orgs"), size: 18, weight: 650, alignment: .center)
                        ReferenceLabel(m.t("chat.no_orgs_hint"), size: 14, color: RelicStyle.muted, lines: 0, alignment: .center).padding(.bottom, 14)
                    }.padding(30).frame(maxWidth: 880).frame(maxWidth: .infinity).frame(height: m.windowSize.height * 0.7).padding(.horizontal, 20).padding(.top, 8)
                }.measuredRegion("conversation")
            } else {
                header.measuredRegion("conversation")
                if m.member.isEmpty && m.digestOpen { DigestCard() }
                if !m.member.isEmpty {
                    Text(m.banner(m.selectedMember)).font(RelicStyle.font(12, weight: 400)).padding(8).background(.quaternary.opacity(0.4))
                    Rows(m.snapshot["decisions"].rows.filter { $0["member"].text == m.member }) { DecisionView(decision: $0) }
                    if !m.selectedMember["detail"].text.isEmpty { Text(m.selectedMember["detail"].text).font(RelicStyle.font(12, weight: 400)).foregroundStyle(.secondary) }
                }
                if m.snapshot["org"]["status"].text == "closed" { Text(m.t("org.ended_closed")) }
                if m.snapshot["org"]["status"].text == "dissolved" { Text(m.t("org.ended_dissolved")) }
                ConversationStream()
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).modifier(RecordedSurface(background: RelicStyle.background, kind: "region"))
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.chat"))
    }
    private var header: some View {
        HStack(spacing: 12) {
            if m.member.isEmpty { ReferenceIcon(name: "hash", size: 14).frame(width: 28, height: 28).background(RelicStyle.hover, in: RoundedRectangle(cornerRadius: 8)) } else { Avatar(member: m.member, size: 28, secretaryStyle: m.member == m.secretary, showState: true) }
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 8) {
                    let title = m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("chat.secretary_title", ["name": m.selectedMember["role"].text.isEmpty ? m.t("common.secretary") : m.selectedMember["role"].text]) : m.name(m.member)
                    Text(title).font(RelicStyle.font(15, weight: 600)).lineLimit(1).help(title)
                    if m.member.isEmpty { Text(m.t("common.members", ["n": String(m.members.count)])).font(RelicStyle.font(15, weight: 400)).foregroundStyle(RelicStyle.muted).lineLimit(1) }
                    else {
                        if !m.selectedMember["display"].text.isEmpty && m.selectedMember["display"].text != m.member { Text(m.member).font(.system(size: 13.8, design: .monospaced)).foregroundStyle(RelicStyle.muted).lineLimit(1) }
                        if m.selectedMember["leader"].flag { SmallBadge(text: m.t("common.leader"), color: RelicStyle.accent) }
                    }
                }.frame(height: 19.5, alignment: .leading)
                let meta = m.member.isEmpty ? m.t(m.snapshot["org"]["auto_wake"].flag ? "chat.group_meta_on" : "chat.group_meta_off", ["org": m.snapshot["org"]["name"].text]) : [m.snapshot["org"]["name"].text, m.selectedMember["harness_label"].text, m.selectedMember["surface_label"].text, m.selectedMember["model"].text, m.stateLabel(m.selectedMember["state"].text)].filter { !$0.isEmpty }.joined(separator: " · ")
                Text(meta).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).lineLimit(1).help(meta).frame(height: 16.8, alignment: .leading)
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
        }.padding(.leading, 20).padding(.trailing, 14).frame(height: 56).overlay(alignment: .bottom) { RelicStyle.line.frame(height: 1) }
    }
}

private struct StreamMetrics: Equatable {
    var bottom: CGFloat = 0
    var height: CGFloat = 0
}
private struct StreamBottom: PreferenceKey {
    static var defaultValue = StreamMetrics()
    static func reduce(value: inout StreamMetrics, nextValue: () -> StreamMetrics) {
        let next = nextValue()
        if next.bottom != 0 { value.bottom = next.bottom }
        if next.height != 0 { value.height = next.height }
    }
}

struct ConversationStream: View {
    @EnvironmentObject var m: Model
    @State private var followsBottom = true
    @State private var initialLoad = true
    @State private var lastHeight: CGFloat = 0
    @State private var lastViewport: CGSize = .zero
    var body: some View {
        ScrollViewReader { proxy in
            VStack(spacing: 0) {
                GeometryReader { viewport in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            if m.moreChat { Button(m.t("trace.load_older")) { followsBottom = false; m.run { try await m.loadOlder() } } }
                            if m.messages.isEmpty && m.conversation["steps"].rows.isEmpty { Text(m.t(m.member.isEmpty ? "chat.empty_group" : "chat.empty_private")).foregroundStyle(.secondary) }
                            ForEach(m.conversationRows(m.displayMessages)) { row in
                                if let separator = row.separator { ReferenceLabel(separator, size: 11.5, color: RelicStyle.muted, alignment: .center).frame(maxWidth: .infinity).padding(.top, 18).padding(.bottom, 8) }
                                MessageView(item: row.item, continued: row.continued)
                                    .padding(.top, ["notice", "acts"].contains(row.item["type"].text) ? 0 : row.continued ? 4 : m.preferences["density"].text == "compact" ? 7 : 14)
                            }
                            if !m.displayLiveItems.isEmpty { LiveTurnView() }
                            Color.clear.frame(height: 1).id("end").background(GeometryReader { end in Color.clear.preference(key: StreamBottom.self, value: StreamMetrics(bottom: end.frame(in: .named("conversation")).maxY)) })
                        }.frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 24)
                            .background(GeometryReader { content in Color.clear.preference(key: StreamBottom.self, value: StreamMetrics(height: content.size.height)) })
                    }.defaultScrollAnchor(.bottom).coordinateSpace(name: "conversation").measuredRegion("conversation")
                        .onPreferenceChange(StreamBottom.self) { metrics in
                            // A digest, inspector resize, or late text measurement
                            // changes geometry without the person scrolling away.
                            let resized = abs(metrics.height - lastHeight) > 1 || viewport.size != lastViewport
                            if resized && followsBottom { DispatchQueue.main.async { proxy.scrollTo("end", anchor: .bottom) } }
                            else if !resized { followsBottom = metrics.bottom <= viewport.size.height + 90 }
                            lastHeight = metrics.height; lastViewport = viewport.size
                        }
                }
                ComposerView { followsBottom = true; m.run { try await m.send(); proxy.scrollTo("end", anchor: .bottom) } }.measuredRegion("composer")
            }.onChange(of: m.selection) { initialLoad = true; followsBottom = true }
                .onChange(of: m.revision) {
                    if initialLoad || followsBottom { DispatchQueue.main.async { proxy.scrollTo("end", anchor: .bottom) }; initialLoad = false }
                }
                .onAppear { proxy.scrollTo("end", anchor: .bottom) }
        }
    }
}

struct MessageView: View {
    @EnvironmentObject var m: Model
    let item: Node
    var inThread = false
    var continued = false
    @State private var threadIdentity = "relic-row/thread/" + UUID().uuidString
    @State private var hovering = false
    @State private var originalExpanded = false
    private var mine: Bool { item["from"].text == "human" }
    private var bodyText: String { item["body"].text.isEmpty ? item["text"].text : item["body"].text }
    private var groupPlain: Bool { m.plainMode && m.member.isEmpty && !inThread }
    private var wantsPlain: Bool { (groupPlain || m.plainOne.contains(item["id"].text)) && item["from"].text != "human" && Int(item["id"].text) != nil }
    private var recipientLabel: String {
        let recipients = Set(item["to"].rows.map(\.text))
        let everyone = m.members.map { $0["name"].text }.filter { $0 != item["from"].text }
        return m.t("msg.to", ["names": !everyone.isEmpty && everyone.allSatisfy(recipients.contains) ? m.t("msg.everyone") : m.list(item["to"].rows.map { m.name($0.text) })])
    }
    var body: some View {
        if item["type"].text == "notice" {
            NoticeLayout {
                ReferenceLabel(item["text"].text, size: 12, color: RelicStyle.muted, lines: 0, alignment: .center)
                    .padding(.horizontal, 10).padding(.vertical, 2).modifier(RecordedSurface(background: RelicStyle.sidebar, radius: 10, kind: "region"))
            }.padding(.top, 8)
        }
        else if item["type"].text == "acts" {
            let actions = ToolActivity.pair(item["steps"].rows)
            DisclosureGroup {
                ForEach(Array(actions.enumerated()), id: \.offset) { _, row in ActivityRow(row: row, member: item["member"].text) }
            } label: {
                HStack {
                    Text(m.t("step.actions", ["n": String(actions.count)]))
                    Text(actions.compactMap { $0.call == nil ? nil : $0.title }.prefix(4).joined(separator: " · ")).lineLimit(1).foregroundStyle(.secondary)
                    let failed = actions.filter(\.failed).count
                    if failed > 0 { Text(m.t("step.failed", ["n": String(failed)])).foregroundStyle(.red) }
                }
            }
        } else {
            HStack(alignment: .top, spacing: 10) {
                if !mine { if continued { Color.clear.frame(width: inThread ? 30 : 36, height: 0) } else { MemberCardButton(member: item["from"].text) { Avatar(member: item["fromParent"].text.isEmpty ? item["from"].text : item["fromParent"].text, size: inThread ? 30 : 36) }.buttonStyle(.plain) } }
                else { Spacer(minLength: 0) }
                VStack(alignment: mine ? .trailing : .leading, spacing: 4) {
                    if !continued { HStack(spacing: 6) {
                        Text(item["fromLabel"].text.isEmpty ? m.name(item["from"].text) : item["fromLabel"].text).font(RelicStyle.font(12.5, weight: 600)).foregroundStyle(RelicStyle.secondary).lineLimit(1)
                        if item["type"].text != "receipt" && m.member.isEmpty && !inThread && m.members.contains(where: { $0["name"].text == item["from"].text }) { Text(item["from"].text).font(.system(size: 11, design: .monospaced)).foregroundStyle(RelicStyle.muted) }
                        if item["type"].text == "receipt" { Text(m.t("msg.auto_receipt_to", ["names": m.list(item["to"].rows.map { m.name($0.text) })])).foregroundStyle(RelicStyle.muted) }
                        else if m.member.isEmpty && !inThread && !item["to"].rows.isEmpty { Text(recipientLabel).foregroundStyle(RelicStyle.muted).lineLimit(1).help(recipientLabel) }
                        Text(m.clock(item["at"])).foregroundStyle(RelicStyle.muted).fixedSize().help(m.day(item["at"]) + " " + m.clock(item["at"]))
                    }.font(RelicStyle.font(12, weight: 400)) }
                    if item["type"].text == "receipt" {
                        MessageReceipt(text: bodyText.replacingOccurrences(of: #"^\[Relic auto-receipt\]\s*"#, with: "", options: .regularExpression))
                    } else if wantsPlain, let plain = m.plain[item["id"].text] {
                        messageBubble(plain["text"].text.isEmpty ? plain.text : plain["text"].text, plain: true)
                        VStack(alignment: .leading, spacing: 0) {
                            Button { originalExpanded.toggle() } label: {
                                ReferenceLabel((originalExpanded ? "▾ " : "▸ ") + m.t("msg.original"), size: 11.5, color: RelicStyle.muted)
                                    .padding(.horizontal, 2).modifier(RecordedSurface(background: .clear, expanded: originalExpanded))
                            }.buttonStyle(.plain)
                            if originalExpanded { messageBubble(bodyText) }
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
                        ReferenceLabel(m.readReceipt(item), size: 11, color: RelicStyle.muted)
                    }
                    if !inThread, !item["thread"].isNull {
                        Button { m.run { try await m.openThread(item["id"].text) } } label: {
                            HStack(spacing: 6) {
                                HStack(spacing: -4) { Rows(Array(item["thread"]["people"].rows.prefix(3))) { person in Avatar(member: person.text, size: 20).padding(2).background(RelicStyle.background, in: RoundedRectangle(cornerRadius: 8)) } }
                                ReferenceLabel(m.t("thread.replies", ["n": item["thread"]["count"].text]), size: 12.5, weight: 600, color: RelicStyle.accent, owner: threadIdentity)
                                ReferenceLabel(m.t("thread.last_reply", ["when": m.shortWhen(item["thread"]["last_at"])]), size: 12.5, color: RelicStyle.muted, owner: threadIdentity)
                            }.padding(.leading, 4).padding(.trailing, 8).padding(.vertical, 3)
                        }.buttonStyle(QuietButtonStyle()).accessibilityIdentifier(threadIdentity)
                    }
                }.frame(maxWidth: 720, alignment: mine ? .trailing : .leading).overlay(alignment: .topTrailing) {
                    if hovering { HStack {
                        if !groupPlain, item["from"].text != "human", Int(item["id"].text) != nil { Button(m.t(wantsPlain ? "msg.original" : "msg.plain")) { if m.plainOne.contains(item["id"].text) { m.plainOne.remove(item["id"].text) } else { m.plainOne.insert(item["id"].text); m.run { try await m.requestPlain([item["id"].text]) } } }.help(m.t(wantsPlain ? "msg.hide_plain" : "common.plain_words")) }
                        Button(m.t("common.quote")) { m.setQuote(bodyText, from: item["fromLabel"].text.isEmpty ? item["from"].text : item["fromLabel"].text, stripExisting: true) }
                        if !inThread, Int(item["id"].text) != nil { Button(m.t("common.reply")) { m.run { try await m.openThread(item["id"].text) } }.help(m.t("msg.reply_in_thread")) }
                        Button(m.t("common.copy")) { NSPasteboard.general.clearContents(); m.notice = m.t(NSPasteboard.general.setString(bodyText, forType: .string) ? "msg.copied" : "msg.copy_failed") }
                    }.buttonStyle(.link).font(RelicStyle.font(11, weight: 400)).padding(5).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 6)).overlay(RoundedRectangle(cornerRadius: 6).stroke(RelicStyle.line)).offset(y: -14) }
                }
                if mine { if continued { Color.clear.frame(width: inThread ? 30 : 36, height: 0) } else { Avatar(member: "human", size: inThread ? 30 : 36) } }
                else { Spacer(minLength: 0) }
            }.onHover { hovering = $0 }.environment(\.selectedAuthor, item["from"].text).task(id: wantsPlain) { if wantsPlain { m.enqueuePlain(item["id"].text) } }
        }
    }
    private func messageBubble(_ text: String, plain: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            if plain { HStack(spacing: 4) { ReferenceIcon(name: "lang", size: 13, color: RelicStyle.violet); ReferenceLabel(m.t("msg.plain"), size: 11, weight: 650, color: RelicStyle.violet) } }
            RichText(text)
        }.padding(.horizontal, plain ? 14 : 13).padding(.vertical, plain ? 10 : 9)
            .modifier(RecordedSurface(background: mine ? RelicStyle.mine : plain ? RelicStyle.violetSoft : RelicStyle.bubble,
                border: plain ? RelicStyle.violet.opacity(0.22) : .clear, borderWidth: plain ? 1 : 0, radius: 14, kind: "card",
                cornerRadii: mine ? [14,4,14,14] : [4,14,14,14], insetLeadingWidth: item["from"].text == m.secretary ? 3 : 0, insetLeadingColor: RelicStyle.violet))
    }
}

struct MessageReceipt: View {
    let text: String
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button { expanded.toggle() } label: {
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
    let row: ToolActivity
    let member: String
    @State private var expanded = false
    @State private var full: [String: Node] = [:]
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            ForEach(Array([row.call, row.result].compactMap { $0 }.enumerated()), id: \.offset) { _, step in
                Text((full[step["i"].text] ?? step)["text"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
            }
        } label: {
            HStack { Text(row.call == nil ? m.t("common.result") : row.title).bold(); Text(row.argument).lineLimit(1); Spacer(); Text(m.clock((row.call ?? row.result ?? Node())["at"])).font(RelicStyle.font(12, weight: 400)) }
        }.foregroundStyle(row.failed ? .red : .secondary).task(id: expanded) {
            guard expanded else { return }
            for step in [row.call, row.result].compactMap({ $0 }) where step["cut"].flag && !step["i"].isNull && full[step["i"].text] == nil {
                if let result = try? await m.get(m.path("/step?member=" + Client.segment(member) + "&i=" + step["i"].text)) { full[step["i"].text] = result }
            }
        }
    }
}

struct StepView: View {
    @EnvironmentObject var m: Model
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
            Button { expanded.toggle() } label: {
                HStack(spacing: 8) {
                    Circle().fill(step["error"].flag ? RelicStyle.red : step["role"].text == "tool_result" ? RelicStyle.green : RelicStyle.faint).frame(width: 7, height: 7)
                    ReferenceLabel(title, size: 12.5, weight: 600, owner: identity).fixedSize()
                    Text(summary).font(Font(RelicStyle.monoFont(11.5))).foregroundStyle(RelicStyle.muted).lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
                    ReferenceLabel(m.clock(step["at"]), size: 11, color: RelicStyle.muted, owner: identity).fixedSize()
                }.padding(.leading, 12).padding(.trailing, 10).padding(.vertical, 3)
                    .modifier(RecordedSurface(background: .clear, owner: identity, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity)
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
    @State private var recipientIdentity = "relic-text-button/" + UUID().uuidString
    private var placeholder: String { m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)]) }
    private var recipientLabel: String { m.t("composer.send_to", ["to": ReferenceText.clip(m.recipients.contains("all") ? m.t("msg.everyone") : m.list(m.recipients.map { m.name($0) }), to: 24)]) }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !m.quote.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    ReferenceLabel(m.quote.replacingOccurrences(of: #"(?m)^>\s?"#, with: "", options: .regularExpression), size: 12.5, color: RelicStyle.secondary, lines: 3).frame(maxWidth: .infinity, alignment: .leading).help(m.quote).accessibilityLabel(m.t("composer.quoting", ["who": m.quote]))
                    IconButton(title: m.t("composer.cancel_quote"), icon: "x") { m.quote = "" }
                }.padding(.leading, 13).padding(.trailing, 8).padding(.vertical, 6)
                    .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.accent, radius: 10, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "region"))
            }
            MentionEditor(text: $m.draft, placeholder: placeholder, focusChanged: { focused = $0 }, members: m.member.isEmpty ? m.members : [], onMention: { who in m.recipients.removeAll { $0 == "all" }; if !m.recipients.contains(who) { m.recipients.append(who) } }, send: send)
                .accessibilityLabel(placeholder)
            HStack(spacing: 6) {
                if m.member.isEmpty {
                    Button { m.recipientPicker.toggle() } label: {
                        HStack(spacing: 6) {
                            ReferenceLabel(recipientLabel, size: 12.5, color: RelicStyle.secondary, owner: recipientIdentity)
                            ReferenceIcon(name: "down", size: 14, color: RelicStyle.secondary, owner: recipientIdentity)
                        }.padding(.horizontal, 10).frame(height: 28)
                            .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 9, owner: recipientIdentity))
                    }.buttonStyle(.plain).accessibilityIdentifier(recipientIdentity)
                        .background(GeometryReader { proxy in Color.clear.preference(key: RecipientAnchor.self, value: proxy.frame(in: .named("relic-window"))) })
                        .onPreferenceChange(RecipientAnchor.self) { m.recipientAnchor = $0 }
                }
                Spacer(minLength: 0)
                VoiceButton(text: $m.draft, size: 32)
                ComposerSendButton(action: send).keyboardShortcut(.return, modifiers: .command)
                    .disabled(m.sending || m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty)
            }
        }.padding(.leading, 15).padding(.trailing, 11).padding(.top, 11).padding(.bottom, 9)
            .modifier(RecordedSurface(background: RelicStyle.card, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.45) : RelicStyle.border, borderWidth: 1, radius: 18, kind: "region", shadows: SurfaceShadow.small))
            .frame(maxWidth: 880).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 16)
            .onChange(of: m.draft) { m.persistDraft() }.onChange(of: m.quote) { m.persistDraft() }
    }
}

private struct RecipientAnchor: PreferenceKey {
    static var defaultValue = CGRect.zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
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
        }.buttonStyle(.plain).accessibilityIdentifier(identity).accessibilityLabel(m.t("common.send")).help(m.t("composer.send_title"))
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
                    MessageView(item: m.threadData["root"], inThread: true).padding(.horizontal, 16).padding(.top, 18).padding(.bottom, 11)
                        .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
                    ReferenceLabel(m.t(m.threadData["replies"].rows.isEmpty ? "thread.no_replies" : "thread.replies", ["n": String(m.threadData["replies"].rows.count)]), size: 12, color: RelicStyle.muted).padding(.horizontal, 16).padding(.top, 10)
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(m.conversationRows(m.threadData["replies"].rows, separators: false)) { row in
                            MessageView(item: row.item, inThread: true, continued: row.continued).padding(.top, row.continued ? 4 : m.preferences["density"].text == "compact" ? 7 : 14)
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
            .modifier(RecordedSurface(background: RelicStyle.card, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.45) : RelicStyle.border, borderWidth: 1, radius: 18, kind: "region", shadows: SurfaceShadow.small))
            .onChange(of: m.threadDraft) { m.defaults.set(m.threadDraft, forKey: "thread." + m.organization + "/" + m.threadID) }
    }
    private func send() { m.run { try await m.sendThread() } }
}

struct ComposerQuote: View {
    @EnvironmentObject var m: Model
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            ReferenceLabel(m.quote.replacingOccurrences(of: #"(?m)^>\s?"#, with: "", options: .regularExpression), size: 12.5, color: RelicStyle.secondary, lines: 3).frame(maxWidth: .infinity, alignment: .leading).help(m.quote)
            IconButton(title: m.t("composer.cancel_quote"), icon: "x") { m.quote = "" }
        }.padding(.leading, 13).padding(.trailing, 8).padding(.vertical, 6)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.accent, radius: 10, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "region"))
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
