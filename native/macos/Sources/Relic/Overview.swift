import SwiftUI
import RelicCore

struct Overview: View {
    @EnvironmentObject var m: Model
    @State private var purposeOpen = false
    private var org: Node { m.snapshot["org"] }
    private func roleName(_ id: String, _ key: String) -> String { m.name(id) == m.t(key) ? id : m.name(id) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            OverviewBlock {
                HStack(spacing: 8) {
                    Text(m.t("org.heading")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted); Spacer(minLength: 0)
                    HStack(spacing: 2) {
                        ForEach(Choices.modes, id: \.0) { value, key in
                            Button { m.overviewMode = value } label: {
                                Text(m.t(key)).font(RelicStyle.font(12, weight: 400)).foregroundStyle(m.overviewMode == value ? RelicStyle.ink : RelicStyle.secondary)
                                    .padding(.horizontal, 9).frame(height: 23.2)
                                    .modifier(RecordedSurface(background: m.overviewMode == value ? RelicStyle.card : .clear, radius: 6))
                            }.buttonStyle(.plain).accessibilityAddTraits(m.overviewMode == value ? [.isSelected] : [])
                        }
                    }.padding(2).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "region"))
                        .accessibilityElement(children: .contain).accessibilityLabel(m.t("org.view_mode"))
                }
                Text(org["name"].text).font(RelicStyle.font(16, weight: 700)).frame(minHeight: 21.6)
                Text(org["purpose"].text.isEmpty ? m.t("org.no_purpose") : org["purpose"].text)
                    .font(RelicStyle.font(12.5, weight: 400)).foregroundStyle(RelicStyle.secondary).lineSpacing(5)
                    .lineLimit(purposeOpen ? nil : 3).fixedSize(horizontal: false, vertical: true)
                    .help(m.t("org.click_expand")).onTapGesture { purposeOpen.toggle() }
                FlowLayout {
                    if org["cabinet"].flag { OverviewChip(text: m.t("org.cabinet_chip")) }
                    OverviewChip(text: m.t(org["kind"].text == "subgroup" ? "org.kind_subgroup" : "org.kind_formal"))
                    if !["", "active"].contains(org["status"].text) { OverviewChip(text: m.t(org["status"].text == "closed" ? "org.status_closed" : "org.status_dissolved"), tone: "bad") }
                    OverviewChip(text: m.t(org["governance"].text == "peer" ? "org.gov_peer" : "org.gov_leader"))
                    if !org["leader"].text.isEmpty { OverviewChip(text: m.t(org["cabinet"].flag ? "org.secretary_general_chip" : "org.leader_chip", ["name": roleName(org["leader"].text, "common.leader")])) }
                    OverviewChip(text: m.t("common.members", ["n": String(m.members.count)]))
                    if !m.secretary.isEmpty { OverviewChip(text: m.t("org.secretary_chip", ["name": roleName(m.secretary, "common.secretary")]), tone: "sec") }
                }
                if !["", "active"].contains(org["status"].text) { Text(m.t(org["status"].text == "closed" ? "org.ended_closed" : "org.ended_dissolved")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted) }
                Toggle(m.t("org.auto_wake"), isOn: Binding(get: { org["auto_wake"].flag }, set: { value in m.run { try await m.post(m.path("/auto_wake"), ["on": value]); try await m.refresh() } })).toggleStyle(OverviewToggleStyle())
            }
            OverviewBlock {
                HStack { sectionTitle("decision.title"); Spacer(); if !m.snapshot["decisions"].rows.isEmpty { Text(String(m.snapshot["decisions"].rows.count)).font(RelicStyle.font(11, weight: 700)).foregroundStyle(.white).padding(.horizontal, 5).frame(minWidth: 18, minHeight: 18).modifier(RecordedSurface(background: RelicStyle.accent, radius: 9, kind: "badge")) } }
                if m.snapshot["decisions"].rows.isEmpty { empty("decision.none") }
                Rows(m.snapshot["decisions"].rows) { DecisionView(decision: $0) }
            }
            HierarchyView()
            currentWork
            if m.overviewMode != "liaison" { people; protocols; episodes }
            OverviewBlock {
                if m.overviewMode == "liaison" { empty("org.liaison_note") }
                Button { m.openDetails("trace") } label: { HStack(spacing: 6) { ReferenceIcon(name: "trace", size: 16); Text(m.t("org.details")).fixedSize(horizontal: false, vertical: true) }.frame(maxWidth: .infinity) }.buttonStyle(ReferenceButtonStyle())
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .onChange(of: m.overviewMode) { m.defaults.set(m.overviewMode, forKey: "mode." + m.organization); if m.overviewMode == "liaison" && !m.secretary.isEmpty && m.member != m.secretary { m.run { try await m.select(m.organization, m.secretary) } } }
    }
    private func sectionTitle(_ key: String) -> some View { Text(m.t(key)).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).frame(minHeight: 19.2) }
    private func empty(_ key: String) -> some View { Text(m.t(key)).font(RelicStyle.font(12.5, weight: 400)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true) }
    private var currentWork: some View {
        let tasks = m.snapshot["tasks"].rows, open = tasks.filter { !["done", "dropped"].contains($0["status"].text) }, done = tasks.filter { $0["status"].text == "done" }
        return OverviewBlock {
            HStack { OverviewLink(text: m.t("org.current_work")) { m.openDetails("tasks", filter: "open") }; Spacer(); OverviewLink(text: m.t("org.done_count", ["n": String(done.count)])) { m.openDetails("tasks", filter: "done") } }
            if tasks.isEmpty { empty("org.no_tasks") }
            else if open.isEmpty { Text(m.t("org.nothing_open", ["n": String(done.count)])).font(RelicStyle.font(12.5, weight: 400)).foregroundStyle(RelicStyle.muted) }
            Rows(Array(open.prefix(8))) { overviewTask($0, report: false) }
            if open.count > 8 { OverviewLink(text: m.t("common.more_items", ["n": String(open.count - 8)]), icon: "") { m.openDetails("tasks", filter: "open") } }
            let reports = done.filter { !$0["report"].text.isEmpty }.sorted { $0["done_at"].text > $1["done_at"].text }
            if !reports.isEmpty { sectionTitle("org.recently_done").padding(.top, 4); Rows(Array(reports.prefix(3))) { overviewTask($0, report: true) } }
        }
    }
    private func overviewTask(_ task: Node, report: Bool) -> some View {
        Button { m.openDetails("tasks", task: task["id"].text) } label: {
            OverviewRow(title: task["title"].text, subtitle: report ? m.taskReportPreview(task["report"].text) : task["id"].text + " · " + (task["owner"].text.isEmpty ? m.t("org.no_owner") : m.name(task["owner"].text))) {
                if task["owner"].text.isEmpty { Color.clear.frame(width: 0, height: 0) } else { Avatar(member: task["owner"].text, size: 20) }
            } trailing: { OverviewChip(text: report ? m.t("org.report") : m.taskLabel(task["status"].text), tone: report ? "ok" : task["status"].text == "blocked" ? "bad" : task["status"].text == "working" ? "warn" : "") }
        }.buttonStyle(QuietButtonStyle())
    }
    private var people: some View {
        OverviewBlock {
            HStack { sectionTitle("org.members"); Spacer(); OverviewLink(text: m.t("org.add"), icon: "plus", leading: true) { m.openMemberForm() } }
            Rows(m.members) { member in
                Button { m.openCard(member["name"].text) } label: {
                    OverviewRow(title: member["secretary"].flag ? m.t("org.member_secretary", ["name": roleName(member["name"].text, "common.secretary")]) : member.display, subtitle: m.overviewMemberDetail(member)) {
                        Avatar(member: member["name"].text, size: 28, showState: true)
                    } trailing: { OverviewChip(text: m.stateLabel(member["state"].text), tone: ["running", "working"].contains(member["state"].text) ? "ok" : member["state"].text == "waiting" ? "warn" : member["state"].text == "error" ? "bad" : "") }
                }.buttonStyle(QuietButtonStyle())
            }
        }
    }
    private var protocols: some View {
        let live = m.snapshot["protocols"].rows.filter { ["active", "proposed"].contains($0["status"].text) }
        return OverviewBlock {
            HStack { OverviewLink(text: m.t("org.protocols")) { m.openDetails("protocols") }; Spacer(); Text(m.t("org.protocols_active", ["n": String(m.snapshot["protocols"].rows.filter { $0["status"].text == "active" }.count)])).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted) }
            if live.isEmpty && m.snapshot["inherited_protocols"].rows.isEmpty && m.snapshot["replaced_protocols"].rows.isEmpty { empty("org.no_protocols") }
            ForEach(["protocols", "inherited_protocols", "replaced_protocols"], id: \.self) { kind in
                Rows(kind == "protocols" ? live : m.snapshot[kind].rows) { p in
                    Button { m.openDetails("protocols") } label: {
                        OverviewRow(title: p["id"].text + " " + p["title"].text, subtitle: m.overviewProtocolDetail(p, source: kind), struck: kind == "replaced_protocols") {
                            OverviewChip(text: m.t(p["strength"].text == "strong" ? "common.strong" : "common.weak"), tone: p["strength"].text == "strong" && kind != "replaced_protocols" ? "bad" : "")
                        } trailing: { Color.clear.frame(width: 0, height: 0) }
                    }.buttonStyle(QuietButtonStyle()).recordedOpacity(kind == "replaced_protocols" ? 0.6 : 1)
                }
            }
        }
    }
    private var episodes: some View {
        let all = m.snapshot["episodes"].rows
        let visible = all.filter { $0["status"].text == "open" } + all.filter { $0["status"].text == "closed" }.suffix(3).reversed()
        return OverviewBlock {
            sectionTitle("native.episodes")
            if all.isEmpty { empty("org.no_episodes") }
            Rows(visible) { episode in
                OverviewRow(title: episode["id"].text + " " + episode["title"].text, subtitle: m.t("org.episode_reflections", ["reflections": episode["reflections"].text, "participants": episode["participants"].text])) {
                    OverviewChip(text: m.episodeLabel(episode), tone: episode["status"].text == "open" ? "warn" : episode["outcome"].text == "success" ? "ok" : "")
                } trailing: { Color.clear.frame(width: 0, height: 0) }
            }
        }
    }
}

