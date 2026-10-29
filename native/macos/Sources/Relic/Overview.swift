import SwiftUI
import RelicCore

struct Overview: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(m.t("org.heading")).font(.system(size: 12)).foregroundStyle(RelicStyle.muted); Spacer(minLength: 4)
                Picker(m.t("org.view_mode"), selection: $m.overviewMode) { ForEach(Choices.modes, id: \.0) { value, key in Text(m.t(key)).tag(value) } }.labelsHidden().pickerStyle(.segmented).frame(maxWidth: 190)
                    .onChange(of: m.overviewMode) { m.defaults.set(m.overviewMode, forKey: "mode." + m.organization); if m.overviewMode == "liaison" && !m.secretary.isEmpty && m.member != m.secretary { m.run { try await m.select(m.organization, m.secretary) } } }
            }
            Text(m.snapshot["org"]["name"].text).font(.system(size: 15, weight: .semibold))
            Text(m.snapshot["org"]["purpose"].text.isEmpty ? m.t("org.no_purpose") : m.snapshot["org"]["purpose"].text).font(.system(size: 13)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 5) {
                SmallBadge(text: m.t(m.snapshot["org"]["kind"].text == "subgroup" ? "org.kind_subgroup" : "org.kind_formal"))
                SmallBadge(text: m.t(m.snapshot["org"]["governance"].text == "peer" ? "org.gov_peer" : "org.gov_leader"))
                SmallBadge(text: m.t("common.members", ["n": String(m.members.count)]))
            }
            if !m.snapshot["org"]["leader"].text.isEmpty { SmallBadge(text: m.t(m.snapshot["org"]["cabinet"].flag ? "org.secretary_general_chip" : "org.leader_chip", ["name": m.name(m.snapshot["org"]["leader"].text)])) }
            if !m.secretary.isEmpty { Button { m.run { try await m.select(m.organization, m.secretary) } } label: { SmallBadge(text: m.t("org.secretary_chip", ["name": m.name(m.secretary)]), color: RelicStyle.violet) }.buttonStyle(.plain) }
            HStack(alignment: .top, spacing: 7) {
                Toggle("", isOn: Binding(get: { m.snapshot["org"]["auto_wake"].flag }, set: { value in m.run { try await m.post(m.path("/auto_wake"), ["on": value]); try await m.refresh() } })).labelsHidden().toggleStyle(.switch).controlSize(.mini).accessibilityLabel(m.t("org.auto_wake"))
                Text(m.t("org.auto_wake")).font(.system(size: 12)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Divider().padding(.vertical, 4)
            Text(m.t("decision.title")).font(.headline)
            if m.snapshot["decisions"].rows.isEmpty { Text(m.t("decision.none")).foregroundStyle(.secondary) }
            Rows(m.snapshot["decisions"].rows) { DecisionView(decision: $0) }
            HierarchyView()
            currentWork
            if m.overviewMode != "liaison" {
                HStack { Text(m.t("org.members")).font(.headline); Spacer(); Button(m.t("org.add")) { m.openMemberForm() } }
                Rows(m.members) { member in
                    Button { m.openCard(member["name"].text) } label: {
                        HStack { Avatar(member: member["name"].text); VStack(alignment: .leading) {
                            Text((member["secretary"].flag ? m.t("org.member_secretary", ["name": member.display]) : member.display) + " · " + m.stateLabel(member["state"].text))
                            Text(member["role"].text).font(.caption); Text(member["doing"].text).font(.caption).foregroundStyle(.secondary)
                        }; Spacer() }
                    }.buttonStyle(.plain)
                }
                HStack { Text(m.t("org.protocols")).font(.headline); Spacer(); Button(m.t("org.add")) { m.sheet = .protocolForm } }
                Text(m.t("org.protocols_active", ["n": String(m.snapshot["protocols"].rows.filter { $0["status"].text == "active" }.count)])).font(.caption)
                if m.snapshot["protocols"].rows.isEmpty && m.snapshot["inherited_protocols"].rows.isEmpty { Text(m.t("org.no_protocols")) }
                ProtocolList()
                DisclosureGroup(m.t("native.episodes")) {
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
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 8).buttonStyle(.borderless).controlSize(.small)
    }
    private var currentWork: some View {
        let tasks = m.snapshot["tasks"].rows, open = tasks.filter { !["done", "dropped"].contains($0["status"].text) }, done = tasks.filter { $0["status"].text == "done" }
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Button(m.t("org.current_work")) { m.openDetails("tasks", filter: "open") }.font(.headline)
                Spacer(); Button(m.t("org.done_count", ["n": String(done.count)])) { m.openDetails("tasks", filter: "done") }.font(.caption)
            }
            if tasks.isEmpty { Text(m.t("org.no_tasks")) }
            else if open.isEmpty { Text(m.t("org.nothing_open", ["n": String(done.count)])) }
            Rows(Array(open.prefix(8))) { TaskCard(task: $0) }
            if open.count > 8 { Button(m.t("common.more_items", ["n": String(open.count - 8)])) { m.openDetails("tasks", filter: "open") } }
            let reports = done.filter { !$0["report"].text.isEmpty }.sorted { $0["done_at"].text > $1["done_at"].text }
            if !reports.isEmpty { Text(m.t("org.recently_done")).font(.headline); Rows(Array(reports.prefix(3))) { TaskCard(task: $0) } }
        }
    }
}

