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
            ForEach(Array(text.components(separatedBy: "```").enumerated()), id: \.offset) { index, part in
                if index % 2 == 1 {
                    ScrollView(.horizontal) { Text(part.components(separatedBy: "\n").dropFirst().joined(separator: "\n")).font(.system(.caption, design: .monospaced)).textSelection(.enabled).padding(8) }.background(.quaternary.opacity(0.4))
                } else {
                    Text((try? AttributedString(markdown: linkedPaths(part), options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(part)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }.environment(\.openURL, OpenURLAction { url in
            if url.scheme == "relic-file", let parts = URLComponents(url: url, resolvingAgainstBaseURL: false), let path = parts.queryItems?.first(where: { $0.name == "path" })?.value {
                let line = Int(parts.queryItems?.first(where: { $0.name == "line" })?.value ?? "") ?? 0
                m.run { try await m.openFile(path, line: line) }; return .handled
            }
            if url.isFileURL { m.run { try await m.openFile(url.path) }; return .handled }
            return .systemAction
        })
    }
    private func linkedPaths(_ input: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: #"(?<![\w./:\\(])/(?!/)[^\s<>\"'`|*?，。；、（）)\]]+"#) else { return input }
        var output = input
        for match in regex.matches(in: input, range: NSRange(input.startIndex..., in: input)).reversed() {
            guard let range = Range(match.range, in: output) else { continue }
            let token = String(output[range]); let parts = token.split(separator: ":")
            let line = parts.count > 1 ? Int(parts[1]) ?? 0 : 0
            let path = String(parts[0]); var url = URLComponents(); url.scheme = "relic-file"; url.host = "preview"
            url.queryItems = [.init(name: "path", value: path), .init(name: "line", value: String(line))]
            if let target = url.url?.absoluteString { output.replaceSubrange(range, with: "[" + token + "](" + target + ")") }
        }
        return output
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
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: m.preferences["density"].text == "compact" ? 8 : 16) {
                            if m.moreChat { Button(m.t("trace.load_older")) { m.run { try await m.loadOlder() } } }
                            if m.messages.isEmpty && m.conversation["steps"].rows.isEmpty { Text(m.t(m.member.isEmpty ? "chat.empty_group" : "chat.empty_private")).foregroundStyle(.secondary) }
                            Rows(m.displayMessages) { MessageView(item: $0) }
                            Rows(m.liveItems) { LiveItem(item: $0) }
                            if ["running", "working"].contains(m.liveStatus["state"].text) { Label(m.t("live.replying"), systemImage: "ellipsis") }
                            Color.clear.frame(height: 1).id("end")
                        }.padding(.vertical, 8)
                    }.onChange(of: m.selection) { proxy.scrollTo("end", anchor: .bottom) }
                    ComposerView { m.run { try await m.send(); proxy.scrollTo("end", anchor: .bottom) } }
                }
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

struct MessageView: View {
    @EnvironmentObject var m: Model
    let item: Node
    var inThread = false
    private var bodyText: String { item["body"].text.isEmpty ? item["text"].text : item["body"].text }
    private var wantsPlain: Bool { (m.plainMode && m.member.isEmpty || m.plainOne.contains(item["id"].text)) && item["from"].text != "human" && Int(item["id"].text) != nil }
    var body: some View {
        if item["type"].text == "notice" { Text(item["text"].text).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
        else if item["type"].text == "acts" {
            DisclosureGroup(m.t("step.actions", ["n": String(item["steps"].rows.count)])) { Rows(item["steps"].rows) { StepView(step: $0, member: item["member"].text) } }
        } else {
            HStack(alignment: .top, spacing: 10) {
                Button { if item["from"].text != "human" { m.openCard(item["from"].text) } } label: { Avatar(member: item["from"].text) }.buttonStyle(.plain)
                VStack(alignment: .leading, spacing: 6) {
                    HStack { Text(item["fromLabel"].text.isEmpty ? m.name(item["from"].text) : item["fromLabel"].text).bold(); Text(m.day(item["at"]) + " " + m.clock(item["at"])).foregroundStyle(.secondary) }.font(.caption)
                    if !item["to"].rows.isEmpty { Text(m.t("msg.to", ["names": item["to"].rows.map { m.name($0.text) }.joined(separator: ", ")])).font(.caption).foregroundStyle(.secondary) }
                    if item["type"].text == "receipt" { DisclosureGroup(m.t("msg.auto_receipt_to", ["names": item["to"].rows.map { m.name($0.text) }.joined(separator: ", ")])) { RichText(bodyText) } }
                    else if wantsPlain, let plain = m.plain[item["id"].text] { RichText(plain["text"].text.isEmpty ? plain.text : plain["text"].text); DisclosureGroup(m.t("msg.original")) { RichText(bodyText) } }
                    else { RichText(bodyText) }
                    if wantsPlain && m.plain[item["id"].text] == nil {
                        if m.plainFailed.contains(item["id"].text) { Button(m.t("plain.retry")) { m.run { try await m.requestPlain([item["id"].text]) } } }
                        else { Text(m.t(m.plainPending.contains(item["id"].text) ? "plain.pending" : "plain.waiting")).font(.caption) }
                    }
                    if item["from"].text == "human" && !item["read_by"].isNull {
                        DisclosureGroup(item["to"].rows.count == 1 ? m.t(item["read_by"].rows.isEmpty ? "msg.unread" : "msg.read") : m.t("msg.read_count", ["read": String(item["read_by"].rows.count), "total": String(item["to"].rows.filter { $0.text != "human" }.count)])) {
                            Text(item["read_by"].rows.map { m.name($0.text) }.joined(separator: ", ")).font(.caption)
                        }.font(.caption)
                    }
                    if !inThread, !item["thread"].isNull { Button(m.t("thread.replies", ["n": item["thread"]["count"].text]) + " · " + m.t("thread.last_reply", ["when": item["thread"]["last_at"].text])) { m.run { try await m.openThread(item["id"].text) } }.font(.caption) }
                    HStack {
                        if item["from"].text != "human", Int(item["id"].text) != nil { Button(m.t(wantsPlain ? "msg.original" : "msg.plain")) { if m.plainOne.contains(item["id"].text) { m.plainOne.remove(item["id"].text) } else { m.plainOne.insert(item["id"].text); m.run { try await m.requestPlain([item["id"].text]) } } } }
                        Button(m.t("common.quote")) { m.setQuote(bodyText, from: item["from"].text) }
                        if !inThread, Int(item["id"].text) != nil { Button(m.t("common.reply")) { m.run { try await m.openThread(item["id"].text) } }.help(m.t("msg.reply_in_thread")) }
                        Button(m.t("common.copy")) { NSPasteboard.general.clearContents(); m.notice = m.t(NSPasteboard.general.setString(bodyText, forType: .string) ? "msg.copied" : "msg.copy_failed") }
                    }.buttonStyle(.link).font(.caption)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.task(id: wantsPlain) { if wantsPlain { m.run { try await m.requestPlain([item["id"].text]) } } }
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
            DisclosureGroup(item["title"].text + " · " + item["status"].text) { Text(pretty(item)).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
        } else { RichText(item["text"].text) }
    }
}

struct ComposerView: View {
    @EnvironmentObject var m: Model
    let send: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if m.member.isEmpty {
                Menu(m.t("composer.send_to", ["to": m.recipients.contains("all") ? m.t("msg.everyone") : m.recipients.map { m.name($0) }.joined(separator: ", ")])) {
                    Button(m.t("composer.all_members")) { m.recipients = ["all"] }
                    Rows(m.members) { who in Toggle(who.display, isOn: Binding(get: { m.recipients.contains(who["name"].text) }, set: { on in m.recipients.removeAll { $0 == "all" || $0 == who["name"].text }; if on { m.recipients.append(who["name"].text) }; if m.recipients.isEmpty { m.recipients = ["all"] }; m.persistDraft() })) }
                }.fixedSize()
            }
            if !m.quote.isEmpty { HStack(alignment: .top) { Text(m.quote).font(.caption).lineLimit(3).accessibilityLabel(m.t("composer.quoting")); Spacer(); Button(m.t("composer.cancel_quote")) { m.quote = "" } }.padding(8).background(.quaternary) }
            MentionEditor(text: $m.draft, members: m.member.isEmpty ? m.members : [], onMention: { who in m.recipients.removeAll { $0 == "all" }; if !m.recipients.contains(who) { m.recipients.append(who) } }, send: send)
                .frame(minHeight: 70, maxHeight: 140).overlay(RoundedRectangle(cornerRadius: 5).stroke(.secondary.opacity(0.3)))
                .accessibilityLabel(m.t(m.member.isEmpty ? "composer.group_placeholder" : "composer.dm_placeholder", ["name": m.name(m.member)]))
            HStack { VoiceButton(text: $m.draft); Spacer(); Button(m.t("common.send"), action: send).keyboardShortcut(.return, modifiers: .command).help(m.t("composer.send_title")).disabled(m.sending || m.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
        }.onChange(of: m.draft) { m.persistDraft() }.onChange(of: m.quote) { m.persistDraft() }
    }
}

struct ThreadView: View {
    @EnvironmentObject var m: Model
    @State private var sending = false
    var body: some View {
        VStack(alignment: .leading) {
            HStack { Text(m.t("thread.replies", ["n": String(m.threadData["replies"].rows.count)])); Spacer(); Button(m.t("panel.close_thread")) { m.threadID = ""; m.setPane("overview") } }
            ScrollView { LazyVStack(alignment: .leading, spacing: 16) {
                if !m.threadData["root"].isNull { MessageView(item: m.threadData["root"], inThread: true) }
                Divider(); Rows(m.threadData["replies"].rows) { MessageView(item: $0, inThread: true) }
                if m.threadData["replies"].rows.isEmpty { Text(m.t("thread.no_replies")) }
            } }
            TextEditor(text: $m.threadDraft).frame(height: 100).accessibilityLabel(m.t("thread.reply_placeholder"))
            if !m.quote.isEmpty { HStack { Text(m.quote).lineLimit(2); Button(m.t("composer.cancel_quote")) { m.quote = "" } }.font(.caption) }
            HStack { VoiceButton(text: $m.threadDraft); Spacer(); Button(m.t("common.send")) { sending = true; m.run { defer { sending = false }; try await m.sendThread() } }.disabled(sending || m.threadDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
        }.onChange(of: m.threadDraft) { m.defaults.set(m.threadDraft, forKey: "thread." + m.organization + "/" + m.threadID) }
    }
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
            else { RichText(m.digest["text"].text); Text(m.t("digest.read", ["n": m.digest["count"].text, "when": m.digest["at"].text])).font(.caption) }
        }.padding(10).background(.tint.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
}
