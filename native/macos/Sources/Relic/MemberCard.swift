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
                        Text(card.display).font(.title2); Text(who).font(.caption).textSelection(.enabled)
                        HStack { if card["leader"].flag { Text(m.t("common.leader")) }; if card["secretary"].flag { Text(m.t("common.secretary")) }; if !card["ex_officio"].isNull { Text(m.t("card.ex_officio_tag")) } }.font(.caption)
                    }
                }
                HStack { TextField(m.t("card.new_name"), text: $name); Button(m.t("common.save")) { m.run { let result = try await m.post(m.path("/rename"), ["member": who, "name": name]); status = m.t(name.isEmpty ? "card.name_reset" : "card.renamed") + " " + result["note"].text; try await m.refresh(); try await load() } } }
                LabeledContent(m.t("common.role"), value: card["role"].text.isEmpty ? m.t("card.no_role") : card["role"].text)
                LabeledContent(m.t("card.identity"), value: m.identity(card))
                LabeledContent(m.t("common.status"), value: m.stateLabel(card["state"].text) + " · " + card["detail"].text)
                if !card["doing"].text.isEmpty { LabeledContent(m.t("card.doing"), value: card["doing"].text) }
                if !card["ex_officio"]["org"].text.isEmpty { Button(m.t("card.ex_officio", ["org": card["ex_officio"]["org_name"].text])) { let org = card["ex_officio"]["org"].text; m.sheet = nil; m.run { try await m.select(org) } } }
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
                LabeledContent(m.t("card.folder"), value: card["cwd"].text).textSelection(.enabled)
                LabeledContent(m.t("card.joined"), value: card["joined_at"].text)
                DisclosureGroup(m.t("card.owns")) { Rows(card["tasks"].rows) { TaskCard(task: $0) } }
                DisclosureGroup(m.t("card.recent")) { Rows(card["recent"].rows) { Text($0["at"].text + " · " + $0["tool"].text + " · " + $0["summary"].text).font(.caption) } }
                HStack { Button(m.t("card.message")) { m.sheet = nil; m.run { try await m.select(m.organization, who) } }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: who) } }
                Divider()
                if own && (card["embedded"].flag || hosted && Capabilities.automatic(m.platform, harness: card["harness"].text, surface: card["config"]["surface"].text)) { Button(m.t("card.new_session")) { confirmation = "fresh" }.help(m.t("card.new_session_hint")) }
                if hosted && !card["session"].text.isEmpty { Button(m.t("card.open_session")) { m.run { try await seatAction("open_session") } }.help(m.t("card.open_session_hint")) }
                if hosted { Button(m.t("card.edit_setup")) { m.openMemberForm(mode: "host", edit: who) }.help(m.t("card.edit_setup_hint")) }
                if card["harness"].text == "chatgpt" { Button(m.t("card.forward_reply")) { m.sheet = .forward }.help(m.t("card.forward_reply_hint")) }
                if !card["session"].text.isEmpty { Button(m.t("card.leave_seat"), role: .destructive) { confirmation = "unbind" }.help(m.t("card.leave_seat_hint")) }
                if !status.isEmpty { Text(status) }
            }.padding(8)
        }.frame(width: 600, height: 650)
        .task(id: who) { m.run { try await load() } }
        .confirmationDialog(m.t(confirmation == "fresh" ? "card.new_session_confirm" : "card.leave_seat_confirm", ["name": card.display]), isPresented: Binding(get: { !confirmation.isEmpty }, set: { if !$0 { confirmation = "" } })) {
            Button(m.t(confirmation == "fresh" ? "card.new_session" : "card.leave_seat"), role: .destructive) { let action = confirmation; m.run { try await seatAction(action) } }
        }
    }
    func load() async throws { card = try await m.get(m.path("/member/" + Client.segment(who))); name = card["display_custom"].flag ? card.display : ""; model = card["model"].text; effort = card["effort"].text }
    func seatAction(_ action: String) async throws {
        let route: String
        switch action { case "fresh": route = "/fresh"; case "unbind": route = "/unbind"; default: route = "/open_session" }
        try await m.post(m.path(route), ["member": who]); status = m.t("seat." + action, ["name": m.name(who)]); try await m.refresh(); try await load()
    }
}

struct SecretarySetup: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(m.t("secretary.setup_title")).font(.title2); Text(m.t("secretary.setup_intro"))
            Rows(m.members.filter { $0["state"].text != "vacant" && !["subagent", "chat"].contains($0["surface"].text) }) { who in
                Button(m.t("secretary.make", ["name": who.display])) { m.run { let org = m.organization; try await m.post(Client.org(org, "/secretary"), ["member": who["name"].text]); m.sheet = nil; try await m.select(org, who["name"].text) } }
            }
            Button(m.t("secretary.new_embedded")) { m.openMemberForm(secretary: true) }
        }.padding(10)
    }
}

struct ForwardForm: View {
    @EnvironmentObject var m: Model
    @State private var info = Node()
    @State private var recipients = ""
    @State private var reply = ""
    @State private var acknowledged = false
    var body: some View {
        Form {
            Text(m.t("forward.title", ["name": m.name(m.cardMember)])).font(.title2)
            Text(m.t(info["waiting"].rows.isEmpty ? "forward.how" : "forward.waiting", ["name": m.name(m.cardMember), "n": String(info["waiting"].rows.count), "ids": info["waiting"].rows.first?["ids"].rows.map(\.text).joined(separator: ",") ?? ""]))
            TextField(m.t("forward.to"), text: $recipients, prompt: Text(m.t("forward.to_placeholder")))
            TextField(m.t("common.reply"), text: $reply, prompt: Text(m.t("forward.body_placeholder")), axis: .vertical).lineLimit(10...20)
            VoiceButton(text: $reply)
            SaveButton {
                let body = reply.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !body.isEmpty else { throw RelicError.message(m.t("forward.need_body")) }
                if body.hasPrefix("【Relic") && !acknowledged { acknowledged = true; throw RelicError.message(m.t("forward.not_reply", ["prefix": "【Relic"])) }
                try await m.post(m.path("/forward"), ["member": m.cardMember, "to": recipients, "body": body]); try await m.refresh()
            }
        }.formStyle(.grouped).frame(width: 680, height: 520)
        .task { m.run { info = try await m.get(m.path("/waiting?member=" + Client.segment(m.cardMember))); recipients = (info["waiting"].rows.first?["to"].rows ?? info["members"].rows).map(\.text).joined(separator: ",") } }
    }
}
