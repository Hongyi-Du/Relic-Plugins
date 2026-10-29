import SwiftUI
import RelicCore

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
        Form {
                heading
                if mode == "existing" { existingFields }
                else {
                    TextField(m.t("member.name_label"), text: $name, prompt: Text(m.t("member.name_placeholder"))).dictation($name).disabled(!m.editMember.isEmpty)
                    TextField(m.t("common.role"), text: $role, prompt: Text(m.t(secretary ? "member.role_placeholder_secretary" : "member.role_placeholder"))).dictation($role)
                    if mode == "app" { appFields } else { hostFields }
                }
                SaveButton(labelKey: submitLabel, action: save).disabled(loading)
        }.formStyle(.grouped).frame(minHeight: 420, maxHeight: 550)
        .task {
            m.run {
                defer { loading = false }
                mode = m.editMember.isEmpty ? m.memberMode : "host"; secretary = m.newSecretary
                if secretary { name = "secretary" }
                harnesses = try await m.get("/api/harnesses").rows; harness = harnesses.first { $0["available"].flag && !$0["later"].flag }?["id"].text ?? ""
                let found = try await m.get("/api/sessions"); sessions = found["sessions"].rows.filter { $0["harness"].text != "chatgpt" || m.platform["chatgpt_delivery"].flag }; problems = found["problems"].rows
                sessionIndex = ""
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

    @ViewBuilder private var heading: some View {
        Text(m.editMember.isEmpty ? m.t("common.add_member") : m.t("member.edit_title", ["name": m.name(m.editMember)])).font(.title2)
        Picker(m.t("member.where_run"), selection: $mode) {
            Text(m.t("member.run_app")).tag("app"); Text(m.t(Capabilities.hostKinds(m.platform).contains(where: { $0.hasSuffix("/gui") }) ? "member.run_host" : "member.run_host_mac")).tag("host"); Text(m.t("member.run_existing")).tag("existing")
        }.pickerStyle(.segmented).disabled(!m.editMember.isEmpty || m.newSecretary)
        Text(m.t(!m.editMember.isEmpty ? "member.edit_note" : mode == "host" ? "member.note_host_mac" : mode == "existing" ? "member.note_existing_mac" : "member.note_app")).font(.caption)
    }

    @ViewBuilder private var existingFields: some View {
        TextField(m.t("member.session_search"), text: $search).dictation($search)
        if loading { Text(m.t("member.finding_sessions")) }
        if !loading && sessions.isEmpty { Text(m.t("member.no_sessions")) }
        if !search.isEmpty && !sessions.contains(where: { [$0["title"].text, $0["cwd"].text, $0["id"].text].joined().localizedCaseInsensitiveContains(search) }) { Text(m.t("member.no_match")) }
        Picker(m.t("common.session"), selection: $sessionIndex) {
            Text(m.t("member.pick_session")).tag("")
            ForEach(Array(sessions.enumerated()), id: \.offset) { index, session in
                if search.isEmpty || [session["title"].text, session["cwd"].text, session["id"].text].joined().localizedCaseInsensitiveContains(search) {
                    Text(sessionLabel(session)).tag(String(index))
                }
            }
        }
        Text(problems.map(\.text).joined(separator: m.t("member.problem_sep"))).foregroundStyle(.secondary)
        HStack {
            TextField(m.t("member.which_seat"), text: $name, prompt: Text(m.t("member.seat_placeholder"))).dictation($name)
            Menu(m.t("member.which_seat")) { Rows(m.members) { who in Button(who.display + " · " + who["name"].text) { name = who["name"].text } } }
        }
        TextField(m.t("member.role_new"), text: $role, prompt: Text(m.t("member.role_placeholder"))).dictation($role)
    }

    @ViewBuilder private var appFields: some View {
        Picker(m.t("common.harness"), selection: $harness) { Rows(harnesses.filter { !$0["later"].flag }) { Text($0["title"].text + ($0["available"].flag ? "" : " · " + $0["problem"].text)).tag($0["id"].text).disabled(!$0["available"].flag) } }
        Rows(harnesses.filter { !$0["available"].flag && !$0["later"].flag }) { Text($0["title"].text + " · " + $0["problem"].text).font(.caption).foregroundStyle(.secondary) }
        if let connected = harnesses.first(where: { $0["id"].text == harness }) { Text(m.t("member.connected", ["program": connected["program"].text])).font(.caption) }
        DisclosureGroup(m.t("member.later_acp")) { Rows(harnesses.filter { $0["later"].flag }) { Text($0["title"].text + " · " + $0["vendor"].text) } }
        TextField(m.t("common.model"), text: $model, prompt: Text(m.t("member.model_placeholder"))).dictation($model)
        TextField(m.t("common.work_folder"), text: $folder, prompt: Text(m.t("member.folder_placeholder"))).dictation($folder)
        Toggle(m.t("member.make_secretary"), isOn: $secretary)
    }

    @ViewBuilder private var hostFields: some View {
        Picker(m.t("member.where_run"), selection: $hostHarness) { Text("Claude Code").tag("claude-code"); Text("Codex").tag("codex") }
            .onChange(of: hostHarness) { permission = options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.first?.text ?? "" }
        Picker(m.t("member.where_run"), selection: $surface) {
            Text(m.t("member.harness_cli", ["harness": hostHarness == "codex" ? "Codex" : "Claude Code"])).tag("cli")
            if Capabilities.automatic(m.platform, harness: hostHarness, surface: "gui") { Text(m.t("member.harness_gui", ["harness": hostHarness == "codex" ? "Codex" : "Claude Code"])).tag("gui") }
        }
        HStack {
            TextField(m.t("common.model"), text: $model, prompt: Text(m.t("member.model_placeholder"))).dictation($model)
            if hostHarness == "claude-code" { Menu(m.t("common.model")) { Rows(options["claude_models"].rows) { option in Button(option.text.isEmpty ? m.t("common.default_model") : option.text) { model = option.text } } } }
        }
        Picker(m.t("member.effort"), selection: $effort) { Rows(options["efforts"].rows) { Text($0.text.isEmpty ? m.t("common.default_effort") : $0.text).tag($0.text) } }
        TextField(m.t("member.work_folder"), text: $folder, prompt: Text(m.t("member.host_folder_placeholder"))).dictation($folder)
        Picker(m.t("member.environment"), selection: $environment) { Text(m.t("member.env_local")).tag("local"); Text(m.t("member.env_worktree")).tag("worktree") }
        Picker(m.t("member.permission"), selection: $permission) { Rows(options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows) { Text($0.text).tag($0.text) } }
        TextField(m.t("member.env_vars"), text: $env, prompt: Text(m.t("member.env_placeholder")), axis: .vertical)
        if m.editMember.isEmpty { Toggle(m.t("member.start_now"), isOn: $start) }
    }

    private func save() async throws {
        let seat = name.trimmingCharacters(in: .whitespacesAndNewlines), org = m.organization
        guard !seat.isEmpty else { throw RelicError.message(m.t(mode == "existing" ? "member.need_seat_name" : "member.need_name")) }
        if mode == "existing" {
            guard let index = Int(sessionIndex), sessions.indices.contains(index) else { throw RelicError.message(m.t("member.pick_session")) }
            try await m.post(Client.org(org, "/bind"), ["member": seat, "role": role.trimmingCharacters(in: .whitespacesAndNewlines), "session": sessions[index].raw])
            m.notice = m.t("member.bound", ["name": seat])
        } else if mode == "app" {
            guard !harness.isEmpty else { throw RelicError.message(m.t("member.need_harness")) }
            try await m.post(Client.org(org, "/members"), ["name": seat, "role": role.trimmingCharacters(in: .whitespacesAndNewlines), "harness": harness, "model": model.trimmingCharacters(in: .whitespacesAndNewlines), "folder": folder.trimmingCharacters(in: .whitespacesAndNewlines), "secretary": secretary])
            m.notice = m.t("member.starting", ["name": seat])
        } else {
            guard Capabilities.automatic(m.platform, harness: hostHarness, surface: surface) else { throw RelicError.message(m.t("member.choose_supported_host")) }
            var payload = original.object
            let changed: [String: Any] = ["name": seat, "role": role.trimmingCharacters(in: .whitespacesAndNewlines), "harness": hostHarness, "surface": surface, "model": model.trimmingCharacters(in: .whitespacesAndNewlines), "folder": folder.trimmingCharacters(in: .whitespacesAndNewlines), "effort": effort, "permission": permission, "environment": environment, "env": env, "start": m.editMember.isEmpty && start, "edit": !m.editMember.isEmpty]
            payload.merge(changed) { _, new in new }
            try await m.post(Client.org(org, "/seat"), payload)
            m.notice = m.t(!m.editMember.isEmpty ? "member.edit_saved" : start ? "member.starting_first" : "member.seat_created", ["name": seat])
        }
        try await m.select(org, seat)
    }
    private func sessionLabel(_ session: Node) -> String {
        var parts = [session["title"].text.isEmpty ? session["id"].text : session["title"].text, session["harness"].text, session["cwd"].text, m.ago(session["updated"])]
        if !Capabilities.automatic(m.platform, harness: session["harness"].text, surface: session["surface"].text) { parts.append(m.t("member.manual_delivery")) }
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }

}
