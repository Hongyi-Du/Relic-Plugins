import SwiftUI
import RelicCore

struct SaveButton: View {
    @EnvironmentObject var m: Model
    @State private var saving = false
    @State private var error = ""
    let action: () async throws -> Void
    var body: some View {
        VStack(alignment: .leading) {
            if !error.isEmpty { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            HStack { Spacer(); Button(m.t("common.save")) {
                saving = true
                Task { defer { saving = false }; do { try await action(); m.sheet = nil } catch { self.error = error.localizedDescription } }
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
            TextField(m.t("common.name"), text: $name)
            TextField(m.t("neworg.purpose"), text: $purpose, axis: .vertical)
            Picker(m.t("neworg.governance"), selection: $governance) { Text(m.t("neworg.gov_leader")).tag("leader"); Text(m.t("neworg.gov_peer")).tag("peer") }
            SaveButton {
                guard !name.trimmingCharacters(in: .whitespaces).isEmpty else { throw RelicError.message(m.t("neworg.need_name")) }
                let result = try await m.post("/api/orgs", ["name": name, "purpose": purpose, "governance": governance])
                try await m.select(result["org_id"].text)
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
    var body: some View {
        ScrollView {
            Form {
                Text(m.t("common.add_member")).font(.title2)
                Picker(m.t("member.where_run"), selection: $mode) {
                    Text(m.t("member.run_app")).tag("app"); Text(m.t("member.run_host_mac")).tag("host"); Text(m.t("member.run_existing")).tag("existing")
                }.pickerStyle(.segmented)
                TextField(m.t("member.name_label"), text: $name)
                TextField(m.t("common.role"), text: $role)
                if mode == "existing" {
                    Picker(m.t("common.session"), selection: $sessionIndex) {
                        ForEach(Array(sessions.enumerated()), id: \.offset) { index, session in Text(session["title"].text + " · " + session["cwd"].text).tag(String(index)) }
                    }
                    Rows(problems) { Text($0.text).foregroundStyle(.secondary) }
                } else {
                    if mode == "app" {
                        Picker(m.t("common.harness"), selection: $harness) { Rows(harnesses) { Text($0["title"].text).tag($0["id"].text) } }
                        Toggle(m.t("member.make_secretary"), isOn: $secretary)
                    } else {
                        Picker(m.t("member.where_run"), selection: $hostHarness) { Text("Claude Code").tag("claude-code"); Text("Codex").tag("codex") }
                            .onChange(of: hostHarness) { permission = options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.first?.text ?? "" }
                        Picker(m.t("member.effort"), selection: $effort) { Rows(options["efforts"].rows) { Text($0.text.isEmpty ? m.t("common.default_effort") : $0.text).tag($0.text) } }
                        Picker(m.t("member.environment"), selection: $environment) { Text(m.t("member.env_local")).tag("local"); Text(m.t("member.env_worktree")).tag("worktree") }
                        Picker(m.t("member.permission"), selection: $permission) { Rows(options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows) { Text($0.text).tag($0.text) } }
                        TextField(m.t("member.env_vars"), text: $env, axis: .vertical)
                        Toggle(m.t("member.start_now"), isOn: $start)
                    }
                    TextField(m.t("common.model"), text: $model)
                    TextField(m.t("common.work_folder"), text: $folder)
                }
                SaveButton {
                    let seat = name.trimmingCharacters(in: .whitespacesAndNewlines), org = m.organization
                    guard !seat.isEmpty else { throw RelicError.message(m.t("member.need_name")) }
                    if mode == "existing" {
                        guard let index = Int(sessionIndex), sessions.indices.contains(index) else { throw RelicError.message(m.t("member.pick_session")) }
                        try await m.post(Client.org(org, "/bind"), ["member": seat, "role": role, "session": sessions[index].raw])
                    } else if mode == "app" {
                        guard !harness.isEmpty else { throw RelicError.message(m.t("member.need_harness")) }
                        try await m.post(Client.org(org, "/members"), ["name": seat, "role": role, "harness": harness, "model": model, "folder": folder, "secretary": secretary])
                    } else {
                        try await m.post(Client.org(org, "/seat"), ["name": seat, "role": role, "harness": hostHarness, "surface": "cli", "model": model, "folder": folder, "effort": effort, "permission": permission, "environment": environment, "env": env, "start": start])
                    }
                    try await m.select(org, seat)
                }
            }.formStyle(.grouped)
        }.frame(maxHeight: 650)
        .task {
            m.run {
                harnesses = try await m.get("/api/harnesses").rows.filter { $0["available"].flag && !$0["later"].flag }; harness = harnesses.first?["id"].text ?? ""
                let found = try await m.get("/api/sessions"); sessions = found["sessions"].rows.filter { $0["harness"].text != "chatgpt" }; problems = found["problems"].rows
                sessionIndex = sessions.isEmpty ? "" : "0"
                options = try await m.get("/api/seat-options"); permission = options["claude_modes"].rows.first?.text ?? ""
            }
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject var m: Model
    @State private var language = "en-US"
    @State private var notify = false
    var body: some View {
        Form {
            Text(m.t("common.settings")).font(.title2)
            Picker(m.t("settings.language.title"), selection: $language) { Text("简体中文").tag("zh-CN"); Text("English").tag("en-US") }
            Toggle(m.t("settings.notify"), isOn: $notify)
            SaveButton { try await m.saveSettings(language: language, notify: notify) }
        }.formStyle(.grouped).onAppear { language = m.words.language; notify = m.preferences["notify"].flag }
    }
}

struct ProtocolForm: View {
    @EnvironmentObject var m: Model
    @State private var title = ""
    @State private var guidance = ""
    var body: some View {
        Form {
            Text(m.t("org.protocols")).font(.title2)
            TextField(m.t("common.name"), text: $title)
            TextField(m.t("org.protocols"), text: $guidance, axis: .vertical)
            SaveButton { try await m.post(m.path("/protocols"), ["title": title, "guidance": guidance, "strength": "weak"]); try await m.refresh() }
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
                        Text(copy["summary"].text).textSelection(.enabled)
                        Text(copy["author_display"].text + " · " + copy["status"].text)
                        Text(copy["stats"]["total"].text.isEmpty || copy["stats"]["total"].text == "0" ? m.t("cc.stats_none") : m.t("cc.stats", ["n": copy["stats"]["total"].text, "allow": copy["stats"]["allow"].text, "deny": copy["stats"]["deny"].text, "review": copy["stats"]["review"].text, "error": copy["stats"]["error"].text]))
                        DisclosureGroup(m.t("cc.code")) { Rows(copy["rules"].rows) { Text(pretty($0)).font(.system(.caption, design: .monospaced)).textSelection(.enabled) } }
                        HStack {
                            Button(m.t("cc.ack")) { m.run { try await m.post("/api/cc/" + copy["id"].text + "/read", [:]); try await m.refresh() } }
                            if copy["status"].text == "active" && ["", "active"].contains(copy["org_status"].text) { Button(m.t("cc.retire"), role: .destructive) { retire = copy } }
                        }
                    }.padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.frame(maxHeight: 600)
        .confirmationDialog(m.t("cc.retire"), isPresented: Binding(get: { retire != nil }, set: { if !$0 { retire = nil } }), presenting: retire) { copy in
            Button(m.t("cc.retire"), role: .destructive) { m.run { try await m.post("/api/cc/" + copy["id"].text + "/retire", [:]); try await m.refresh() } }
        } message: { copy in Text(m.t("cc.retire_confirm", ["id": copy["protocol_id"].text, "title": copy["title"].text, "org": copy["org_name"].text])) }
    }
}
