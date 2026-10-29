import SwiftUI
import RelicCore

struct MemberCard: View {
    @EnvironmentObject var m: Model
    @State private var card = Node()
    @State private var name = ""
    @State private var model = ""
    @State private var effort = ""
    @State private var confirmation = ""
    @State private var status = ""
    @State private var editingName = false
    @State private var editingModel = false
    private var who: String { m.cardMember }
    private var own: Bool { !["chat", "subagent"].contains(card["surface"].text) }
    private var hosted: Bool { own && !card["embedded"].flag && (!card["config"]["harness"].text.isEmpty || ["cli", "desktop"].contains(card["surface"].text)) }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            Divider()
                VStack(alignment: .leading, spacing: 7) {
                    information
                    if !status.isEmpty { Text(status).foregroundStyle(RelicStyle.accent).fixedSize(horizontal: false, vertical: true) }
                }
            Divider()
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
            Button { m.run { try await pickAvatar(m, member: who); try await load() } } label: { Avatar(member: who, size: 60, showState: true, stateBorder: RelicStyle.card) }.buttonStyle(.plain).help(m.t("card.change_avatar"))
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 4) {
                    Text(card.display).font(RelicStyle.font(17, weight: 600)).lineLimit(2).help(card.display)
                    IconButton(title: m.t("card.rename_hint"), icon: "edit", selected: editingName) { editingName.toggle() }
                }
                Text(who + (card["display_custom"].flag ? "" : " · " + m.t("card.auto_named"))).font(Font(RelicStyle.monoFont(12))).foregroundStyle(RelicStyle.muted).lineLimit(1).help(who)
                HStack(spacing: 5) {
                    if card["leader"].flag { SmallBadge(text: m.t("common.leader"), color: RelicStyle.accent) }
                    if card["secretary"].flag { SmallBadge(text: m.t("common.secretary"), color: RelicStyle.violet) }
                    if !card["ex_officio"].isNull { SmallBadge(text: m.t("card.ex_officio_tag")) }
                }
            }
        }
    }
    @ViewBuilder private var information: some View {
        if editingName {
            HStack {
                TextField(m.t("card.new_name"), text: $name).textFieldStyle(.roundedBorder).help(m.t("card.rename_hint")).dictation($name)
                Button(m.t("common.save")) { m.run { let result = try await m.post(m.path("/rename"), ["member": who, "name": name]); status = m.t(name.isEmpty ? "card.name_reset" : "card.renamed") + " " + result["note"].text; editingName = false; try await m.refresh(); try await load() } }.buttonStyle(.borderedProminent)
            }
        }
        row("common.role") { Text(card["role"].text.isEmpty ? m.t("card.no_role") : card["role"].text) }
        row("card.identity") { Text(m.identity(card)) }
        if !card["ex_officio"]["org"].text.isEmpty {
            row("card.seat_origin") { Button(m.t("card.ex_officio", ["org": card["ex_officio"]["org_name"].text])) { let org = card["ex_officio"]["org"].text; m.sheet = nil; m.run { try await m.select(org) } }.buttonStyle(.link) }
        }
        if !card["also_in"].rows.isEmpty {
            row("card.also_in") { VStack(alignment: .leading, spacing: 5) { Rows(card["also_in"].rows) { seat in
                Button(m.t("card.also_in_item", ["org": seat["org_name"].text, "member": seat["member"].text]) + (seat["main"].flag ? " · " + m.t("card.main_seat") : "")) { m.sheet = nil; m.run { try await m.select(seat["org"].text, seat["member"].text) } }.buttonStyle(.link)
            } } }
        }
        row("common.model") {
            HStack {
                Text([card["model"].text.isEmpty ? m.t("common.default_model") : card["model"].text, card["effort"].text].filter { !$0.isEmpty }.joined(separator: " · "))
                if card["model_editable"].flag { Button(m.t(editingModel ? "common.collapse" : "common.change")) { editingModel.toggle() }.buttonStyle(.link) }
            }
        }
        if editingModel && card["model_editable"].flag { modelEditor }
        else if !card["model_editable"].flag && !card["model_note"].text.isEmpty { Text(card["model_note"].text).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true) }
        row("common.status") {
            HStack(spacing: 6) {
                SmallBadge(text: m.stateLabel(card["state"].text), color: RelicStyle.state(card["state"].text))
                if !card["detail"].text.isEmpty && card["detail"].text != m.stateLabel(card["state"].text) { Text(card["detail"].text) }
            }
        }
        if !card["doing"].text.isEmpty { row("card.doing") { Text(card["doing_at"].text.isEmpty ? card["doing"].text : m.t("card.doing_since", ["doing": card["doing"].text, "ago": m.ago(card["doing_at"])])) } }
        if !card["tasks"].rows.isEmpty {
            row("card.owns") {
                if card["tasks"].rows.allSatisfy({ ["done", "dropped"].contains($0["status"].text) }) { Text(m.t("card.tasks_done", ["n": String(card["tasks"].rows.count)])) }
                else { VStack(alignment: .leading, spacing: 0) { Rows(card["tasks"].rows.filter { !["done", "dropped"].contains($0["status"].text) }) { task in ReferenceLabel(task["id"].text + " " + task["title"].text, size: 12.5).help(task["title"].text) } } }
            }
        }
        if !card["agent"].text.isEmpty {
            row("common.session") {
                Text("subagent ") + Text(String(card["agent"].text.prefix(12))).font(Font(RelicStyle.monoFont(12.5))) + Text(card["parent"].text.isEmpty ? "" : m.t("card.in_parent_session", ["parent": m.name(card["parent"].text)]))
            }.help(card["agent"].text)
        } else if !card["session"].text.isEmpty {
            row("common.session") { Text(String(card["session"].text.prefix(18)) + (card["session"].text.count > 18 ? "…" : "")).font(Font(RelicStyle.monoFont(12.5))).help(card["session"].text) }
        }
        if !card["cwd"].text.isEmpty { row("card.folder") { Text(ReferenceText.clip(card["cwd"].text, to: 64)).font(Font(RelicStyle.monoFont(12.5))).help(card["cwd"].text) } }
        if !card["joined_at"].isNull { row("card.joined") { Text(m.day(card["joined_at"]) + " " + m.clock(card["joined_at"]) + (card["carriers"].integer > 1 ? " · " + m.t("card.session_nth", ["n": card["carriers"].text]) : "")) } }
        if !card["recent"].rows.isEmpty {
            row("card.recent") {
                VStack(alignment: .leading, spacing: 0) { Rows(Array(card["recent"].rows.prefix(4))) { recent in
                    ReferenceLabel(m.ago(recent["at"]) + " " + ToolActivity.toolName(recent["tool"].text) + " " + ReferenceText.clip(recent["summary"].text, to: 50), size: 12.5, color: RelicStyle.muted)
                } }
            }
        }

    }
    private var modelEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker(m.t("common.model"), selection: $model) {
                Text(m.t("common.default_model")).tag("")
                if !model.isEmpty && !card["models"].rows.contains(where: { $0.text == model }) { Text(model).tag(model) }
                Rows(card["models"].rows.filter { !$0.text.isEmpty }) { Text($0.text).tag($0.text) }
            }
            Picker(m.t("member.effort"), selection: $effort) {
                Text(m.t("common.default_effort")).tag("")
                if !effort.isEmpty && !card["efforts"].rows.contains(where: { $0.text == effort }) { Text(effort).tag(effort) }
                Rows(card["efforts"].rows.filter { !$0.text.isEmpty }) { Text($0.text).tag($0.text) }
            }
            Text(card["model_note"].text).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true)
            Button(m.t("card.save_model")) { m.run { let result = try await m.post(m.path("/model"), ["member": who, "model": model, "effort": effort]); status = m.t(result["applied"].text == "now" ? "card.model_switched" : "card.model_next_turn"); editingModel = false; try await m.refresh(); try await load() } }.buttonStyle(.borderedProminent)
        }.padding(10).background(RelicStyle.bubble, in: RoundedRectangle(cornerRadius: 8))
    }
    private var actions: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Button { m.sheet = nil; m.run { try await m.select(m.organization, who) } } label: { Text(m.t("card.message")).frame(maxWidth: .infinity) }.buttonStyle(ReferenceButtonStyle(primary: true))
                Button { m.openDetails("trace", member: who) } label: { Text(m.t("common.context_trace")).frame(maxWidth: .infinity) }
            }.buttonStyle(ReferenceButtonStyle())
            FlowLayout(spacing: 6) { seatActions }.padding(.top, 10).overlay(alignment: .top) { RelicStyle.line.frame(height: 1) }.font(RelicStyle.font(12, weight: 600))
        }
    }
    @ViewBuilder private var seatActions: some View {
        if own && (card["embedded"].flag || hosted && Capabilities.automatic(m.platform, harness: card["harness"].text, surface: card["config"]["surface"].text)) { Button(m.t("card.new_session")) { confirmation = "fresh" }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.new_session_hint")) }
        if hosted && !card["session"].text.isEmpty { Button(m.t("card.open_session")) { m.run { try await seatAction("open_session") } }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.open_session_hint")) }
        if hosted { Button(m.t("card.edit_setup")) { m.openMemberForm(mode: "host", edit: who) }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.edit_setup_hint")) }
        if card["harness"].text == "chatgpt" { Button(m.t(card["waiting_replies"].integer > 0 ? "card.forward_reply_waiting" : "card.forward_reply", ["n": card["waiting_replies"].text])) { m.sheet = .forward }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.forward_reply_hint")) }
        if !card["session"].text.isEmpty { Button(m.t("card.leave_seat"), role: .destructive) { confirmation = "unbind" }.buttonStyle(ReferenceButtonStyle(small: true, ghost: true)).help(m.t("card.leave_seat_hint")) }
    }
    private func row<Content: View>(_ key: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ReferenceLabel(m.t(key), size: 12.5, color: RelicStyle.muted, lines: 0).frame(width: 52, alignment: .leading)
            content().frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
        }
    }
    func load() async throws { card = try await m.get(m.path("/member/" + Client.segment(who))); name = card["display_custom"].flag ? card.display : ""; model = card["model"].text; effort = card["effort"].text }
    func seatAction(_ action: String) async throws {
        let route: String
        switch action { case "fresh": route = "/fresh"; case "unbind": route = "/unbind"; default: route = "/open_session" }
        try await m.post(m.path(route), ["member": who]); status = m.t(["fresh": "seat.fresh", "unbind": "seat.unbind", "open_session": "seat.open_session"][action] ?? "seat.done", ["name": m.name(who)]); try await m.refresh(); try await load()
    }
}

struct SecretarySetup: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(m.t("secretary.setup_title")).font(RelicStyle.font(17, weight: 600)); Text(m.t("secretary.setup_intro")).font(RelicStyle.font(13, weight: 400)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            ScrollView { VStack(spacing: 8) { Rows(m.members.filter { $0["state"].text != "vacant" && !["subagent", "chat"].contains($0["surface"].text) }) { who in
                Button { m.run { let org = m.organization; try await m.post(Client.org(org, "/secretary"), ["member": who["name"].text]); m.sheet = nil; try await m.select(org, who["name"].text) } } label: {
                    HStack(spacing: 10) { Avatar(member: who["name"].text, size: 30); VStack(alignment: .leading, spacing: 3) { Text(m.t("secretary.make", ["name": who.display])).font(RelicStyle.font(13, weight: 600)); Text([who["harness_label"].text, who["surface_label"].text].filter { !$0.isEmpty }.joined(separator: " · ")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted) }; Spacer(minLength: 0) }.relicCard()
                }.buttonStyle(QuietButtonStyle())
            } } }
            HStack { Spacer(); Button(m.t("common.cancel")) { m.sheet = nil }; Button(m.t("secretary.new_embedded")) { m.openMemberForm(secretary: true) }.buttonStyle(.borderedProminent) }
        }.frame(maxHeight: .infinity, alignment: .top)
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
            Text(m.t("forward.title", ["name": m.name(m.cardMember)])).font(RelicStyle.font(17, weight: 600))
            Text(m.t(info["waiting"].rows.isEmpty ? "forward.how" : "forward.waiting", ["name": m.name(m.cardMember), "n": String(info["waiting"].rows.count), "ids": info["waiting"].rows.first?["ids"].rows.map(\.text).joined(separator: ",") ?? ""])).font(RelicStyle.font(13, weight: 400)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            Text(m.t("forward.to")).font(RelicStyle.font(12, weight: 400))
            HStack { TextField(m.t("forward.to_placeholder"), text: $recipients).textFieldStyle(.plain); VoiceButton(text: $recipients).labelStyle(.iconOnly) }.padding(9).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.border))
            Text(m.t("common.reply")).font(RelicStyle.font(12, weight: 400))
            ZStack(alignment: .topLeading) {
                if reply.isEmpty { Text(m.t("forward.body_placeholder")).font(RelicStyle.font(13, weight: 400)).foregroundStyle(RelicStyle.muted).padding(9).allowsHitTesting(false) }
                TextEditor(text: $reply).font(RelicStyle.font(14, weight: 400)).scrollContentBackground(.hidden).padding(5).accessibilityLabel(m.t("common.reply"))
            }.frame(minHeight: 160, maxHeight: .infinity).overlay(RoundedRectangle(cornerRadius: 10).stroke(RelicStyle.border)).overlay(alignment: .bottomTrailing) { VoiceButton(text: $reply).labelStyle(.iconOnly).padding(10) }
            SaveButton(labelKey: "common.send") {
                let body = reply.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !body.isEmpty else { throw RelicError.message(m.t("forward.need_body")) }
                if body.hasPrefix("【Relic") && !acknowledged { acknowledged = true; throw RelicError.message(m.t("forward.not_reply", ["prefix": "【Relic"])) }
                try await m.post(m.path("/forward"), ["member": m.cardMember, "to": recipients, "body": body]); m.notice = m.t("forward.sent", ["name": m.name(m.cardMember)]); try await m.refresh()
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .task { m.run { info = try await m.get(m.path("/waiting?member=" + Client.segment(m.cardMember))); recipients = (info["waiting"].rows.first?["to"].rows ?? info["members"].rows).map(\.text).joined(separator: ",") } }
    }
}
