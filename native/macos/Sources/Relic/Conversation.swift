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
            else if secretaryStyle { ReferenceIcon(name: "sec", size: 16, color: RelicStyle.violet).frame(maxWidth: .infinity, maxHeight: .infinity).background(RelicStyle.violetSoft) }
            else { Text(String(m.name(member).prefix(1)).uppercased()).font(RelicStyle.font(fontSize, weight: 650)).frame(maxWidth: .infinity, maxHeight: .infinity)
                .foregroundStyle(member == "human" ? RelicStyle.background : RelicStyle.avatar(member, background: false, dark: scheme == .dark))
                .background(member == "human" ? RelicStyle.ink : RelicStyle.avatar(member, background: true, dark: scheme == .dark)) }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: radius))
            .overlay(alignment: .bottomTrailing) {
                if showState && !["", "idle"].contains(state) { StateDot(state: state, border: stateBorder).offset(x: 2, y: 2) }
            }
            .task(id: cacheKey) {
                guard !member.isEmpty else { image = nil; return }
                let path = member == "human" ? "/api/avatar" : "/api/avatar/" + Client.segment(m.organization) + "/" + Client.segment(member)
                if let data = try? await m.bytes(path) { image = NSImage(data: data) } else { image = nil }
            }.accessibilityLabel(m.name(member))
    }
}

struct RichText: View {
    @EnvironmentObject var m: Model
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(NativeMarkdown.blocks(text).enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
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
    private func inline(_ value: String) -> some View {
        SelectableText(value: NativeMarkdown.attributed(value)).help(m.t("chat.path_preview"))
    }
    @ViewBuilder private func blockView(_ block: MarkdownBlock) -> some View {
        switch block.kind {
        case "code": ScrollView(.horizontal) {
            SelectableText(value: AttributedString(block.text), pointSize: 11.25, lineHeight: 19.375, monospaced: true).fixedSize(horizontal: true, vertical: true).padding(.horizontal, 12).padding(.vertical, 10)
        }.fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 8, kind: "code"))
        case "head": SelectableText(value: NativeMarkdown.attributed(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)), weight: .bold).padding(.top, 8).padding(.bottom, 4)
        case "quote":
            SelectableText(value: quoteText(block), scale: 0.92, color: RelicStyle.secondary)
                .padding(.leading, 13).padding(.vertical, 2)
                .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, edges: EdgeInsets(top: 0, leading: 3, bottom: 0, trailing: 0), kind: "card"))
                .padding(.bottom, 8).fixedSize(horizontal: false, vertical: true)
        case "list":
            VStack(alignment: .leading, spacing: 3) { ForEach(Array(NativeMarkdown.list(block).enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top) { Text(item.marker); inline(item.text) }.padding(.leading, item.indented ? 20 : 0)
            } }
        case "table":
            ScrollView(.horizontal) { Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(Array(NativeMarkdown.table(block).enumerated()), id: \.offset) { index, row in GridRow {
                    ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                        Text(NativeMarkdown.attributed(cell)).fontWeight(index == 0 && NativeMarkdown.tableHasHeader(block) ? .semibold : .regular).textSelection(.enabled).fixedSize(horizontal: true, vertical: false).frame(minWidth: 70, alignment: .leading).padding(.horizontal, 8).padding(.vertical, 3).background(index == 0 && NativeMarkdown.tableHasHeader(block) ? RelicStyle.ink.opacity(0.04) : .clear).overlay(Rectangle().stroke(RelicStyle.border, lineWidth: 1))
                    }
                } }
            }.padding(4) }
        default: inline(block.text)
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