struct HierarchyView: View {
    @EnvironmentObject var m: Model
    @State private var leader = ""
    @State private var close = false
    private var org: Node { m.snapshot["org"] }
    private var active: Bool { org["status"].text.isEmpty || org["status"].text == "active" }
    private var parent: String { org["parent"]["id"].text.isEmpty ? (org["parent"].raw as? String ?? "") : org["parent"]["id"].text }
    private var parents: [(String, String)] {
        [("", m.t("org.parent_none"))] + m.organizations.filter {
            $0["id"].text != m.organization && !Tree.descendants(m.organization, in: m.organizations).contains($0["id"].text) &&
            ($0["id"].text == parent || $0["status"].text == "active" && (org["kind"].text == "subgroup" || $0["kind"].text != "subgroup"))
        }.map { ($0["id"].text, $0["name"].text) }
    }
    private func note(_ value: String) -> some View { Text(value).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).lineSpacing(4.6).fixedSize(horizontal: false, vertical: true) }
    private func stats(_ child: Node) -> String { m.t("org.child_stats", ["decisions": child["decisions"].text, "blocked": child["blocked"].text, "working": child["working"].text]) }
    var body: some View {
        OverviewBlock {
            HStack { Text(m.t("org.hierarchy")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted); Spacer(); OverviewLink(text: m.t("chart.title")) { m.sheet = .chart } }
            OverviewPicker(title: m.t("org.parent_label"), selection: Binding(get: { parent }, set: { value in m.run {
                do { try await m.post(m.path("/parent"), ["parent": value.isEmpty ? NSNull() : value as Any]); try await m.refresh() }
                catch { throw RelicError.message(m.t("org.parent_failed", ["error": error.localizedDescription])) }
            } }), options: parents).disabled(!active)
            if org["governance"].text != "peer" {
                OverviewPicker(title: m.t("common.leader"), selection: Binding(get: { org["leader"].text }, set: { leader = $0 }),
                    options: (org["leader"].text.isEmpty ? [("", m.t("org.leader_unset"))] : []) + m.members.map { ($0["name"].text, $0.display) }).disabled(!active || m.members.isEmpty)
            }
            if org["kind"].text == "subgroup" {
                note(m.t("org.subgroup_note", ["name": m.organizations.first { $0["id"].text == org["home"].text }?["name"].text ?? (org["parent"]["name"].text.isEmpty ? "-" : org["parent"]["name"].text)]))
            } else {
                Toggle(m.t("org.cabinet_toggle"), isOn: Binding(get: { org["cabinet"].flag }, set: { value in m.run {
                    do { try await m.post(m.path("/cabinet"), ["on": value]); try await m.refresh() }
                    catch { throw RelicError.message(m.t("org.cabinet_failed", ["error": error.localizedDescription])) }
                } })).toggleStyle(OverviewToggleStyle()).disabled(!active)
                let other = m.organizations.first { $0["cabinet"].flag && $0["id"].text != m.organization }
                note(m.t(org["cabinet"].flag ? "org.cabinet_on_hint" : other == nil ? "org.cabinet_hint" : "org.cabinet_elsewhere", ["name": other?["name"].text ?? ""]))
            }
            note(m.t("org.parent_hint"))
            let formal = org["children"].rows.filter { $0["kind"].text != "subgroup" }
            if !formal.isEmpty { note(m.t("org.children")).padding(.top, 6) }
            Rows(formal) { child in childRow(child, subtitle: stats(child)) }
            if !org["subgroups"].rows.isEmpty { note(m.t("org.subgroups")).padding(.top, 6) }
            Rows(org["subgroups"].rows) { group in
                let child = org["children"].rows.first { $0["id"].text == group["id"].text }
                let active = group["status"].text == "active"
                let subtitle = active ? [group["leader"].text.isEmpty ? "" : m.t("org.leader_chip", ["name": group["leader"].text]), child.map { stats($0) } ?? ""].filter { !$0.isEmpty }.joined(separator: " · ") : m.t(group["status"].text == "closed" ? "org.status_closed" : "org.status_dissolved") + (group["ended_at"].text.isEmpty ? "" : " · " + m.shortWhen(group["ended_at"]))
                childRow(group, subtitle: subtitle).recordedOpacity(active ? 1 : 0.6)
            }
            if org["kind"].text == "subgroup" && active { Button(m.t("org.close_group"), role: .destructive) { close = true }.buttonStyle(ReferenceButtonStyle(small: true, danger: true)) }
        }.confirmationDialog(m.t("org.leader_confirm", ["name": m.name(leader), "org": org["name"].text]), isPresented: Binding(get: { !leader.isEmpty }, set: { if !$0 { leader = "" } })) {
            Button(m.t("common.save")) { let who = leader; m.run { do { try await m.post(m.path("/leader"), ["member": who]); m.notice = m.t("org.leader_changed", ["name": m.name(who)]); try await m.refresh() } catch { throw RelicError.message(m.t("org.leader_failed", ["error": error.localizedDescription])) } } }
        }.confirmationDialog(m.t("org.close_group_confirm", ["name": org["name"].text]), isPresented: $close) {
            Button(m.t("org.close_group"), role: .destructive) { m.run { do { try await m.post(m.path("/close"), [:]); m.notice = m.t("org.group_closed", ["name": org["name"].text]); try await m.refresh() } catch { throw RelicError.message(m.t("org.close_group_failed", ["error": error.localizedDescription])) } } }
        }
    }
    private func childRow(_ node: Node, subtitle: String) -> some View {
        Button { m.run { try await m.select(node["id"].text) } } label: {
            OverviewRow(title: node["name"].text, subtitle: subtitle) {
                Text(String(node["name"].text.prefix(1)).uppercased()).font(RelicStyle.font(11, weight: 700)).frame(width: 22, height: 22)
                    .foregroundStyle(RelicStyle.avatar(node["id"].text, background: false, dark: false))
                    .modifier(RecordedSurface(background: RelicStyle.avatar(node["id"].text, background: true, dark: false), radius: 6))
            } trailing: { Color.clear.frame(width: 0, height: 0) }
        }.buttonStyle(QuietButtonStyle())
    }
}