struct HierarchyView: View {
    @EnvironmentObject var m: Model
    @State private var leader = ""
    @State private var close = false
    @State private var expanded = true
    private var org: Node { m.snapshot["org"] }
    private var active: Bool { org["status"].text.isEmpty || org["status"].text == "active" }
    var body: some View {
        DisclosureGroup(m.t("org.hierarchy"), isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 8) {
                Picker(m.t("org.parent_label"), selection: Binding(get: { org["parent"]["id"].text.isEmpty ? (org["parent"].raw as? String ?? "") : org["parent"]["id"].text }, set: { value in m.run { do { try await m.post(m.path("/parent"), ["parent": value]); try await m.refresh() } catch { throw RelicError.message(m.t("org.parent_failed", ["error": error.localizedDescription])) } } })) {
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
                    Toggle(m.t("org.cabinet_toggle"), isOn: Binding(get: { org["cabinet"].flag }, set: { value in m.run { do { try await m.post(m.path("/cabinet"), ["on": value]); try await m.refresh() } catch { throw RelicError.message(m.t("org.cabinet_failed", ["error": error.localizedDescription])) } } })).disabled(!active)
                    Text(m.t(org["cabinet"].flag ? "org.cabinet_on_hint" : "org.cabinet_hint")).font(.caption)
                    if let other = m.organizations.first(where: { $0["cabinet"].flag && $0["id"].text != m.organization }) { Text(m.t("org.cabinet_elsewhere", ["name": other["name"].text])).font(.caption) }
                } else {
                    Text(m.t("org.subgroup_note", ["name": m.organizations.first { $0["id"].text == org["home"].text }?["name"].text ?? org["parent"]["name"].text])).font(.caption)
                }
                if !org["children"].rows.isEmpty { Text(m.t("org.children")).bold() }
                Rows(org["children"].rows.filter { $0["kind"].text != "subgroup" }) { child in
                    Button { m.run { try await m.select(child["id"].text) } } label: { VStack(alignment: .leading) { Text(child["name"].text); Text(m.t("org.child_stats", ["decisions": child["decisions"].text, "blocked": child["blocked"].text, "working": child["working"].text])).font(.caption) } }
                }
                if !org["subgroups"].rows.isEmpty { Text(m.t("org.subgroups")).bold() }
                Rows(org["subgroups"].rows) { group in
                    Button(group["name"].text + " · " + (group["status"].text == "active" ? m.t("org.leader_chip", ["name": group["leader"].text]) : m.t(group["status"].text == "closed" ? "org.status_closed" : "org.status_dissolved"))) { m.run { try await m.select(group["id"].text) } }
                }
                if org["kind"].text == "subgroup" && active { Button(m.t("org.close_group"), role: .destructive) { close = true } }
                Button(m.t("chart.title")) { m.sheet = .chart }
            }.padding(.vertical, 8)
        }.confirmationDialog(m.t("org.leader_confirm", ["name": m.name(leader), "org": org["name"].text]), isPresented: Binding(get: { !leader.isEmpty }, set: { if !$0 { leader = "" } })) {
            Button(m.t("common.save")) { let who = leader; m.run { do { try await m.post(m.path("/leader"), ["member": who]); m.notice = m.t("org.leader_changed", ["name": m.name(who)]); try await m.refresh() } catch { throw RelicError.message(m.t("org.leader_failed", ["error": error.localizedDescription])) } } }
        }.confirmationDialog(m.t("org.close_group_confirm", ["name": org["name"].text]), isPresented: $close) {
            Button(m.t("org.close_group"), role: .destructive) { m.run { do { try await m.post(m.path("/close"), [:]); m.notice = m.t("org.group_closed", ["name": org["name"].text]); try await m.refresh() } catch { throw RelicError.message(m.t("org.close_group_failed", ["error": error.localizedDescription])) } } }
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
        sending = true; m.run {
            defer { sending = false }; var body: [String: Any] = ["request_id": decision["id"].text, "decision": answer, "note": note]; if redact { body["redact"] = true }
            do { try await m.post(Client.org(org, route), body) } catch { throw RelicError.message(m.t("decision.approval_failed", ["id": decision["id"].text, "error": error.localizedDescription])) }
            m.notice = m.t(answer == "deny" ? "decision.denied" : "decision.approved", ["id": decision["id"].text]); try await m.refresh()
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(m.decisionTitle(decision), systemImage: "exclamationmark.circle.fill").font(.system(size: 12, weight: .semibold)).foregroundStyle(RelicStyle.amber).fixedSize(horizontal: false, vertical: true)
            Text(["reason", "error", "detail"].map { decision[$0].text }.filter { !$0.isEmpty }.joined(separator: "\n")).textSelection(.enabled)
            if decision["kind"].text == "approval" { Text(m.approvalNote(decision)).font(.caption) }
            if decision["kind"].text == "permission" {
                Text(m.t("perm.ask")).font(.caption)
                Rows(decision["options"].rows) { option in Button(option["name"].text) { sending = true; m.run { defer { sending = false }; try await m.post("/api/permission/" + Client.segment(decision["id"].text), ["option": option["id"].text]); try await m.refresh() } } }
            } else if ["approval", "trajectory"].contains(decision["kind"].text) {
                TextField(m.t("decision.reason", ["reason": ""]), text: $note)
                HStack { Button(m.t("decision.approve")) { act("approve") }.buttonStyle(.borderedProminent); Button(m.t("decision.deny")) { act("deny") }.buttonStyle(.bordered) }
                if decision["kind"].text == "trajectory" { Button(m.t("decision.approve_redacted")) { act("approve", redact: true) } }
            }
            if decision["kind"].text == "task" { Text(m.t("decision.task_owner", ["name": m.name(decision["member"].text)])).font(.system(size: 12)).foregroundStyle(RelicStyle.muted); Button(m.t("decision.view_task")) { m.openDetails("tasks", task: decision["id"].text) }.buttonStyle(.bordered) }
            if !decision["member"].text.isEmpty { Button(m.t(decision["kind"].text == "task" ? "decision.ask" : "decision.open_chat", ["name": m.name(decision["member"].text)])) { m.run { try await m.select(m.organization, decision["member"].text) } } }
        }.relicCard(RelicStyle.amberSoft).font(.system(size: 13)).controlSize(.small).disabled(sending)
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
                if !task["at"].text.isEmpty { Text(m.t("details.updated", ["when": m.day(task["at"]) + " " + m.clock(task["at"])])) }
                Text(m.t("details.label_evidence")).bold()
                if task["evidence"].rows.isEmpty { Text(m.t("details.no_evidence")) }
                Rows(task["evidence"].rows) { RichText($0.text) }
                if !task["owner"].text.isEmpty { Button(m.t("details.ask", ["name": m.name(task["owner"].text)])) { m.sheet = nil; m.run { try await m.select(m.organization, task["owner"].text) } } }
            }.padding(8)
        } label: {
            VStack(alignment: .leading) {
                HStack(alignment: .top) { Text(task["id"].text + " " + task["title"].text).font(.system(size: 13, weight: .semibold)).fixedSize(horizontal: false, vertical: true); Spacer(minLength: 4); SmallBadge(text: m.taskLabel(task["status"].text), color: task["status"].text == "blocked" ? RelicStyle.amber : task["status"].text == "done" ? RelicStyle.green : RelicStyle.violet) }
                Text((task["owner"].text.isEmpty ? m.t(m.sheet == .details ? "details.no_owner" : "org.no_owner") : m.name(task["owner"].text)) + " · " + m.taskLabel(task["status"].text)).font(.caption).foregroundStyle(.secondary)
                if !task["report"].text.isEmpty { Text(m.t("details.has_report")).font(.caption).help(m.t("org.report")) }
            }
        }.relicCard()
    }
}

