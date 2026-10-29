import SwiftUI
import RelicCore

struct Overview: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(m.snapshot["org"]["purpose"].text.isEmpty ? m.t("org.no_purpose") : m.snapshot["org"]["purpose"].text).font(.headline)
            Picker(m.t("org.view_mode"), selection: $m.overviewMode) { ForEach(Choices.modes, id: \.0) { value, key in Text(m.t(key)).tag(value) } }
                .onChange(of: m.overviewMode) { m.defaults.set(m.overviewMode, forKey: "mode." + m.organization) }
            Text(m.t("decision.title")).font(.headline)
            if m.snapshot["decisions"].rows.isEmpty { Text(m.t("decision.none")).foregroundStyle(.secondary) }
            Rows(m.snapshot["decisions"].rows) { DecisionView(decision: $0) }
            if m.overviewMode != "liaison" {
                HierarchyView()
                Toggle(m.t("org.auto_wake"), isOn: Binding(get: { m.snapshot["org"]["auto_wake"].flag }, set: { value in m.run { try await m.post(m.path("/auto_wake"), ["on": value]); try await m.refresh() } }))
                HStack { Text(m.t("org.members")).font(.headline); Spacer(); Button(m.t("org.add")) { m.openMemberForm() } }
                Rows(m.members) { member in
                    Button { m.openCard(member["name"].text) } label: {
                        HStack { Avatar(member: member["name"].text); VStack(alignment: .leading) {
                            Text(member.display + " · " + m.stateLabel(member["state"].text))
                            Text(member["role"].text).font(.caption); Text(member["doing"].text).font(.caption).foregroundStyle(.secondary)
                        }; Spacer() }
                    }.buttonStyle(.plain)
                }
                HStack { Text(m.t("org.current_work")).font(.headline); Spacer(); Button(m.t("common.tasks")) { m.openDetails("tasks") } }
                if m.snapshot["tasks"].rows.isEmpty { Text(m.t("org.no_tasks")) }
                Rows(m.snapshot["tasks"].rows.filter { !["done", "dropped"].contains($0["status"].text) }) { TaskCard(task: $0) }
                DisclosureGroup(m.t("org.recently_done")) { Rows(Array(m.snapshot["tasks"].rows.filter { $0["status"].text == "done" }.suffix(5).reversed())) { TaskCard(task: $0) } }
                HStack { Text(m.t("org.protocols")).font(.headline); Spacer(); Button(m.t("org.add")) { m.sheet = .protocolForm } }
                ProtocolList()
                DisclosureGroup("Episode") {
                    if m.snapshot["episodes"].rows.isEmpty { Text(m.t("org.no_episodes")) }
                    Rows(Array(m.snapshot["episodes"].rows.reversed())) { episode in
                        DisclosureGroup(episode["id"].text + " · " + episode["title"].text) {
                            Text(m.episodeLabel(episode))
                            Text(m.t("org.episode_reflections", ["reflections": episode["reflections"].text, "participants": episode["participants"].text]))
                            RichText(episode["summary"].text); Text(pretty(episode)).font(.caption).textSelection(.enabled)
                        }
                    }
                }
            } else {
                Text(m.t("org.liaison_note"))
                if !m.secretary.isEmpty { Button(m.t("org.secretary_chip", ["name": m.name(m.secretary)])) { m.run { try await m.select(m.organization, m.secretary) } } }
                else { Button(m.t("secretary.setup_title")) { m.sheet = .secretary } }
            }
            Button(m.t("org.details")) { m.openDetails("trace") }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 8)
    }
}