struct DecisionView: View {
    @EnvironmentObject var m: Model
    let decision: Node
    @State private var sending = false
    private func act(_ answer: String) {
        let org = decision["org"].text.isEmpty ? m.organization : decision["org"].text
        let route = decision["kind"].text == "approval" ? "/request" : "/trajectory_answer"
        sending = true
        m.run {
            defer { sending = false }
            do { try await m.post(Client.org(org, route), ["request_id": decision["id"].text, "decision": answer]) }
            catch { throw RelicError.message(m.t("decision.approval_failed", ["id": decision["id"].text, "error": error.localizedDescription])) }
            if decision["kind"].text == "approval" { m.notice = m.t(answer == "deny" ? "decision.denied" : "decision.approved", ["id": decision["id"].text]) }
            try await m.refresh()
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(m.decisionTitle(decision)).font(RelicStyle.font(12.5, weight: 700)).fixedSize(horizontal: false, vertical: true)
            switch decision["kind"].text {
            case "permission":
                if !decision["detail"].text.isEmpty { Text(decision["detail"].text).foregroundStyle(RelicStyle.muted).lineLimit(1).help(decision["detail"].text) }
                FlowLayout {
                    Rows(decision["options"].rows) { option in
                        Button(option["name"].text.isEmpty ? option["kind"].text : option["name"].text) { sending = true; m.run { defer { sending = false }; try await m.post("/api/permission/" + Client.segment(decision["id"].text), ["option": option["id"].text]); try await m.refresh() } }
                            .buttonStyle(ReferenceButtonStyle(primary: option["kind"].text.hasPrefix("allow"), small: true))
                    }
                }
            case "trajectory":
                Text(m.t("decision.reason", ["reason": decision["reason"].text.isEmpty ? "—" : decision["reason"].text])).fixedSize(horizontal: false, vertical: true)
                FlowLayout { Button(m.t("decision.approve_redacted")) { act("approve") }.buttonStyle(ReferenceButtonStyle(primary: true, small: true)); Button(m.t("decision.deny")) { act("deny") }.buttonStyle(ReferenceButtonStyle(small: true)) }
            case "approval":
                if !decision["reason"].text.isEmpty { Text(m.t("decision.reason", ["reason": decision["reason"].text])).fixedSize(horizontal: false, vertical: true) }
                Text([m.shortWhen(decision["at"]), m.approvalNote(decision)].filter { !$0.isEmpty }.joined(separator: " · ")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted)
                FlowLayout { Button(m.t("decision.approve")) { act("approve") }.buttonStyle(ReferenceButtonStyle(primary: true, small: true)); Button(m.t("decision.deny")) { act("deny") }.buttonStyle(ReferenceButtonStyle(small: true)) }
            case "wake":
                Text(m.clippedDecisionError(decision["error"].text)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true)
                Button(m.t("decision.open_chat")) { m.run { try await m.select(m.organization, decision["member"].text) } }.buttonStyle(ReferenceButtonStyle(small: true))
            case "task":
                Text(m.t("decision.task_owner", ["name": decision["member"].text.isEmpty ? "—" : m.name(decision["member"].text)])).foregroundStyle(RelicStyle.muted)
                FlowLayout {
                    Button(m.t("decision.view_task")) { m.openDetails("tasks", task: decision["id"].text) }.buttonStyle(ReferenceButtonStyle(small: true))
                    if !decision["member"].text.isEmpty { Button(m.t("decision.ask", ["name": m.name(decision["member"].text)])) { m.run { try await m.select(m.organization, decision["member"].text) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
                }
            default: Text(pretty(decision)).textSelection(.enabled)
            }
        }.font(RelicStyle.font(12.5, weight: 400)).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.vertical, 8)
            .modifier(RecordedSurface(background: RelicStyle.amberSoft, border: RelicStyle.amber.opacity(0.4), borderWidth: 1, radius: 10, kind: "card"))
            .disabled(sending)
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
                if !task["report"].text.isEmpty { VStack(alignment: .leading, spacing: 8) { HStack { Label(m.t("report.title"), systemImage: "checkmark").font(RelicStyle.font(12, weight: 600)); Text(m.day(task["done_at"]) + " " + m.clock(task["done_at"])).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted) }; RichText(task["report"].text) }.padding(10).frame(maxWidth: .infinity, alignment: .leading).background(RelicStyle.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 8)).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.green.opacity(0.3))) }
                if !task["at"].text.isEmpty { Text(m.t("details.updated", ["when": m.day(task["at"]) + " " + m.clock(task["at"])])) }
                Text(m.t("details.label_evidence")).bold()
                if task["evidence"].rows.isEmpty { Text(m.t("details.no_evidence")) }
                Rows(task["evidence"].rows) { RichText($0.text) }
                if !task["owner"].text.isEmpty { Button(m.t("details.ask", ["name": m.name(task["owner"].text)])) { m.sheet = nil; m.run { try await m.select(m.organization, task["owner"].text) } } }
            }.padding(8).frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            VStack(alignment: .leading) {
                HStack(alignment: .top) { Text(task["id"].text + " " + task["title"].text).font(RelicStyle.font(13, weight: 600)).fixedSize(horizontal: false, vertical: true); Spacer(minLength: 4); SmallBadge(text: m.taskLabel(task["status"].text), color: task["status"].text == "blocked" ? RelicStyle.amber : task["status"].text == "done" ? RelicStyle.green : RelicStyle.violet) }
                Text((task["owner"].text.isEmpty ? m.t(m.sheet == .details ? "details.no_owner" : "org.no_owner") : m.name(task["owner"].text)) + " · " + m.taskLabel(task["status"].text)).font(RelicStyle.font(12, weight: 400)).foregroundStyle(.secondary)
                if !task["report"].text.isEmpty { Text(m.t("details.has_report")).font(RelicStyle.font(12, weight: 400)).help(m.t("org.report")) }
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
                    Rows(key == "protocols" && m.sheet == .details ? Array(m.snapshot[key].rows.reversed()) : m.snapshot[key].rows) { p in ProtocolCard(protocolItem: p) }
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
                RichText(p["guidance"].text)
                if !p["summary_for_person"].text.isEmpty { VStack(alignment: .leading, spacing: 5) { Text(m.t("details.label_summary")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted); RichText(p["summary_for_person"].text) }.padding(10).frame(maxWidth: .infinity, alignment: .leading).background(RelicStyle.bubble, in: RoundedRectangle(cornerRadius: 8)) }
                if !p["rules"].rows.isEmpty {
                    let metadata = p["rules"].rows.map { rule in rule["effect"].text == "check" ? rule.object.filter { !["code", "examples", "code_sha256"].contains($0.key) } : rule.object }
                    Text(pretty(Node(metadata))).font(.system(size: 11, design: .monospaced)).textSelection(.enabled).padding(8).frame(maxWidth: .infinity, alignment: .leading).background(RelicStyle.code, in: RoundedRectangle(cornerRadius: 8))
                }
                RulesView(rules: p["rules"].rows)
                if p["rules"].rows.contains(where: { $0["effect"].text == "check" }) { Text(m.t("org.protocol_check")).font(RelicStyle.font(12, weight: 400)) }
                if p["status"].text == "active" { Text(m.t("org.protocol_used", ["n": p["uses"].text])) }
                if p["status"].text == "proposed" { Text(m.t("org.protocol_voting", ["n": p["votes"].text])) }
                if p["retired_by_person"].flag { Text(m.t("details.retired_by_person")) }
                Text(m.t("details.proposed_by", ["name": m.name(p["author"].text)]) + " · " + m.t("details.votes", ["n": p["votes"].text]) + " · " + m.t("details.uses", ["n": p["uses"].text])).font(RelicStyle.font(12, weight: 400))
            }.padding(6).frame(maxWidth: .infinity, alignment: .leading)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(m.t("details.protocol_head", ["id": p["id"].text, "title": p["title"].text, "kind": m.t(p["strength"].text == "strong" ? "details.strong_protocol" : "details.weak_protocol"), "status": m.protocolLabel(p["status"].text.isEmpty ? "active" : p["status"].text)])).font(RelicStyle.font(13, weight: 600)).fixedSize(horizontal: false, vertical: true)
                if !expanded {
                    if !p["issued_by"].isNull { SmallBadge(text: m.t(p["issued_by"]["person"].flag ? "org.issued_by_person" : "org.issued_by", ["name": p["issued_by"]["name"].text]), color: RelicStyle.violet) }
                    if !p["from"].text.isEmpty { Text(m.t("org.inherited_from", ["name": p["from"].text])).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted) }
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
        Rows(rules.filter { $0["effect"].text == "check" }) { rule in
            DisclosureGroup(m.t(rule["effect"].text == "check" ? "cc.code" : "org.protocols"), isExpanded: $expanded) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(m.t("cc.scope", ["what": m.ruleScope(rule)]))
                    if rule["effect"].text == "check" {
                        Text(m.t(rule["on_error"].text == "allow" ? "cc.on_error_allow" : "cc.on_error_deny"))
                        Text(rule["code"].text).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        if !rule["code_sha256"].text.isEmpty { Text("sha256 " + String(rule["code_sha256"].text.prefix(16)) + "…").font(.system(size: 11, design: .monospaced)).foregroundStyle(RelicStyle.muted).help(rule["code_sha256"].text) }
                        if !rule["examples"].rows.isEmpty { Text(m.t("cc.examples")).bold() }
                        Rows(rule["examples"].rows) { example in
                            Text(m.t(example["expect"].text == "allow" ? "cc.decision_allow" : example["expect"].text == "deny" ? "cc.decision_deny" : "cc.decision_review")).bold()
                            Text(pretty(example)).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.onAppear { expanded = m.expandRules }
    }
}
