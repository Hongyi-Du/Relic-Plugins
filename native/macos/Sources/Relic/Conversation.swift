import SwiftUI
import AppKit
import RelicCore

struct Avatar: View {
    @EnvironmentObject var m: Model
    let member: String
    var size: CGFloat = 30
    @State private var image: NSImage?
    private var cacheKey: String {
        let avatar = m.members.first(where: { $0["name"].text == member })?["avatar"].text ?? ""
        return [m.organization, member, m.preferences["avatar"].text, avatar].joined(separator: "/")
    }
    var body: some View {
        Group {
            if let image { Image(nsImage: image).resizable().scaledToFill() }
            else { Text(String(m.name(member).prefix(1))).font(.system(size: size * 0.45)).frame(maxWidth: .infinity, maxHeight: .infinity).background(.tint.opacity(0.15)) }
        }.frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: size * 0.25))
            .task(id: cacheKey) {
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
        VStack(alignment: .leading, spacing: 5) {
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
        SelectableText(value: (try? AttributedString(markdown: NativeLinks.markdown(value), options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(value)).frame(maxWidth: .infinity, alignment: .leading).help(m.t("chat.path_preview"))
    }
    @ViewBuilder private func blockView(_ block: MarkdownBlock) -> some View {
        switch block.kind {
        case "code": ScrollView(.horizontal) { Text(block.text).font(.system(.caption, design: .monospaced)).textSelection(.enabled).padding(8) }.background(.quaternary.opacity(0.4))
        case "head": inline("**" + block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression) + "**").padding(.top, 6)
        case "quote":
            HStack(alignment: .top) { Rectangle().fill(.secondary.opacity(0.4)).frame(width: 3); inline(quoteText(block)) }.padding(6).fixedSize(horizontal: false, vertical: true).background(.quaternary.opacity(0.3)).accessibilityLabel(m.t("common.quote"))
        case "list":
            VStack(alignment: .leading, spacing: 3) { ForEach(Array(NativeMarkdown.list(block).enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top) { Text(item.marker); inline(item.text) }.padding(.leading, item.indented ? 20 : 0)
            } }
        case "table":
            ScrollView(.horizontal) { Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
                ForEach(Array(NativeMarkdown.table(block).enumerated()), id: \.offset) { index, row in GridRow {
                    ForEach(Array(row.enumerated()), id: \.offset) { _, cell in inline(index == 0 ? "**" + cell + "**" : cell).padding(4) }
                } }
            }.padding(4) }
        default: inline(block.text)
        }
    }
    private func quoteText(_ block: MarkdownBlock) -> String {
        let value = block.lines.map { $0.replacingOccurrences(of: #"^\s*>\s?"#, with: "", options: .regularExpression) }.joined(separator: "\n")
        if let range = value.range(of: #"^[^\n：:]{1,40}[：:]\s?"#, options: .regularExpression) {
            let head = String(value[range]).trimmingCharacters(in: CharacterSet(charactersIn: ":： "))
            return "**" + m.t("chat.quote_from", ["name": head]) + "**" + value[range.upperBound...]
        }
        return value
    }
}

struct ChatView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if m.organization.isEmpty {
                ContentUnavailableView(m.t("chat.no_orgs"), systemImage: "person.3", description: Text(m.t("chat.no_orgs_hint")))
                Button(m.t("common.new_org")) { m.sheet = .create }
            } else {
                header
                if m.member.isEmpty && m.digestOpen { DigestCard() }
                if !m.member.isEmpty {
                    Text(m.banner(m.selectedMember)).font(.caption).padding(8).background(.quaternary.opacity(0.4))
                    Rows(m.snapshot["decisions"].rows.filter { $0["member"].text == m.member }) { DecisionView(decision: $0) }
                    if !m.selectedMember["detail"].text.isEmpty { Text(m.selectedMember["detail"].text).font(.caption).foregroundStyle(.secondary) }
                }
                if m.snapshot["org"]["status"].text == "closed" { Text(m.t("org.ended_closed")) }
                if m.snapshot["org"]["status"].text == "dissolved" { Text(m.t("org.ended_dissolved")) }
                Divider()
                ConversationStream()
            }
        }.padding(16)
    }
    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(m.snapshot["org"]["name"].text + " · " + (m.member.isEmpty ? m.t("common.group_chat") : m.member == m.secretary ? m.t("chat.secretary_title", ["name": m.name(m.member)]) : m.name(m.member))).font(.title3)
                Spacer()
                if m.member.isEmpty {
                    Button(m.t("common.tasks")) { m.openDetails("tasks") }
                } else {
                    Button(m.t("chat.card")) { m.openCard(m.member) }
                    Button(m.t("common.context_trace")) { m.openDetails("trace") }
                    Button(m.t("chat.workspace")) { m.setPane("workspace") }
                    if m.selectedMember["embedded"].flag { Button(m.t("chat.stop_turn")) { m.run { try await m.post(m.path("/cancel"), ["member": m.member]); try await m.refresh() } } }
                }
            }
            if m.member.isEmpty {
                Text(m.t(m.snapshot["org"]["auto_wake"].flag ? "chat.group_meta_on" : "chat.group_meta_off", ["org": m.snapshot["org"]["name"].text])).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button(m.t(m.plainMode ? "chat.plain_on" : "common.plain_words")) { m.togglePlain() }.help(m.t("chat.plain_title"))
                    Button(m.t("chat.digest")) { m.toggleDigest() }.help(m.t("chat.digest_title"))
                    if m.secretary.isEmpty { Button(m.t("secretary.setup_title")) { m.sheet = .secretary } }
                }
            } else { Text(m.stateLabel(m.selectedMember["state"].text) + " · " + m.selectedMember["role"].text).font(.caption) }
        }
    }
}