struct HierarchyView: View {
    @EnvironmentObject var m: Model
    @State private var leader = ""
    @State private var close = false
    private var org: Node { m.snapshot["org"] }
    private var active: Bool { org["status"].text.isEmpty || org["status"].text == "active" }
    var body: some View {
        DisclosureGroup(m.t("org.hierarchy")) {
            VStack(alignment: .leading, spacing: 8) {
                Picker(m.t("org.parent_label"), selection: Binding(get: { org["parent"]["id"].text.isEmpty ? (org["parent"].raw as? String ?? "") : org["parent"]["id"].text }, set: { value in m.run { try await m.post(m.path("/parent"), ["parent": value]); try await m.refresh() } })) {
                    Text(m.t("org.parent_none")).tag("")
                    Rows(m.organizations.filter { !Tree.descendants(m.organization, in: m.organizations).contains($0["id"].text) && ($0["status"].text == "active") && (org["kind"].text == "subgroup" || $0["kind"].text != "subgroup") }) { Text($0["name"].text).tag($0["id"].text) }
                }.disabled(!active)
                Text(m.t("org.parent_hint")).font(.caption).foregroundStyle(.secondary)
                if org["governance"].text != "peer" {
                    Picker(m.t("common.leader"), selection: Binding(get: { org["leader"].text }, set: { leader = $0 })) {
                        Text(m.t("org.leader_unset")).tag(""); Rows(m.members) { Text($0.display).tag($0["name"].text) }
                    }.disabled(!active)
                }
                if org["kind"].text != "subgroup" {
                    Toggle(m.t("org.cabinet_toggle"), isOn: Binding(get: { org["cabinet"].flag }, set: { value in m.run { try await m.post(m.path("/cabinet"), ["on": value]); try await m.refresh() } })).disabled(!active)
                    Text(m.t(org["cabinet"].flag ? "org.cabinet_on_hint" : "org.cabinet_hint")).font(.caption)
                }
                if !org["children"].rows.isEmpty { Text(m.t("org.children")).bold() }
                Rows(org["children"].rows.filter { $0["kind"].text != "subgroup" }) { child in
                    Button { m.run { try await m.select(child["id"].text) } } label: { VStack(alignment: .leading) { Text(child["name"].text); Text(m.t("org.child_stats", ["decisions": child["decisions"].text, "blocked": child["blocked"].text, "working": child["working"].text])).font(.caption) } }
                }
                if !org["subgroups"].rows.isEmpty { Text(m.t("org.subgroups")).bold() }
                Rows(org["subgroups"].rows) { group in
                    Button(group["name"].text + " · " + (group["status"].text == "active" ? m.t("org.leader_chip", ["name": group["leader"].text]) : m.t("org.status_" + group["status"].text))) { m.run { try await m.select(group["id"].text) } }
                }
                if org["kind"].text == "subgroup" && active { Button(m.t("org.close_group"), role: .destructive) { close = true } }
                Button(m.t("chart.title")) { m.sheet = .chart }
            }.padding(.vertical, 8)
        }.confirmationDialog(m.t("org.leader_confirm", ["name": m.name(leader), "org": org["name"].text]), isPresented: Binding(get: { !leader.isEmpty }, set: { if !$0 { leader = "" } })) {
            Button(m.t("common.save")) { let who = leader; m.run { try await m.post(m.path("/leader"), ["member": who]); try await m.refresh() } }
        }.confirmationDialog(m.t("org.close_group_confirm", ["name": org["name"].text]), isPresented: $close) {
            Button(m.t("org.close_group"), role: .destructive) { m.run { try await m.post(m.path("/close"), [:]); try await m.refresh() } }
        }
    }
}

struct DecisionView: View {
    @EnvironmentObject var m: Model
    let decision: Node
    @State private var sending = false
    @State private var note = ""
    func act(_ answer: String, redact: Bool = false) {
        let org = decision["org"].text.isEmpty ? m.organization : decision["org"].text
        let route = decision["kind"].text == "approval" ? "/request" : "/trajectory_answer"
        sending = true; m.run { defer { sending = false }; var body: [String: Any] = ["request_id": decision["id"].text, "decision": answer, "note": note]; if redact { body["redact"] = true }; try await m.post(Client.org(org, route), body); try await m.refresh() }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(["label", "title", "text", "reason", "error", "detail"].map { decision[$0].text }.filter { !$0.isEmpty }.joined(separator: "\n")).textSelection(.enabled)
            if decision["kind"].text == "permission" {
                Rows(decision["options"].rows) { option in Button(option["name"].text) { sending = true; m.run { defer { sending = false }; try await m.post("/api/permission/" + Client.segment(decision["id"].text), ["option": option["id"].text]); try await m.refresh() } } }
            } else if ["approval", "trajectory"].contains(decision["kind"].text) {
                if decision["kind"].text == "trajectory" { Text(m.t("decision.trajectory", ["requester": m.name(decision["requester"].text), "which": decision["carrier"].text, "whose": m.name(decision["member"].text)])) }
                TextField(m.t("decision.reason", ["reason": ""]), text: $note)
                HStack { Button(m.t("decision.approve")) { act("approve") }; Button(m.t("decision.deny")) { act("deny") } }
                if decision["kind"].text == "trajectory" { Button(m.t("decision.approve_redacted")) { act("approve", redact: true) } }
            }
            if decision["kind"].text == "task" { Button(m.t("decision.view_task")) { m.openDetails("tasks", task: decision["id"].text) } }
            if !decision["member"].text.isEmpty { Button(m.t("decision.open_chat")) { m.run { try await m.select(m.organization, decision["member"].text) } } }
        }.padding(10).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8)).disabled(sending)
    }
}