struct ChatView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if m.organization.isEmpty {
                VStack(spacing: 6) {
                    Text(m.t("chat.no_orgs")).font(RelicStyle.font(18, weight: 600))
                    Text(m.t("chat.no_orgs_hint")).font(RelicStyle.font(14, weight: 400)).foregroundStyle(RelicStyle.muted).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                }.padding(30).frame(maxWidth: .infinity).frame(height: m.windowSize.height * 0.7)
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
            }.padding(.vertical, 8)
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
                        if m.member.isEmpty && !inThread && m.members.contains(where: { $0["name"].text == item["from"].text }) { Text(item["from"].text).font(.system(size: 11, design: .monospaced)).foregroundStyle(RelicStyle.muted) }
                        if m.member.isEmpty && !inThread && !item["to"].rows.isEmpty { Text(recipientLabel).foregroundStyle(RelicStyle.muted).lineLimit(1).help(recipientLabel) }
                        Text(m.clock(item["at"])).foregroundStyle(RelicStyle.muted).fixedSize().help(m.day(item["at"]) + " " + m.clock(item["at"]))
                    }.font(RelicStyle.font(12, weight: 400)) }
                    VStack(alignment: .leading, spacing: 6) {
                    if item["type"].text == "receipt" { DisclosureGroup(m.t("msg.auto_receipt_to", ["names": m.list(item["to"].rows.map { m.name($0.text) })])) { RichText(bodyText.replacingOccurrences(of: #"^\[Relic auto-receipt\]\s*"#, with: "", options: .regularExpression)) } }
                    else if wantsPlain, let plain = m.plain[item["id"].text] { Label(m.t("common.plain_words"), systemImage: "sparkles").font(RelicStyle.font(11, weight: 400)).foregroundStyle(RelicStyle.violet); RichText(plain["text"].text.isEmpty ? plain.text : plain["text"].text); DisclosureGroup(m.t("msg.original")) { RichText(bodyText) } }
                    else { RichText(bodyText) }
                    if wantsPlain && m.plain[item["id"].text] == nil {
                        if m.plainFailed.contains(item["id"].text) { Button(m.t("plain.retry")) { m.run { try await m.requestPlain([item["id"].text]) } } }
                        else { Text(m.t(m.plainPending.contains(item["id"].text) ? "plain.pending" : "plain.waiting")).font(RelicStyle.font(12, weight: 400)) }
                    }
                    }.padding(.horizontal, 13).padding(.vertical, 9)
                        .modifier(RecordedSurface(background: mine ? RelicStyle.mine : wantsPlain ? RelicStyle.violetSoft : RelicStyle.bubble,
                            border: wantsPlain ? RelicStyle.violet.opacity(0.22) : .clear, borderWidth: wantsPlain ? 1 : 0, radius: 14, kind: "card",
                            cornerRadii: mine ? [14,4,14,14] : [4,14,14,14], insetLeadingWidth: item["from"].text == m.secretary ? 3 : 0, insetLeadingColor: RelicStyle.violet))
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

struct LiveTurnView: View {
    @EnvironmentObject var m: Model
    @State private var expanded = true
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if m.selectedMember["embedded"].flag, m.selectedMember["has_transcript"].flag, let prompt = m.displayLiveItems.first(where: { $0["type"].text == "prompt" }) {
                HStack(alignment: .top) { Avatar(member: "human"); RichText(prompt["text"].text) }.environment(\.selectedAuthor, "human")
            }
            HStack(alignment: .top) {
                Avatar(member: m.member)
                VStack(alignment: .leading, spacing: 8) {
                    HStack { Text(m.name(m.member)).bold(); Text(m.liveStatus["state"].text == "running" ? m.t("live.replying") : m.stateLabel(m.liveStatus["state"].text)).foregroundStyle(.secondary) }.font(RelicStyle.font(12, weight: 400))
                    let actions = m.displayLiveItems.filter { ["tool", "tool_call", "tool_result", "permission", "error"].contains($0["type"].text) }
                    if !actions.isEmpty { DisclosureGroup(m.t("live.turn_actions"), isExpanded: $expanded) { Rows(actions) { LiveItem(item: $0) } } }
                    if let reply = m.displayLiveItems.last(where: { $0["type"].text == "assistant" }) { RichText(reply["text"].text) }
                    else if m.liveStatus["state"].text == "running" { ProgressView().controlSize(.small) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.environment(\.selectedAuthor, m.member)
        }
    }
}

struct StepView: View {
    @EnvironmentObject var m: Model
    let step: Node
    let member: String
    @State private var full: Node?
    @State private var expanded = false
    private var title: String {
        if step["role"].text == "tool_call" { return ToolActivity.toolName(step["tool"].text) }
        return m.t(["user": "trace.user", "assistant": "common.reply", "thinking": "trace.thinking", "context": "trace.injected"][step["role"].text] ?? "common.result")
    }
    private var summary: String { ToolActivity.pair([step]).first?.argument ?? step["text"].text }
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 7) {
                if ["assistant", "user"].contains(step["role"].text) { RichText(step["text"].text) }
                else { Text((full ?? step)["text"].text).font(.system(size: 12, design: .monospaced)).textSelection(.enabled).fixedSize(horizontal: false, vertical: true) }
                if !step["i"].isNull && full == nil && !["assistant", "user"].contains(step["role"].text) { Button(m.t("org.click_expand")) { m.run { full = try await m.get(m.path("/step?member=" + Client.segment(member) + "&i=" + step["i"].text)) } }.buttonStyle(.link) }
            }.padding(10).frame(maxWidth: .infinity, alignment: .leading).background(RelicStyle.bubble, in: RoundedRectangle(cornerRadius: 8)).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.line)).padding(.top, 5)
        } label: {
            HStack(spacing: 6) {
                Circle().fill(step["error"].flag ? RelicStyle.red : step["role"].text == "tool_result" ? RelicStyle.green : RelicStyle.muted).frame(width: 6, height: 6)
                Text(title).font(RelicStyle.font(12, weight: 600)).fixedSize()
                Text(summary).font(.system(size: 11, design: .monospaced)).foregroundStyle(RelicStyle.muted).lineLimit(1).help(step["text"].text)
                Spacer(minLength: 4)
                Text(m.clock(step["at"])).font(RelicStyle.font(10.5, weight: 400)).foregroundStyle(RelicStyle.muted).fixedSize().help(step["at"].text)
            }
        }.padding(.vertical, 3).onAppear { expanded = ["assistant", "user"].contains(step["role"].text) }
    }
}

