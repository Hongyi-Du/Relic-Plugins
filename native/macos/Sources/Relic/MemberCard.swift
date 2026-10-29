import SwiftUI
import RelicCore

struct MemberCard: View {
    @EnvironmentObject var m: Model
    @State private var card = Node()
    @State private var name = ""
    @State private var model = ""
    @State private var effort = ""
    @State private var confirmation = ""
    @State private var editingName = false
    @State private var editingModel = false
    @State private var avatarHovered = false
    private var who: String { m.cardMember }
    private var own: Bool { !["chat", "subagent"].contains(card["surface"].text) }
    private var hosted: Bool { own && !card["embedded"].flag && (!card["config"]["harness"].text.isEmpty || ["cli", "desktop"].contains(card["surface"].text)) }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
                VStack(alignment: .leading, spacing: 7) {
                    information
                }.padding(.top, 13)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "region"))
                    .padding(.vertical, 12.5)
            actions
        }.font(RelicStyle.font(12.5, weight: 400)).frame(maxWidth: .infinity, alignment: .topLeading)
        .accessibilityElement(children: .contain).accessibilityLabel(m.t("card.aria", ["name": card.display]))
        .task(id: who) { m.run { try await load() } }
        .confirmationDialog(m.t(confirmation == "fresh" ? "card.new_session_confirm" : "card.leave_seat_confirm", ["name": card.display]), isPresented: Binding(get: { !confirmation.isEmpty }, set: { if !$0 { confirmation = "" } })) {
            Button(m.t(confirmation == "fresh" ? "card.new_session" : "card.leave_seat"), role: .destructive) { let action = confirmation; m.run { try await seatAction(action) } }
        }
    }
    private var header: some View {
        HStack(spacing: 14) {
            Button { m.run { try await pickAvatar(m, member: who); try await load() } } label: {
                Avatar(member: who, size: 60, showState: true, stateBorder: RelicStyle.card).overlay {
                    if avatarHovered {
                        ReferenceLabel(m.t("card.change_avatar"), size: 11, color: .white, lines: 0, alignment: .center).frame(width: 60, height: 60)
                            .modifier(RecordedSurface(background: .black.opacity(0.45), radius: 14, kind: "card"))
                            .accessibilityIdentifier("relic-member-avatar-hover")
                    }
                }
            }.buttonStyle(.plain).help(m.t("card.change_avatar")).accessibilityLabel(m.t("card.change_avatar")).accessibilityIdentifier("relic-row/member-avatar").onHover { avatarHovered = $0 }
            VStack(alignment: .leading, spacing: 0) {
                if editingName {
                    HStack(spacing: 6) {
                        MemberNameInput(placeholder: card.display.isEmpty ? m.t("card.new_name") : card.display, text: $name, save: saveName, cancel: { editingName = false })
                        TextButton(m.t("common.save"), size: 12, color: RelicStyle.background, action: saveName).buttonStyle(ReferenceButtonStyle(primary: true, small: true)).fixedSize()
                    }
                } else { FlowLayout(spacing: 6, centerRows: true) {
                    ReferenceLabel(card.display, size: 17, weight: 650, lineHeight: 22.1, lines: 0).help(card.display)
                    if card["leader"].flag { tag(m.t("common.leader"), color: RelicStyle.accent, background: RelicStyle.accent.opacity(0.13)) }
                    if card["secretary"].flag { tag(m.t("common.secretary"), color: RelicStyle.violet, background: RelicStyle.violetSoft) }
                    if !card["ex_officio"].isNull { tag(m.t("card.ex_officio_tag")) }
                    IconButton(title: m.t("card.rename_hint"), icon: "edit", selected: editingName, size: 14, height: 24, width: 24) { editingName.toggle() }
                } }
                ReferenceLabel(who + (card["display_custom"].flag ? "" : " · " + m.t("card.auto_named")), size: 12, color: RelicStyle.muted, lineHeight: 19.2, monospaced: true).help(who)
            }
        }
    }
    private func tag(_ text: String, color: Color = RelicStyle.secondary, background: Color = RelicStyle.hover) -> some View {
        MemberTag(text: text, color: color, background: background)
    }
    private func value(_ text: String, mono: Bool = false) -> some View {
        ReferenceLabel(text, size: mono ? 11.5 : 12.5, lineHeight: 20, lines: 0, monospaced: mono)
    }
    @ViewBuilder private var information: some View {
        row("common.role") { value(card["role"].text.isEmpty ? m.t("card.no_role") : card["role"].text) }
        row("card.identity") { value(m.identity(card)) }
        if !card["ex_officio"]["org"].text.isEmpty {
            row("card.seat_origin") { TextButton(m.t("card.ex_officio", ["org": card["ex_officio"]["org_name"].text]), size: 12.5, weight: 400, color: RelicStyle.accent, height: 20) { let org = card["ex_officio"]["org"].text; m.sheet = nil; m.run { try await m.select(org) } }.buttonStyle(.plain) }
        }
        if !card["also_in"].rows.isEmpty {
            row("card.also_in") { VStack(alignment: .leading, spacing: 3) { Rows(card["also_in"].rows) { seat in
                Button { m.sheet = nil; m.run { try await m.select(seat["org"].text, seat["member"].text) } } label: {
                    HStack(spacing: 6) {
                        ReferenceLabel(m.t("card.also_in_item", ["org": seat["org_name"].text, "member": seat["member"].text]), size: 12.5, color: RelicStyle.accent, lineHeight: 20)
                        if seat["main"].flag { tag(m.t("card.main_seat")) }
                    }
                }.buttonStyle(.plain).help(seat["role"].text)
            } } }
        }
        row("common.model") {
            VStack(alignment: .leading, spacing: 0) {
                FlowLayout(spacing: 4, centerRows: true) {
                    value([card["model"].text.isEmpty ? m.t("common.default_model") : card["model"].text, card["effort"].text].filter { !$0.isEmpty }.joined(separator: " · "))
                    if card["model_editable"].flag { TextButton(m.t(editingModel ? "common.collapse" : "common.change"), size: 12) { editingModel.toggle() }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)) }
                }
                if editingModel && card["model_editable"].flag { modelEditor.padding(.top, 6) }
                else if !card["model_editable"].flag && !card["model_note"].text.isEmpty { ReferenceLabel(card["model_note"].text, size: 11.5, color: RelicStyle.muted, lineHeight: 18.4, lines: 0).padding(.top, 2) }
            }
        }
        row("common.status") {
            HStack(spacing: 6) {
                OverviewChip(text: m.stateLabel(card["state"].text), tone: ["running", "working"].contains(card["state"].text) ? "ok" : card["state"].text == "waiting" ? "warn" : card["state"].text == "error" ? "bad" : "")
                if !card["detail"].text.isEmpty && card["detail"].text != m.stateLabel(card["state"].text) { value(card["detail"].text) }
            }
        }
        if !card["doing"].text.isEmpty { row("card.doing") { value(card["doing_at"].text.isEmpty ? card["doing"].text : m.t("card.doing_since", ["doing": card["doing"].text, "ago": m.ago(card["doing_at"])])) } }
        if !card["tasks"].rows.isEmpty {
            row("card.owns") {
                if card["tasks"].rows.allSatisfy({ ["done", "dropped"].contains($0["status"].text) }) { value(m.t("card.tasks_done", ["n": String(card["tasks"].rows.count)])) }
                else { VStack(alignment: .leading, spacing: 0) { Rows(card["tasks"].rows.filter { !["done", "dropped"].contains($0["status"].text) }) { task in ReferenceLabel(task["id"].text + " " + task["title"].text, size: 12.5).help(task["title"].text) } } }
            }
        }
        if !card["agent"].text.isEmpty {
            row("common.session") {
                Text("subagent ") + Text(String(card["agent"].text.prefix(12))).font(Font(RelicStyle.monoFont(12.5))) + Text(card["parent"].text.isEmpty ? "" : m.t("card.in_parent_session", ["parent": m.name(card["parent"].text)]))
            }.help(card["agent"].text)
        } else if !card["session"].text.isEmpty {
            row("common.session") { value(String(card["session"].text.prefix(18)) + (card["session"].text.count > 18 ? "…" : ""), mono: true).help(card["session"].text) }
        }
        if !card["cwd"].text.isEmpty { row("card.folder") { value(ReferenceText.clip(card["cwd"].text, to: 64), mono: true).help(card["cwd"].text) } }
        if !card["joined_at"].isNull { row("card.joined") { value(m.day(card["joined_at"]) + " " + m.clock(card["joined_at"]) + (card["carriers"].integer > 1 ? " · " + m.t("card.session_nth", ["n": card["carriers"].text]) : "")) } }
        if !card["recent"].rows.isEmpty {
            row("card.recent") {
                VStack(alignment: .leading, spacing: 0) { Rows(Array(card["recent"].rows.prefix(4))) { recent in
                    ReferenceLabel(m.ago(recent["at"]) + " " + ToolActivity.toolName(recent["tool"].text) + " " + ReferenceText.clip(recent["summary"].text, to: 50), size: 12.5, color: RelicStyle.muted)
                } }
            }
        }

    }
    private var modelEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            cardSelect(m.t("common.model"), value: $model, options: [("", m.t("common.default_model"))] + card["models"].rows.map { ($0.text, $0.text) })
            cardSelect(m.t("member.effort"), value: $effort, options: [("", m.t("common.default_effort"))] + card["efforts"].rows.map { ($0.text, $0.text) })
            ReferenceLabel(card["model_note"].text, size: 11.5, color: RelicStyle.muted, lineHeight: 18.4, lines: 0)
            TextButton(m.t("card.save_model"), size: 12, color: RelicStyle.background) { m.run { let result = try await m.post(m.path("/model"), ["member": who, "model": model, "effort": effort]); m.notice = m.t(result["applied"].text == "now" ? "card.model_switched" : "card.model_next_turn"); editingModel = false; try await m.refresh(); try await load() } }.buttonStyle(ReferenceButtonStyle(primary: true, small: true)).frame(maxWidth: .infinity)
        }
    }
    private func cardSelect(_ title: String, value: Binding<String>, options: [(String, String)]) -> some View {
        ReferenceSelect(title: title, selection: value, options: options, pointSize: 12.5).padding(.horizontal, 9).frame(height: 30)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 8, owner: "relic-dropdown/" + title))
    }
    private var actions: some View {
        VStack(alignment: .leading, spacing: 12) {
            CardActionLayout {
                Button { m.sheet = nil; m.run { try await m.select(m.organization, who) } } label: { ReferenceLabel(m.t("card.message"), size: 13, weight: 600, color: RelicStyle.background).frame(maxWidth: .infinity) }.buttonStyle(ReferenceButtonStyle(primary: true))
                Button { m.openDetails("trace", member: who) } label: { ReferenceLabel(m.t("common.context_trace"), size: 13, weight: 600).frame(maxWidth: .infinity) }
            }.buttonStyle(ReferenceButtonStyle())
            if hasSeatActions { FlowLayout(spacing: 6) { seatActions }.padding(.top, 11).modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "region")).font(RelicStyle.font(12, weight: 600)) }
        }
    }
    private var hasSeatActions: Bool { own && (card["embedded"].flag || hosted && Capabilities.automatic(m.platform, harness: card["harness"].text, surface: card["config"]["surface"].text)) || hosted || card["harness"].text == "chatgpt" || !card["session"].text.isEmpty }
    @ViewBuilder private var seatActions: some View {
        if own && (card["embedded"].flag || hosted && Capabilities.automatic(m.platform, harness: card["harness"].text, surface: card["config"]["surface"].text)) { Button(m.t("card.new_session")) { confirmation = "fresh" }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.new_session_hint")) }
        if hosted && !card["session"].text.isEmpty { Button(m.t("card.open_session")) { m.run { try await seatAction("open_session") } }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.open_session_hint")) }
        if hosted { Button(m.t("card.edit_setup")) { m.openMemberForm(mode: "host", edit: who) }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.edit_setup_hint")) }
        if card["harness"].text == "chatgpt" { Button(m.t(card["waiting_replies"].integer > 0 ? "card.forward_reply_waiting" : "card.forward_reply", ["n": card["waiting_replies"].text])) { m.sheet = .forward }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.forward_reply_hint")) }
        if !card["session"].text.isEmpty { Button(m.t("card.leave_seat"), role: .destructive) { confirmation = "unbind" }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.leave_seat_hint")) }
    }
    private func row<Content: View>(_ key: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ReferenceLabel(m.t(key), size: 12.5, color: RelicStyle.muted, lineHeight: 20, lines: 0).frame(width: 52, alignment: .leading)
            content().frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
        }
    }
    private func saveName() {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        m.run {
            let result = try await m.post(m.path("/rename"), ["member": who, "name": trimmed])
            m.notice = trimmed.isEmpty ? m.t("card.name_reset") : m.t("card.renamed") + (result["note"].text.isEmpty ? "" : " " + result["note"].text)
            editingName = false; try await m.refresh(); try await load()
        }
    }
    func load() async throws {
        card = try await m.get(m.path("/member/" + Client.segment(who))); name = card["display_custom"].flag ? card.display : ""
        model = card["models"].rows.contains { $0.text == card["model"].text } ? card["model"].text : ""
        effort = card["efforts"].rows.contains { $0.text == card["effort"].text } ? card["effort"].text : ""
    }
    func seatAction(_ action: String) async throws {
        let route: String
        switch action { case "fresh": route = "/fresh"; case "unbind": route = "/unbind"; default: route = "/open_session" }
        try await m.post(m.path(route), ["member": who]); m.notice = m.t(["fresh": "seat.fresh", "unbind": "seat.unbind", "open_session": "seat.open_session"][action] ?? "seat.done", ["name": m.name(who)]); try await m.refresh(); try await load()
    }
}

private struct CardActionLayout: Layout {
    private func widths(_ subviews: Subviews, available: CGFloat) -> [CGFloat] {
        let half = max(0, available - 8) / 2
        let intrinsic = subviews.map { $0.sizeThatFits(.unspecified).width }
        guard intrinsic.count == 2 else { return intrinsic }
        if intrinsic[0] > half { return [intrinsic[0], max(0, available - 8 - intrinsic[0])] }
        if intrinsic[1] > half { return [max(0, available - 8 - intrinsic[1]), intrinsic[1]] }
        return [half, half]
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? subviews.map { $0.sizeThatFits(.unspecified).width }.reduce(0,+) + 8
        let columns = widths(subviews, available: width)
        let height = subviews.enumerated().map { index, item in item.sizeThatFits(ProposedViewSize(width: columns[index], height: nil)).height }.max() ?? 0
        return CGSize(width: width, height: height)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let columns = widths(subviews, available: bounds.width)
        var x = bounds.minX
        for (index, item) in subviews.enumerated() {
            item.place(at: CGPoint(x: x, y: bounds.minY), proposal: ProposedViewSize(width: columns[index], height: bounds.height))
            x += columns[index] + 8
        }
    }
}

struct SecretarySetup: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ReferenceLabel(m.t("secretary.setup_title"), size: 17, weight: 650, lines: 0)
            ReferenceLabel(m.t("secretary.setup_intro"), size: 12.5, color: RelicStyle.muted, lines: 0)
            VStack(spacing: 6) {
                Rows(m.members.filter { $0["state"].text != "vacant" && !["subagent", "chat"].contains($0["surface"].text) }) { who in
                    Button { m.run { let org = m.organization; try await m.post(Client.org(org, "/secretary"), ["member": who["name"].text]); m.sheet = nil; try await m.select(org, who["name"].text) } } label: {
                        HStack(spacing: 10) {
                            Avatar(member: who["name"].text, size: 28)
                            VStack(alignment: .leading, spacing: 0) {
                                ReferenceLabel(m.t("secretary.make", ["name": who.display]), size: 14, weight: 700, lines: 0)
                                ReferenceLabel([who["harness_label"].text, who["surface_label"].text].filter { !$0.isEmpty }.joined(separator: " · "), size: 12, color: RelicStyle.muted, lines: 0)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }.padding(.horizontal, 12).padding(.vertical, 10)
                            .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 10, kind: "card"))
                    }.buttonStyle(.plain)
                }
            }
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                TextButton(m.t("common.cancel"), size: 13) { m.sheet = nil }.buttonStyle(ReferenceButtonStyle())
                TextButton(m.t("secretary.new_embedded"), size: 13, color: RelicStyle.background) { m.openMemberForm(secretary: true) }.buttonStyle(ReferenceButtonStyle(primary: true))
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ForwardForm: View {
    @EnvironmentObject var m: Model
    @State private var info = Node()
    @State private var recipients = ""
    @State private var reply = ""
    @State private var acknowledged = false
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ReferenceLabel(m.t("forward.title", ["name": m.name(m.cardMember)]), size: 17, weight: 650, lines: 0)
            ReferenceLabel(m.t(info["waiting"].rows.isEmpty ? "forward.how" : "forward.waiting", ["name": m.name(m.cardMember), "n": String(info["waiting"].rows.count), "ids": info["waiting"].rows.first?["ids"].rows.map(\.text).joined(separator: ",") ?? ""]), size: 12.5, color: RelicStyle.muted, lines: 0)
            VStack(alignment: .leading, spacing: 12) {
                NativeFormField(title: m.t("forward.to")) { ReferenceInput(placeholder: m.t("forward.to_placeholder"), text: $recipients, height: 36, pointSize: 12.5) }
                NativeFormField(title: m.t("common.reply")) { NativeTextArea(placeholder: m.t("forward.body_placeholder"), text: $reply, rows: 10, voice: false) }
            }
            SaveButton(labelKey: "common.send", reserveErrorSpace: true) {
                let body = reply.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !body.isEmpty else { throw RelicError.message(m.t("forward.need_body")) }
                if body.hasPrefix("【Relic") && !acknowledged { acknowledged = true; throw RelicError.message(m.t("forward.not_reply", ["prefix": "【Relic"])) }
                try await m.post(m.path("/forward"), ["member": m.cardMember, "to": recipients, "body": body]); m.notice = m.t("forward.sent", ["name": m.name(m.cardMember)]); try await m.refresh()
            }
        }.frame(maxWidth: .infinity, alignment: .topLeading)
        .task { m.run { info = try await m.get(m.path("/waiting?member=" + Client.segment(m.cardMember))); recipients = (info["waiting"].rows.first?["to"].rows ?? info["members"].rows).map(\.text).joined(separator: ",") } }
    }
}
