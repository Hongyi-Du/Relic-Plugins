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
    private var who: String { m.cardMember }
    private var own: Bool { !["chat", "subagent"].contains(card["surface"].text) }
    private var hosted: Bool { own && !card["embedded"].flag && (!card["config"]["harness"].text.isEmpty || ["cli", "desktop"].contains(card["surface"].text)) }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Button { m.run { try await pickAvatar(m, member: who); try await load() } } label: { Avatar(member: who, size: 60) }.buttonStyle(.plain).help(m.t("card.change_avatar"))
                    VStack(alignment: .leading) {
                        Text(card.display).font(.title2); Text(who + (card["display_custom"].flag ? "" : " · " + m.t("card.auto_named"))).font(.caption).textSelection(.enabled)
                        HStack { if card["leader"].flag { Text(m.t("common.leader")) }; if card["secretary"].flag { Text(m.t("common.secretary")) }; if !card["ex_officio"].isNull { Text(m.t("card.ex_officio_tag")) } }.font(.caption)
                    }
                }
                HStack { TextField(m.t("card.new_name"), text: $name).help(m.t("card.rename_hint")).dictation($name); Button(m.t("common.save")) { m.run { let result = try await m.post(m.path("/rename"), ["member": who, "name": name]); status = m.t(name.isEmpty ? "card.name_reset" : "card.renamed") + " " + result["note"].text; try await m.refresh(); try await load() } } }
                LabeledContent(m.t("common.role"), value: card["role"].text.isEmpty ? m.t("card.no_role") : card["role"].text)
                LabeledContent(m.t("card.identity"), value: m.identity(card))
                LabeledContent(m.t("common.status"), value: m.stateLabel(card["state"].text) + " · " + card["detail"].text)
                if !card["doing"].text.isEmpty { LabeledContent(m.t("card.doing"), value: card["doing_at"].text.isEmpty ? card["doing"].text : m.t("card.doing_since", ["doing": card["doing"].text, "ago": m.ago(card["doing_at"])])) }
                if !card["ex_officio"]["org"].text.isEmpty { Text(m.t("card.seat_origin")).font(.caption); Button(m.t("card.ex_officio", ["org": card["ex_officio"]["org_name"].text])) { let org = card["ex_officio"]["org"].text; m.sheet = nil; m.run { try await m.select(org) } } }
                if !card["also_in"].rows.isEmpty {
                    Text(m.t("card.also_in")).bold()
                    Rows(card["also_in"].rows) { seat in Button(m.t("card.also_in_item", ["org": seat["org_name"].text, "member": seat["member"].text]) + (seat["main"].flag ? " · " + m.t("card.main_seat") : "")) { m.sheet = nil; m.run { try await m.select(seat["org"].text, seat["member"].text) } } }
                }
                if card["model_editable"].flag {
                    Picker(m.t("common.model"), selection: $model) { Text(m.t("common.default_model")).tag(""); Rows(card["models"].rows.filter { !$0.text.isEmpty }) { Text($0.text).tag($0.text) } }
                    Picker(m.t("member.effort"), selection: $effort) { Text(m.t("common.default_effort")).tag(""); Rows(card["efforts"].rows.filter { !$0.text.isEmpty }) { Text($0.text).tag($0.text) } }
                    Button(m.t("card.save_model")) { m.run { let result = try await m.post(m.path("/model"), ["member": who, "model": model, "effort": effort]); status = m.t(result["applied"].text == "now" ? "card.model_switched" : "card.model_next_turn"); try await m.refresh(); try await load() } }
                } else { LabeledContent(m.t("common.model"), value: card["model"].text.isEmpty ? m.t("common.default_model") : card["model"].text) }
                Text(card["model_note"].text).font(.caption).foregroundStyle(.secondary)
                LabeledContent(m.t("common.session"), value: card["agent"].text.isEmpty ? card["session"].text : card["agent"].text).textSelection(.enabled)
                if !card["parent"].text.isEmpty { Text(m.t("card.in_parent_session", ["parent": m.name(card["parent"].text)])) }
                if card["carriers"].integer > 1 { Text(m.t("card.session_nth", ["n": card["carriers"].text])) }
                LabeledContent(m.t("card.folder"), value: card["cwd"].text).textSelection(.enabled)
                LabeledContent(m.t("card.joined"), value: card["joined_at"].text)
                DisclosureGroup(m.t("card.owns")) { Rows(card["tasks"].rows) { TaskCard(task: $0) }; if !card["tasks"].rows.isEmpty && card["tasks"].rows.allSatisfy({ ["done", "dropped"].contains($0["status"].text) }) { Text(m.t("card.tasks_done", ["n": String(card["tasks"].rows.count)])) } }
                DisclosureGroup(m.t("card.recent")) { Rows(card["recent"].rows) { Text($0["at"].text + " · " + $0["tool"].text + " · " + $0["summary"].text).font(.caption) } }
                HStack { Button(m.t("card.message")) { m.sheet = nil; m.run { try await m.select(m.organization, who) } }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: who) } }
                Divider()
                if own && (card["embedded"].flag || hosted && Capabilities.automatic(m.platform, harness: card["harness"].text, surface: card["config"]["surface"].text)) { Button(m.t("card.new_session")) { confirmation = "fresh" }.help(m.t("card.new_session_hint")) }
                if hosted && !card["session"].text.isEmpty { Button(m.t("card.open_session")) { m.run { try await seatAction("open_session") } }.help(m.t("card.open_session_hint")) }
                if hosted { Button(m.t("card.edit_setup")) { m.openMemberForm(mode: "host", edit: who) }.help(m.t("card.edit_setup_hint")) }
                if card["harness"].text == "chatgpt" { Button(m.t(card["waiting_replies"].integer > 0 ? "card.forward_reply_waiting" : "card.forward_reply", ["n": card["waiting_replies"].text])) { m.sheet = .forward }.help(m.t("card.forward_reply_hint")) }
                if !card["session"].text.isEmpty { Button(m.t("card.leave_seat"), role: .destructive) { confirmation = "unbind" }.help(m.t("card.leave_seat_hint")) }
                if !status.isEmpty { Text(status) }
            }.padding(8)
        }.frame(minWidth: 560, idealWidth: 600, maxWidth: 760, minHeight: 380, idealHeight: 520, maxHeight: 550).accessibilityLabel(m.t("card.aria", ["name": card.display]))
        .task(id: who) { m.run { try await load() } }
        .confirmationDialog(m.t(confirmation == "fresh" ? "card.new_session_confirm" : "card.leave_seat_confirm", ["name": card.display]), isPresented: Binding(get: { !confirmation.isEmpty }, set: { if !$0 { confirmation = "" } })) {
            Button(m.t(confirmation == "fresh" ? "card.new_session" : "card.leave_seat"), role: .destructive) { let action = confirmation; m.run { try await seatAction(action) } }
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
            Text(m.t("secretary.setup_title")).font(.system(size: 17, weight: .semibold)); Text(m.t("secretary.setup_intro")).font(.system(size: 13)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            ScrollView { VStack(spacing: 8) { Rows(m.members.filter { $0["state"].text != "vacant" && !["subagent", "chat"].contains($0["surface"].text) }) { who in
                Button { m.run { let org = m.organization; try await m.post(Client.org(org, "/secretary"), ["member": who["name"].text]); m.sheet = nil; try await m.select(org, who["name"].text) } } label: {
                    HStack(spacing: 10) { Avatar(member: who["name"].text, size: 30); VStack(alignment: .leading, spacing: 3) { Text(m.t("secretary.make", ["name": who.display])).font(.system(size: 13, weight: .semibold)); Text([who["harness_label"].text, who["surface_label"].text].filter { !$0.isEmpty }.joined(separator: " · ")).font(.caption).foregroundStyle(RelicStyle.muted) }; Spacer(minLength: 0) }.relicCard()
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
            Text(m.t("forward.title", ["name": m.name(m.cardMember)])).font(.system(size: 17, weight: .semibold))
            Text(m.t(info["waiting"].rows.isEmpty ? "forward.how" : "forward.waiting", ["name": m.name(m.cardMember), "n": String(info["waiting"].rows.count), "ids": info["waiting"].rows.first?["ids"].rows.map(\.text).joined(separator: ",") ?? ""])).font(.system(size: 13)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            Text(m.t("forward.to")).font(.system(size: 12))
            HStack { TextField(m.t("forward.to_placeholder"), text: $recipients).textFieldStyle(.plain); VoiceButton(text: $recipients).labelStyle(.iconOnly) }.padding(9).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.border))
            Text(m.t("common.reply")).font(.system(size: 12))
            ZStack(alignment: .topLeading) {
                if reply.isEmpty { Text(m.t("forward.body_placeholder")).font(.system(size: 13)).foregroundStyle(RelicStyle.muted).padding(9).allowsHitTesting(false) }
                TextEditor(text: $reply).font(.system(size: 14)).scrollContentBackground(.hidden).padding(5).accessibilityLabel(m.t("common.reply"))
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