struct LiveItem: View {
    @EnvironmentObject var m: Model
    let item: Node
    var body: some View {
        if item["type"].text == "permission" { PermissionCard(item: item) }
        else if ["tool", "tool_call", "tool_result"].contains(item["type"].text) {
            DisclosureGroup(item["title"].text + " · " + m.t(item["status"].text == "pending" ? "live.pending" : item["status"].text == "completed" ? "task.done" : item["status"].text == "failed" ? "common.failed" : "task.working")) { Text(item["text"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
        } else { RichText(item["text"].text).foregroundStyle(item["type"].text == "error" ? .red : .primary) }
    }
}

struct PermissionCard: View {
    @EnvironmentObject var m: Model
    let item: Node
    @State private var sending = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) { ReferenceIcon(name: "bell", size: 14, color: RelicStyle.amber); Text(m.t("perm.ask")).font(RelicStyle.font(12, weight: 700)) }.foregroundStyle(RelicStyle.amber)
            Text(item["title"].text).fixedSize(horizontal: false, vertical: true)
            FlowLayout {
                Rows(item["options"].rows) { option in
                    Button(option["name"].text.isEmpty ? option["kind"].text : option["name"].text) {
                        sending = true
                        m.run { defer { sending = false }; try await m.post("/api/permission/" + Client.segment(item["id"].text), ["option": option["id"].text]); try await m.refresh() }
                    }.buttonStyle(ReferenceButtonStyle(primary: option["kind"].text.hasPrefix("allow"), small: true))
                }
            }
        }.padding(.vertical, 10).padding(.horizontal, 12).frame(maxWidth: 620, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.amberSoft, border: RelicStyle.amber.opacity(0.45), borderWidth: 1, radius: 12, kind: "card")).disabled(sending)
    }
}

struct ComposerView: View {
    @EnvironmentObject var m: Model
    let send: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !m.quote.isEmpty { HStack(alignment: .top) { Text(m.quote.replacingOccurrences(of: #"(?m)^>\s?"#, with: "", options: .regularExpression)).font(RelicStyle.font(12, weight: 400)).lineLimit(3).help(m.quote).accessibilityLabel(m.t("composer.quoting", ["who": m.quote])); Spacer(); IconButton(title: m.t("composer.cancel_quote"), icon: "x") { m.quote = "" } }.padding(8).background(RelicStyle.bubble, in: RoundedRectangle(cornerRadius: 8)) }
            MentionEditor(text: $m.draft, members: m.member.isEmpty ? m.members : [], onMention: { who in m.recipients.removeAll { $0 == "all" }; if !m.recipients.contains(who) { m.recipients.append(who) } }, send: send)
                .frame(height: 44).background(alignment: .topLeading) { if m.draft.isEmpty { Text(m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)])).font(RelicStyle.font(13, weight: 400)).foregroundStyle(RelicStyle.muted).padding(.horizontal, 6).padding(.vertical, 7).allowsHitTesting(false) } }
                .accessibilityLabel(m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)]))
            HStack {
            if m.member.isEmpty {
                Button { m.recipientPicker.toggle() } label: {
                    HStack(spacing: 4) { Text(m.t("composer.send_to", ["to": m.recipients.contains("all") ? m.t("msg.everyone") : m.list(m.recipients.map { m.name($0) })])).lineLimit(1); Image(systemName: "chevron.down").font(RelicStyle.font(9, weight: 400)) }
                }.buttonStyle(.plain).font(RelicStyle.font(12, weight: 400)).padding(.horizontal, 8).padding(.vertical, 4).background(RelicStyle.hover, in: Capsule())
                    .popover(isPresented: $m.recipientPicker, arrowEdge: .top) { RecipientPicker().environmentObject(m) }
            }
                Spacer(minLength: 4); VoiceButton(text: $m.draft).labelStyle(.iconOnly); Button(action: send) { Label(m.t("common.send"), systemImage: "arrow.up").font(RelicStyle.font(12, weight: 600)) }.labelStyle(.iconOnly).buttonStyle(.borderedProminent).buttonBorderShape(.circle).controlSize(.small).keyboardShortcut(.return, modifiers: .command).help(m.t("composer.send_title")).disabled(m.sending || m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty) }
        }.padding(12).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 18)).overlay(RoundedRectangle(cornerRadius: 18).stroke(RelicStyle.border, lineWidth: 1)).padding(.horizontal, 20).padding(.bottom, 16).onChange(of: m.draft) { m.persistDraft() }.onChange(of: m.quote) { m.persistDraft() }
    }
}

