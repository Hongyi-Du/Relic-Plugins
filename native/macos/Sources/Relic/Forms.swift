import SwiftUI
import RelicCore

struct SaveButton: View {
    @EnvironmentObject var m: Model
    @State private var saving = false
    @State private var error = ""
    var labelKey = "common.save"
    let action: () async throws -> Void
    var body: some View {
        VStack(alignment: .leading) {
            if !error.isEmpty { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            HStack { Spacer(); Button(m.t(labelKey)) {
                saving = true
                let sheet = m.sheet
                Task { defer { saving = false }; do { try await action(); if m.sheet == sheet { m.sheet = nil } } catch { self.error = error.localizedDescription } }
            }.disabled(saving).keyboardShortcut(.defaultAction) }
        }
    }
}

struct CreateOrgView: View {
    @EnvironmentObject var m: Model
    @State private var name = ""
    @State private var purpose = ""
    @State private var governance = "leader"
    var body: some View {
        Form {
            Text(m.t("common.new_org")).font(.title2)
            TextField(m.t("common.name"), text: $name, prompt: Text(m.t("neworg.name_placeholder")))
            TextField(m.t("neworg.purpose"), text: $purpose, prompt: Text(m.t("neworg.purpose_placeholder")), axis: .vertical)
            VoiceButton(text: $purpose)
            Picker(m.t("neworg.governance"), selection: $governance) { Text(m.t("neworg.gov_leader")).tag("leader"); Text(m.t("neworg.gov_peer")).tag("peer") }
            SaveButton(labelKey: "neworg.create") {
                guard !name.trimmingCharacters(in: .whitespaces).isEmpty else { throw RelicError.message(m.t("neworg.need_name")) }
                let result = try await m.post("/api/orgs", ["name": name, "purpose": purpose, "governance": governance])
                try await m.select(result["org_id"].text)
                m.sheet = .secretary
            }
        }.formStyle(.grouped)
    }
}

struct MemberForm: View {
    @EnvironmentObject var m: Model
    @State private var mode = "app"
    @State private var name = ""
    @State private var role = ""
    @State private var harness = ""
    @State private var hostHarness = "claude-code"
    @State private var model = ""
    @State private var folder = ""
    @State private var effort = ""
    @State private var environment = "local"
    @State private var permission = ""
    @State private var env = ""
    @State private var sessionIndex = ""
    @State private var secretary = false
    @State private var start = true
    @State private var harnesses: [Node] = []
    @State private var sessions: [Node] = []
    @State private var options = Node()
    @State private var problems: [Node] = []
    @State private var surface = "cli"
    @State private var search = ""
    @State private var original = Node()
    @State private var loading = true
    private var submitLabel: String {
        if !m.editMember.isEmpty { return "common.save" }
        if mode == "existing" { return "member.bind" }
        if mode == "app" { return secretary ? "member.create_secretary" : "member.create_member" }
        return start ? "member.create_start" : "member.create_seat_only"
    }
    var body: some View {
        ScrollView {
            Form {
                Text(m.editMember.isEmpty ? m.t("common.add_member") : m.t("member.edit_title", ["name": m.name(m.editMember)])).font(.title2)
                Picker(m.t("member.where_run"), selection: $mode) {
                    Text(m.t("member.run_app")).tag("app"); Text(m.t(Capabilities.hostKinds(m.platform).contains(where: { $0.hasSuffix("/gui") }) ? "member.run_host" : "member.run_host_mac")).tag("host"); Text(m.t("member.run_existing")).tag("existing")
                }.pickerStyle(.segmented).disabled(!m.editMember.isEmpty || m.newSecretary)
                Text(m.t(!m.editMember.isEmpty ? "member.edit_note" : mode == "host" ? "member.note_host_mac" : mode == "existing" ? "member.note_existing_mac" : "member.note_app")).font(.caption)
                TextField(m.t(mode == "existing" ? "member.which_seat" : "member.name_label"), text: $name, prompt: Text(m.t(mode == "existing" ? "member.seat_placeholder" : "member.name_placeholder")))
                    .disabled(!m.editMember.isEmpty)
                TextField(m.t(mode == "existing" ? "member.role_new" : "common.role"), text: $role, prompt: Text(m.t(secretary ? "member.role_placeholder_secretary" : "member.role_placeholder")))
                if mode == "existing" {
                    TextField(m.t("member.session_search"), text: $search)
                    if loading { Text(m.t("member.finding_sessions")) }
                    if !loading && sessions.isEmpty { Text(m.t("member.no_sessions")) }
                    if !search.isEmpty && !sessions.contains(where: { [$0["title"].text, $0["cwd"].text, $0["id"].text].joined().localizedCaseInsensitiveContains(search) }) { Text(m.t("member.no_match")) }
                    Picker(m.t("common.session"), selection: $sessionIndex) {
                        ForEach(Array(sessions.enumerated()), id: \.offset) { index, session in
                            if search.isEmpty || [session["title"].text, session["cwd"].text, session["id"].text].joined().localizedCaseInsensitiveContains(search) {
                                Text(session["title"].text + " · " + session["cwd"].text + (Capabilities.automatic(m.platform, harness: session["harness"].text, surface: session["surface"].text) ? "" : " · " + m.t("member.manual_delivery"))).tag(String(index))
                            }
                        }
                    }
                    Text(problems.map(\.text).joined(separator: m.t("member.problem_sep"))).foregroundStyle(.secondary)
                } else {
                    if mode == "app" {
                        Picker(m.t("common.harness"), selection: $harness) { Rows(harnesses.filter { !$0["later"].flag }) { Text($0["title"].text + ($0["available"].flag ? "" : " · " + $0["problem"].text)).tag($0["id"].text).disabled(!$0["available"].flag) } }
                        Rows(harnesses.filter { !$0["available"].flag && !$0["later"].flag }) { Text($0["title"].text + " · " + $0["problem"].text).font(.caption).foregroundStyle(.secondary) }
                        if let connected = harnesses.first(where: { $0["id"].text == harness }) { Text(m.t("member.connected", ["program": connected["program"].text])).font(.caption) }
                        DisclosureGroup(m.t("member.later_acp")) { Rows(harnesses.filter { $0["later"].flag }) { Text($0["title"].text + " · " + $0["vendor"].text) } }
                        Toggle(m.t("member.make_secretary"), isOn: $secretary)
                    } else {
                        Picker(m.t("member.where_run"), selection: $hostHarness) { Text("Claude Code").tag("claude-code"); Text("Codex").tag("codex") }
                            .onChange(of: hostHarness) { permission = options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.first?.text ?? "" }
                        Picker(m.t("member.where_run"), selection: $surface) {
                            Text(m.t("member.harness_cli", ["harness": hostHarness == "codex" ? "Codex" : "Claude Code"])).tag("cli")
                            if Capabilities.automatic(m.platform, harness: hostHarness, surface: "gui") { Text(m.t("member.harness_gui", ["harness": hostHarness == "codex" ? "Codex" : "Claude Code"])).tag("gui") }
                        }
                        Picker(m.t("member.effort"), selection: $effort) { Rows(options["efforts"].rows) { Text($0.text.isEmpty ? m.t("common.default_effort") : $0.text).tag($0.text) } }
                        Picker(m.t("member.environment"), selection: $environment) { Text(m.t("member.env_local")).tag("local"); Text(m.t("member.env_worktree")).tag("worktree") }
                        Picker(m.t("member.permission"), selection: $permission) { Rows(options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows) { Text($0.text).tag($0.text) } }
                        TextField(m.t("member.env_vars"), text: $env, prompt: Text(m.t("member.env_placeholder")), axis: .vertical)
                        if m.editMember.isEmpty { Toggle(m.t("member.start_now"), isOn: $start) }
                    }
                    TextField(m.t("common.model"), text: $model, prompt: Text(m.t("member.model_placeholder")))
                    TextField(m.t(mode == "host" ? "member.work_folder" : "common.work_folder"), text: $folder, prompt: Text(m.t(mode == "host" ? "member.host_folder_placeholder" : "member.folder_placeholder")))
                }
                SaveButton(labelKey: submitLabel) {
                    let seat = name.trimmingCharacters(in: .whitespacesAndNewlines), org = m.organization
                    guard !seat.isEmpty else { throw RelicError.message(m.t(mode == "existing" ? "member.need_seat_name" : "member.need_name")) }
                    if mode == "existing" {
                        guard let index = Int(sessionIndex), sessions.indices.contains(index) else { throw RelicError.message(m.t("member.pick_session")) }
                        try await m.post(Client.org(org, "/bind"), ["member": seat, "role": role, "session": sessions[index].raw])
                        m.notice = m.t("member.bound", ["name": seat])
                    } else if mode == "app" {
                        guard !harness.isEmpty else { throw RelicError.message(m.t("member.need_harness")) }
                        try await m.post(Client.org(org, "/members"), ["name": seat, "role": role, "harness": harness, "model": model, "folder": folder, "secretary": secretary])
                        m.notice = m.t("member.starting", ["name": seat])
                    } else {
                        guard Capabilities.automatic(m.platform, harness: hostHarness, surface: surface) else { throw RelicError.message(m.t("member.choose_supported_host")) }
                        var payload = original.object
                        let changed: [String: Any] = ["name": seat, "role": role, "harness": hostHarness, "surface": surface, "model": model, "folder": folder, "effort": effort, "permission": permission, "environment": environment, "env": env, "start": m.editMember.isEmpty && start, "edit": !m.editMember.isEmpty]
                        payload.merge(changed) { _, new in new }
                        try await m.post(Client.org(org, "/seat"), payload)
                        m.notice = m.t(!m.editMember.isEmpty ? "member.edit_saved" : start ? "member.starting_first" : "member.seat_created", ["name": seat])
                    }
                    try await m.select(org, seat)
                }
            }.formStyle(.grouped)
        }.frame(maxHeight: 650)
        .task {
            m.run {
                defer { loading = false }
                mode = m.editMember.isEmpty ? m.memberMode : "host"; secretary = m.newSecretary
                if secretary { name = "secretary" }
                harnesses = try await m.get("/api/harnesses").rows; harness = harnesses.first { $0["available"].flag && !$0["later"].flag }?["id"].text ?? ""
                let found = try await m.get("/api/sessions"); sessions = found["sessions"].rows.filter { $0["harness"].text != "chatgpt" || m.platform["chatgpt_delivery"].flag }; problems = found["problems"].rows
                sessionIndex = sessions.isEmpty ? "" : "0"
                options = try await m.get("/api/seat-options"); permission = options["claude_modes"].rows.first?.text ?? ""
                if !m.editMember.isEmpty {
                    let card = try await m.get(m.path("/member/" + Client.segment(m.editMember))); original = card["config"]
                    name = m.editMember; role = card["role"].text; hostHarness = original["harness"].text; surface = original["surface"].text
                    model = original["model"].text; effort = original["effort"].text; folder = original["folder"].text
                    environment = original["environment"].text; permission = original["permission"].text
                    env = original["env"].object.sorted { $0.key < $1.key }.map { $0.key + "=" + Node($0.value).text }.joined(separator: "\n")
                }
            }
        }
    }
}

struct ProtocolForm: View {
    @EnvironmentObject var m: Model
    @State private var title = ""
    @State private var guidance = ""
    @State private var rationale = ""
    @State private var trigger = ""
    @State private var inherit = false
    @State private var strength = "weak"
    @State private var rules = "[]"
    @State private var summary = ""
    @State private var supersedes = ""
    var body: some View {
        Form {
            Text(m.t("org.protocols")).font(.title2)
            TextField(m.t("native.protocol_title"), text: $title)
            TextField(m.t("native.protocol_rationale"), text: $rationale, axis: .vertical)
            TextField(m.t("native.protocol_trigger"), text: $trigger)
            TextField(m.t("native.protocol_guidance"), text: $guidance, axis: .vertical)
            Picker(m.t("org.protocols"), selection: $strength) { Text(m.t("common.weak")).tag("weak"); Text(m.t("common.strong")).tag("strong") }
            if strength == "strong" { TextField(m.t("cc.code"), text: $rules, axis: .vertical).font(.system(.body, design: .monospaced)) }
            TextField(m.t("details.label_summary"), text: $summary, axis: .vertical)
            TextField(m.t("details.label_supersedes"), text: $supersedes)
            Toggle(m.t("org.protocol_inherits"), isOn: $inherit)
            SaveButton {
                let parsed = try JSONSerialization.jsonObject(with: Data(rules.utf8))
                try await m.post(m.path("/protocols"), ["title": title, "rationale": rationale, "trigger": trigger, "guidance": guidance, "strength": strength, "inherit": inherit, "downward": inherit, "summary_for_person": summary, "supersedes": supersedes, "rules": parsed]); try await m.refresh()
            }
        }.formStyle(.grouped)
    }
}

struct CopiesView: View {
    @EnvironmentObject var m: Model
    @State private var retire: Node?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(m.t("cc.title")).font(.title2); Text(m.t("cc.intro"))
                if m.copies.isEmpty { Text(m.t("cc.empty")) }
                Rows(m.copies) { copy in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(copy["org_name"].text + " · " + copy["title"].text).font(.headline)
                        if !copy["read"].flag { Text(m.t("cc.unread")).font(.caption).foregroundStyle(.tint) }
                        if !copy["supersedes"].text.isEmpty { Text(m.t("cc.revision")).font(.caption) }
                        Text(copy["summary"].text).textSelection(.enabled)
                        Text(m.t("cc.proposed_by", ["name": copy["author_display"].text]))
                        Text(m.t("cc.approved_by", ["names": copy["approved_display"].rows.map(\.text).joined(separator: ", ")]))
                        Text(m.copyLabel(copy))
                        Text(m.t("cc.effective", ["when": copy["activated_at"].text])).font(.caption)
                        if !copy["supersedes"].text.isEmpty { Text(m.t("cc.replaces", ["id": copy["supersedes"].text])) }
                        if !copy["issued_by"].isNull { Text(m.t("cc.issued_by", ["name": copy["issued_by"]["name"].text])) }
                        Text(copy["stats"]["total"].text.isEmpty || copy["stats"]["total"].text == "0" ? m.t("cc.stats_none") : m.t("cc.stats", ["n": copy["stats"]["total"].text, "allow": copy["stats"]["allow"].text, "deny": copy["stats"]["deny"].text, "review": copy["stats"]["review"].text, "error": copy["stats"]["error"].text]))
                        RulesView(rules: copy["rules"].rows)
                        HStack {
                            if !copy["read"].flag { Button(m.t("cc.ack")) { m.run { try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/read", [:]); try await m.refresh() } } }
                            if copy["status"].text == "active" && ["", "active"].contains(copy["org_status"].text) { Button(m.t("cc.retire"), role: .destructive) { retire = copy } }
                        }
                    }.padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.frame(maxHeight: 600)
        .confirmationDialog(m.t("cc.retire"), isPresented: Binding(get: { retire != nil }, set: { if !$0 { retire = nil } }), presenting: retire) { copy in
            Button(m.t("cc.retire"), role: .destructive) { m.run { do { try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/retire", [:]); m.notice = m.t("cc.retired", ["id": copy["protocol_id"].text, "title": copy["title"].text]); try await m.refresh() } catch { throw RelicError.message(m.t("cc.retire_failed", ["error": error.localizedDescription])) } } }
        } message: { copy in Text(m.t("cc.retire_confirm", ["id": copy["protocol_id"].text, "title": copy["title"].text, "org": copy["org_name"].text])) }
    }
}