struct ProtocolList: View {
    @EnvironmentObject var m: Model
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if ["protocols", "inherited_protocols", "replaced_protocols"].allSatisfy({ m.snapshot[$0].rows.isEmpty }) { Text(m.t("details.no_protocols")) }
            ForEach(["protocols", "inherited_protocols", "replaced_protocols"], id: \.self) { key in
                if !m.snapshot[key].rows.isEmpty {
                    if key != "protocols" { Text(m.t(key == "inherited_protocols" ? "details.inherited_title" : "details.replaced_title")).bold() }
                    Rows(m.snapshot[key].rows) { p in ProtocolCard(protocolItem: p) }
                }
            }
        }
    }
}

struct ProtocolCard: View {
    @EnvironmentObject var m: Model
    let protocolItem: Node
    @State private var expanded = false
    private var p: Node { protocolItem }
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 6) {
                if !p["from"].text.isEmpty { Text(m.t("org.inherited_from", ["name": p["from"].text])) }
                if !p["issued_by"].isNull { Text(m.t(p["issued_by"]["person"].flag ? "org.issued_by_person" : "org.issued_by", ["name": p["issued_by"]["name"].text])) }
                if !p["how"].text.isEmpty { Text(m.t(p["how"].text == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ["from": p["from"].text, "at": p["at"].text, "by": p["by"].text])) }
                if p["inherit"].flag { Text(m.t("org.protocol_inherits")) }
                if !p["supersedes"].text.isEmpty { Text(m.t("details.label_supersedes") + p["supersedes"].text) }
                if p["supersedes"].text.contains("/") { Text(m.t("org.protocol_overrides", ["ref": m.protocolReference(p["supersedes"].text)])) }
                if !p["retire_target"].text.isEmpty { Text(m.t("details.label_retires") + p["retire_target"].text) }
                if !p["trigger"].text.isEmpty { Text(m.t("details.label_applies") + p["trigger"].text) }
                RichText(p["guidance"].text); RichText(p["summary_for_person"].text)
                RulesView(rules: p["rules"].rows)
                if p["rules"].rows.contains(where: { $0["effect"].text == "check" }) { Text(m.t("org.protocol_check")).font(.caption) }
                if p["status"].text == "active" { Text(m.t("org.protocol_used", ["n": p["uses"].text])) }
                if p["status"].text == "proposed" { Text(m.t("org.protocol_voting", ["n": p["votes"].text])) }
                if p["retired_by_person"].flag { Text(m.t("details.retired_by_person")) }
                Text(m.t("details.proposed_by", ["name": m.name(p["author"].text)]) + " · " + m.t("details.votes", ["n": p["votes"].text]) + " · " + m.t("details.uses", ["n": p["uses"].text])).font(.caption)
            }.padding(6)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(m.t("details.protocol_head", ["id": p["id"].text, "title": p["title"].text, "kind": m.t(p["strength"].text == "strong" ? "details.strong_protocol" : "details.weak_protocol"), "status": m.protocolLabel(p["status"].text.isEmpty ? "active" : p["status"].text)])).font(.system(size: 13, weight: .semibold)).fixedSize(horizontal: false, vertical: true)
                if !expanded {
                    if !p["issued_by"].isNull { SmallBadge(text: m.t(p["issued_by"]["person"].flag ? "org.issued_by_person" : "org.issued_by", ["name": p["issued_by"]["name"].text]), color: RelicStyle.violet) }
                    if !p["from"].text.isEmpty { Text(m.t("org.inherited_from", ["name": p["from"].text])).font(.caption).foregroundStyle(RelicStyle.muted) }
                }
            }
        }.relicCard().onAppear { expanded = m.sheet == .details }
    }
}

struct RulesView: View {
    @EnvironmentObject var m: Model
    let rules: [Node]
    @State private var expanded = false
    var body: some View {
        Rows(rules) { rule in
            DisclosureGroup(m.t(rule["effect"].text == "check" ? "cc.code" : "org.protocols"), isExpanded: $expanded) {
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
        }.onAppear { expanded = m.expandRules }
    }
}