struct ThreadView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Text(m.t("thread.replies", ["n": String(m.threadData["replies"].rows.count)])).font(RelicStyle.font(13, weight: 600)); Spacer(); IconButton(title: m.t("panel.close_thread"), icon: "x") { m.closeThread() } }
            ScrollView { LazyVStack(alignment: .leading, spacing: 16) {
                if !m.threadData["root"].isNull { MessageView(item: m.threadData["root"], inThread: true) }
                Divider(); Rows(m.threadData["replies"].rows) { MessageView(item: $0, inThread: true) }
                if m.threadData["replies"].rows.isEmpty { Text(m.t("thread.no_replies")) }
            } }
            VStack(alignment: .leading, spacing: 6) {
                if !m.quote.isEmpty { HStack { Text(m.quote).lineLimit(2); IconButton(title: m.t("composer.cancel_quote"), icon: "x") { m.quote = "" } }.font(RelicStyle.font(12, weight: 400)) }
                MentionEditor(text: $m.threadDraft, members: [], onMention: { _ in }, send: send).frame(height: 56).accessibilityLabel(m.t("thread.reply_placeholder"))
                    .background(alignment: .topLeading) { if m.threadDraft.isEmpty { Text(m.t("thread.reply_placeholder")).font(RelicStyle.font(13, weight: 400)).foregroundStyle(RelicStyle.muted).padding(6).allowsHitTesting(false) } }
                HStack { Spacer(); VoiceButton(text: $m.threadDraft).labelStyle(.iconOnly); Button(action: send) { Label(m.t("common.send"), systemImage: "arrow.up") }.labelStyle(.iconOnly).buttonStyle(.borderedProminent).buttonBorderShape(.circle).controlSize(.small).help(m.t("composer.send_title")).disabled(m.threadSending || m.threadDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty) }
            }.padding(10).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 16)).overlay(RoundedRectangle(cornerRadius: 16).stroke(RelicStyle.border))
        }.padding(14).onChange(of: m.threadDraft) { m.defaults.set(m.threadDraft, forKey: "thread." + m.organization + "/" + m.threadID) }
    }
    private func send() { m.run { try await m.sendThread() } }
}

struct DigestCard: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles").foregroundStyle(RelicStyle.violet)
                VStack(alignment: .leading, spacing: 3) {
                    Text(m.t("digest.title")).font(RelicStyle.font(13, weight: 600))
                    if !m.digest["text"].text.isEmpty {
                        let newer = m.messages.filter { $0["id"].integer > m.digest["last_id"].integer }.count
                        Text(m.t(newer > 0 ? "digest.read_newer" : "digest.read", ["n": m.digest["count"].text, "when": m.ago(m.digest["at"]), "newer": String(newer)])).font(RelicStyle.font(11, weight: 400)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 4)
                Button(m.t("digest.update")) { m.run { try await m.loadDigest(true) } }.buttonStyle(.link).disabled(m.digestPending)
                if !m.secretary.isEmpty { Button(m.t("digest.ask")) { m.run { try await m.askSecretary() } }.buttonStyle(.link).help(m.t("digest.ask_title")) }
                IconButton(title: m.t("common.collapse"), icon: "x") { m.toggleDigest() }
            }
            if m.digestPending { Text(m.t("digest.pending")) }
            if m.digest["text"].text.isEmpty { Text(m.t(m.digestPending ? "digest.reading" : "digest.none")) }
            else {
                RichText(m.digest["text"].text).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.font(RelicStyle.font(12, weight: 400)).padding(12).frame(maxWidth: .infinity, alignment: .leading).background(RelicStyle.violetSoft, in: RoundedRectangle(cornerRadius: 12)).overlay(RoundedRectangle(cornerRadius: 12).stroke(RelicStyle.violet.opacity(0.3))).padding(.horizontal, 20).padding(.vertical, 10)
    }
}