struct TaskCard: View {
    @EnvironmentObject var m: Model
    let task: Node
    var body: some View {
        DisclosureGroup(isExpanded: Binding(get: { m.detailTask == task["id"].text }, set: { m.detailTask = $0 ? task["id"].text : "" })) {
            VStack(alignment: .leading, spacing: 8) {
                Text(m.t("details.label_title") + task["title"].text)
                if !task["created_by"].text.isEmpty { Text(m.t("details.label_created_by") + m.name(task["created_by"].text)) }
                if !task["report"].text.isEmpty { Text(m.t("report.title")).bold(); RichText(task["report"].text); Text(task["done_at"].text).font(.caption) }
                Text(m.t("details.label_evidence")).bold()
                if task["evidence"].rows.isEmpty { Text(m.t("details.no_evidence")) }
                Rows(task["evidence"].rows) { RichText($0.text) }
                if !task["owner"].text.isEmpty { Button(m.t("details.ask", ["name": m.name(task["owner"].text)])) { m.sheet = nil; m.run { try await m.select(m.organization, task["owner"].text) } } }
            }.padding(8)
        } label: {
            VStack(alignment: .leading) { Text(task["id"].text + " " + task["title"].text); Text(m.name(task["owner"].text) + " · " + m.taskLabel(task["status"].text)).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

struct ProtocolList: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(["protocols", "inherited_protocols", "replaced_protocols"], id: \.self) { key in
                if !m.snapshot[key].rows.isEmpty {
                    if key != "protocols" { Text(m.t(key == "inherited_protocols" ? "details.inherited_title" : "details.replaced_title")).bold() }
                    Rows(m.snapshot[key].rows) { p in
                        DisclosureGroup(m.t("details.protocol_head", ["id": p["id"].text, "title": p["title"].text, "kind": m.t(p["strength"].text == "strong" ? "details.strong_protocol" : "details.weak_protocol"), "status": m.protocolLabel(p["status"].text.isEmpty ? "active" : p["status"].text)])) {
                            VStack(alignment: .leading, spacing: 6) {
                                if !p["from"].text.isEmpty { Text(m.t("org.inherited_from", ["name": p["from"].text])) }
                                if !p["issued_by"].isNull { Text(m.t(p["issued_by"]["person"].flag ? "org.issued_by_person" : "org.issued_by", ["name": p["issued_by"]["name"].text])) }
                                if !p["how"].text.isEmpty { Text(m.t(p["how"].text == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ["from": p["from"].text, "at": p["at"].text, "by": p["by"].text])) }
                                if p["inherit"].flag { Text(m.t("org.protocol_inherits")) }
                                if !p["supersedes"].text.isEmpty { Text(m.t("details.label_supersedes") + p["supersedes"].text) }
                                if !p["retire_target"].text.isEmpty { Text(m.t("details.label_retires") + p["retire_target"].text) }
                                if !p["trigger"].text.isEmpty { Text(m.t("details.label_applies") + p["trigger"].text) }
                                RichText(p["guidance"].text); RichText(p["summary_for_person"].text)
                                RulesView(rules: p["rules"].rows)
                                Text(m.t("details.proposed_by", ["name": m.name(p["author"].text)]) + " · " + m.t("details.votes", ["n": p["votes"].text]) + " · " + m.t("details.uses", ["n": p["uses"].text])).font(.caption)
                            }.padding(6)
                        }
                    }
                }
            }
        }
    }
}

struct RulesView: View {
    @EnvironmentObject var m: Model
    let rules: [Node]
    var body: some View {
        Rows(rules) { rule in
            DisclosureGroup(m.t(rule["effect"].text == "check" ? "cc.code" : "org.protocols")) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(m.t("cc.scope", ["what": m.ruleScope(rule)]))
                    if rule["effect"].text == "check" {
                        Text(m.t(rule["on_error"].text == "allow" ? "cc.on_error_allow" : "cc.on_error_deny"))
                        Text(rule["code"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        Text(m.t("cc.examples")).bold()
                        Rows(rule["examples"].rows) { example in
                            Text(m.t(example["expect"].text == "allow" ? "cc.decision_allow" : example["expect"].text == "deny" ? "cc.decision_deny" : "cc.decision_review")).bold()
                            Text(pretty(example)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        }
                    }
                    Text(pretty(rule)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                }
            }
        }
    }
}