private struct StreamBottom: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

struct ConversationStream: View {
    @EnvironmentObject var m: Model
    @State private var followsBottom = true
    @State private var initialLoad = true
    var body: some View {
        ScrollViewReader { proxy in
            VStack(spacing: 8) {
                GeometryReader { viewport in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: m.preferences["density"].text == "compact" ? 8 : 16) {
                            if m.moreChat { Button(m.t("trace.load_older")) { followsBottom = false; m.run { try await m.loadOlder() } } }
                            if m.messages.isEmpty && m.conversation["steps"].rows.isEmpty { Text(m.t(m.member.isEmpty ? "chat.empty_group" : "chat.empty_private")).foregroundStyle(.secondary) }
                            Rows(m.displayMessages) { MessageView(item: $0) }
                            if !m.displayLiveItems.isEmpty { LiveTurnView() }
                            Color.clear.frame(height: 1).id("end").background(GeometryReader { end in Color.clear.preference(key: StreamBottom.self, value: end.frame(in: .named("conversation")).maxY) })
                        }.padding(.vertical, 8)
                    }.coordinateSpace(name: "conversation")
                        .onPreferenceChange(StreamBottom.self) { followsBottom = $0 <= viewport.size.height + 90 }
                }
                ComposerView { followsBottom = true; m.run { try await m.send(); proxy.scrollTo("end", anchor: .bottom) } }
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
    private var bodyText: String { item["body"].text.isEmpty ? item["text"].text : item["body"].text }
    private var groupPlain: Bool { m.plainMode && m.member.isEmpty && !inThread }
    private var wantsPlain: Bool { (groupPlain || m.plainOne.contains(item["id"].text)) && item["from"].text != "human" && Int(item["id"].text) != nil }
    var body: some View {
        if item["type"].text == "notice" { Text(item["text"].text).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
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
                Button { if item["from"].text != "human" { m.openCard(item["from"].text) } } label: { Avatar(member: item["from"].text) }.buttonStyle(.plain)
                VStack(alignment: .leading, spacing: 6) {
                    HStack { Text(item["fromLabel"].text.isEmpty ? m.name(item["from"].text) : item["fromLabel"].text).bold(); Text(m.day(item["at"]) + " " + m.clock(item["at"])).foregroundStyle(.secondary) }.font(.caption)
                    if !item["to"].rows.isEmpty { Text(m.t("msg.to", ["names": m.list(item["to"].rows.map { m.name($0.text) })])).font(.caption).foregroundStyle(.secondary) }
                    if item["type"].text == "receipt" { DisclosureGroup(m.t("msg.auto_receipt_to", ["names": m.list(item["to"].rows.map { m.name($0.text) })])) { RichText(bodyText.replacingOccurrences(of: #"^\[Relic auto-receipt\]\s*"#, with: "", options: .regularExpression)) } }
                    else if wantsPlain, let plain = m.plain[item["id"].text] { RichText(plain["text"].text.isEmpty ? plain.text : plain["text"].text); DisclosureGroup(m.t("msg.original")) { RichText(bodyText) } }
                    else { RichText(bodyText) }
                    if wantsPlain && m.plain[item["id"].text] == nil {
                        if m.plainFailed.contains(item["id"].text) { Button(m.t("plain.retry")) { m.run { try await m.requestPlain([item["id"].text]) } } }
                        else { Text(m.t(m.plainPending.contains(item["id"].text) ? "plain.pending" : "plain.waiting")).font(.caption) }
                    }
                    if item["from"].text == "human" && !item["read_by"].isNull {
                        DisclosureGroup(item["to"].rows.count == 1 ? m.t(item["read_by"].rows.isEmpty ? "msg.unread" : "msg.read") : m.t("msg.read_count", ["read": String(item["read_by"].rows.count), "total": String(item["to"].rows.filter { $0.text != "human" }.count)])) {
                            Text(m.list(item["read_by"].rows.map { m.name($0.text) })).font(.caption)
                        }.font(.caption)
                    }
                    if !inThread, !item["thread"].isNull { Button(m.t("thread.replies", ["n": item["thread"]["count"].text]) + " · " + m.t("thread.last_reply", ["when": item["thread"]["last_at"].text])) { m.run { try await m.openThread(item["id"].text) } }.font(.caption) }
                    HStack {
                        if !groupPlain, item["from"].text != "human", Int(item["id"].text) != nil { Button(m.t(wantsPlain ? "msg.original" : "msg.plain")) { if m.plainOne.contains(item["id"].text) { m.plainOne.remove(item["id"].text) } else { m.plainOne.insert(item["id"].text); m.run { try await m.requestPlain([item["id"].text]) } } }.help(m.t(wantsPlain ? "msg.hide_plain" : "common.plain_words")) }
                        Button(m.t("common.quote")) { m.setQuote(bodyText, from: item["fromLabel"].text.isEmpty ? item["from"].text : item["fromLabel"].text, stripExisting: true) }
                        if !inThread, Int(item["id"].text) != nil { Button(m.t("common.reply")) { m.run { try await m.openThread(item["id"].text) } }.help(m.t("msg.reply_in_thread")) }
                        Button(m.t("common.copy")) { NSPasteboard.general.clearContents(); m.notice = m.t(NSPasteboard.general.setString(bodyText, forType: .string) ? "msg.copied" : "msg.copy_failed") }
                    }.buttonStyle(.link).font(.caption)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.environment(\.selectedAuthor, item["from"].text).task(id: wantsPlain) { if wantsPlain { m.enqueuePlain(item["id"].text) } }
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
            HStack { Text(row.call == nil ? m.t("common.result") : row.title).bold(); Text(row.argument).lineLimit(1); Spacer(); Text(m.clock((row.call ?? row.result ?? Node())["at"])).font(.caption) }
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
                    HStack { Text(m.name(m.member)).bold(); Text(m.liveStatus["state"].text == "running" ? m.t("live.replying") : m.stateLabel(m.liveStatus["state"].text)).foregroundStyle(.secondary) }.font(.caption)
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
    var body: some View {
        if ["assistant", "user"].contains(step["role"].text) {
            VStack(alignment: .leading) { Text(step["role"].text == "user" ? m.t("trace.user") : m.name(member)).font(.caption).foregroundStyle(.secondary); RichText(step["text"].text) }
        } else {
            DisclosureGroup(step["tool"].text.isEmpty ? m.t(step["role"].text == "thinking" ? "trace.thinking" : step["role"].text == "context" ? "trace.injected" : "common.result") : step["tool"].text) {
                Text((full ?? step)["text"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                if !step["i"].isNull && full == nil { Button(m.t("org.click_expand")) { m.run { full = try await m.get(m.path("/step?member=" + Client.segment(member) + "&i=" + step["i"].text)) } } }
            }.foregroundStyle(step["error"].flag ? .red : .secondary)
        }
    }
}

struct LiveItem: View {
    @EnvironmentObject var m: Model
    let item: Node
    var body: some View {
        if item["type"].text == "permission" { DecisionView(decision: Node(item.object.merging(["kind": "permission", "member": m.member]) { _, new in new })) }
        else if ["tool", "tool_call", "tool_result"].contains(item["type"].text) {
            DisclosureGroup(item["title"].text + " · " + m.t(item["status"].text == "pending" ? "live.pending" : item["status"].text == "completed" ? "task.done" : item["status"].text == "failed" ? "common.failed" : "task.working")) { Text(item["text"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
        } else { RichText(item["text"].text).foregroundStyle(item["type"].text == "error" ? .red : .primary) }
    }
}

struct ComposerView: View {
    @EnvironmentObject var m: Model
    let send: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if m.member.isEmpty {
                Menu(m.t("composer.send_to", ["to": m.recipients.contains("all") ? m.t("msg.everyone") : m.list(m.recipients.map { m.name($0) })])) {
                    Button(m.t("composer.all_members")) { m.recipients = ["all"] }
                    Rows(m.members) { who in Toggle(who.display, isOn: Binding(get: { m.recipients.contains(who["name"].text) }, set: { on in m.recipients.removeAll { $0 == "all" || $0 == who["name"].text }; if on { m.recipients.append(who["name"].text) }; if m.recipients.isEmpty { m.recipients = ["all"] }; m.persistDraft() })) }
                }.fixedSize()
            }
            if !m.quote.isEmpty { HStack(alignment: .top) { Text(m.quote).font(.caption).lineLimit(3).accessibilityLabel(m.t("composer.quoting", ["who": m.quote])); Spacer(); Button(m.t("composer.cancel_quote")) { m.quote = "" } }.padding(8).background(.quaternary) }
            MentionEditor(text: $m.draft, members: m.member.isEmpty ? m.members : [], onMention: { who in m.recipients.removeAll { $0 == "all" }; if !m.recipients.contains(who) { m.recipients.append(who) } }, send: send)
                .frame(minHeight: 70, maxHeight: 140).overlay(RoundedRectangle(cornerRadius: 5).stroke(.secondary.opacity(0.3)))
                .accessibilityLabel(m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)]))
            HStack { VoiceButton(text: $m.draft); Spacer(); Button(m.t("common.send"), action: send).keyboardShortcut(.return, modifiers: .command).help(m.t("composer.send_title")).disabled(m.sending || m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty) }
        }.onChange(of: m.draft) { m.persistDraft() }.onChange(of: m.quote) { m.persistDraft() }
    }
}

struct ThreadView: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading) {
            HStack { Text(m.t("thread.replies", ["n": String(m.threadData["replies"].rows.count)])); Spacer(); Button(m.t("panel.close_thread")) { m.closeThread() } }
            ScrollView { LazyVStack(alignment: .leading, spacing: 16) {
                if !m.threadData["root"].isNull { MessageView(item: m.threadData["root"], inThread: true) }
                Divider(); Rows(m.threadData["replies"].rows) { MessageView(item: $0, inThread: true) }
                if m.threadData["replies"].rows.isEmpty { Text(m.t("thread.no_replies")) }
            } }
            MentionEditor(text: $m.threadDraft, members: [], onMention: { _ in }, send: send).frame(height: 100).accessibilityLabel(m.t("thread.reply_placeholder"))
            if !m.quote.isEmpty { HStack { Text(m.quote).lineLimit(2); Button(m.t("composer.cancel_quote")) { m.quote = "" } }.font(.caption) }
            HStack { VoiceButton(text: $m.threadDraft); Spacer(); Button(m.t("common.send"), action: send).help(m.t("composer.send_title")).disabled(m.threadSending || m.threadDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && m.quote.isEmpty) }
        }.onChange(of: m.threadDraft) { m.defaults.set(m.threadDraft, forKey: "thread." + m.organization + "/" + m.threadID) }
    }
    private func send() { m.run { try await m.sendThread() } }
}

struct DigestCard: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading) {
            HStack {
                Text(m.t("digest.title")).font(.headline); Spacer()
                Button(m.t("digest.update")) { m.run { try await m.loadDigest(true) } }.disabled(m.digestPending)
                if !m.secretary.isEmpty { Button(m.t("digest.ask")) { m.run { try await m.askSecretary() } }.help(m.t("digest.ask_title")) }
                Button(m.t("common.collapse")) { m.toggleDigest() }
            }
            if m.digestPending { Text(m.t("digest.pending")) }
            if m.digest["text"].text.isEmpty { Text(m.t(m.digestPending ? "digest.reading" : "digest.none")) }
            else {
                RichText(m.digest["text"].text)
                let newer = m.messages.filter { $0["id"].integer > m.digest["last_id"].integer }.count
                Text(m.t(newer > 0 ? "digest.read_newer" : "digest.read", ["n": m.digest["count"].text, "when": m.ago(m.digest["at"]), "newer": String(newer)])).font(.caption)
            }
        }.padding(10).background(.tint.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
}
