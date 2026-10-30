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
    @State private var sessionsLoading = false
    private var submitLabel: String {
        if !m.editMember.isEmpty { return "common.save" }
        if mode == "existing" { return "member.bind" }
        if mode == "app" { return m.newSecretary ? "member.create_secretary" : "member.create_member" }
        return start ? "member.create_start" : "member.create_seat_only"
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading
            VStack(alignment: .leading, spacing: 12) {
                if mode == "existing" { existingFields }
                else {
                    field("member.name_label", placeholder: "member.name_placeholder", text: $name).disabled(!m.editMember.isEmpty)
                    field("common.role", placeholder: m.newSecretary ? "member.role_placeholder_secretary" : "member.role_placeholder", text: $role)
                    if mode == "app" { appFields } else { hostFields }
                }
            }
            SaveButton(labelKey: submitLabel, reserveErrorSpace: true, available: !loading && (mode != "existing" || !sessionsLoading), action: save)
        }.frame(maxWidth: .infinity, alignment: .topLeading)
        .task {
            do {
                defer { loading = false }
                mode = m.editMember.isEmpty ? m.memberMode : "host"; secretary = m.newSecretary
                if secretary { name = "secretary" }
                async let availableHarnesses = m.get("/api/harnesses")
                async let seatOptions = m.get("/api/seat-options")
                let loaded = try await (availableHarnesses, seatOptions)
                harnesses = loaded.0.rows; harness = harnesses.first { $0["available"].flag && !$0["later"].flag }?["id"].text ?? ""
                sessionIndex = ""
                options = loaded.1; permission = options["claude_modes"].rows.first?.text ?? ""
                if !m.editMember.isEmpty {
                    let card = try await m.get(m.path("/member/" + Client.segment(m.editMember))); original = card["config"]
                    name = m.editMember; role = card["role"].text; hostHarness = original["harness"].text.isEmpty ? "claude-code" : original["harness"].text; surface = original["surface"].text.isEmpty ? "cli" : original["surface"].text
                    model = original["model"].text; effort = original["effort"].text; folder = original["folder"].text
                    environment = original["environment"].text.isEmpty ? "local" : original["environment"].text; permission = original["permission"].text.isEmpty ? (options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.first?.text ?? "") : original["permission"].text
                    env = original["env"].object.sorted { $0.key < $1.key }.map { $0.key + "=" + Node($0.value).text }.joined(separator: "\n")
                }
            } catch is CancellationError {} catch { m.error = error.localizedDescription }
        }.task(id: mode) {
            guard mode == "existing" else { return }
            sessionsLoading = true
            defer { sessionsLoading = false }
            do {
                let found = try await m.get("/api/sessions")
                sessions = found["sessions"].rows.filter { $0["harness"].text != "chatgpt" || m.platform["chatgpt_delivery"].flag }; problems = found["problems"].rows
            } catch is CancellationError {} catch { m.error = error.localizedDescription }
        }
    }

    @ViewBuilder private var heading: some View {
        ReferenceLabel(!m.editMember.isEmpty ? m.t("member.edit_title", ["name": m.name(m.editMember)]) : m.newSecretary ? m.t("secretary.new_embedded") : m.t("common.add_member"), size: 17, weight: 650, lines: 0)
        if m.editMember.isEmpty && !m.newSecretary {
            SettingsSegments(options: [("app", m.t("member.run_app")), ("host", m.t(Capabilities.hostKinds(m.platform).contains(where: { $0.hasSuffix("/gui") }) ? "member.run_host" : "member.run_host_mac")), ("existing", m.t("member.run_existing"))], selection: $mode)
        } else { Color.clear.frame(height: 0).accessibilityHidden(true) }
        ReferenceLabel(m.t(!m.editMember.isEmpty ? "member.edit_note" : mode == "host" ? "member.note_host_mac" : mode == "existing" ? "member.note_existing_mac" : "member.note_app"), size: 12.5, color: RelicStyle.muted, lines: 0)
    }
    private func field(_ key: String, placeholder: String, text: Binding<String>) -> some View {
        NativeFormField(title: m.t(key)) {
            ReferenceInput(placeholder: m.t(placeholder), text: text, height: 36, pointSize: 12.5,
                           suggestions: key == "member.which_seat" ? m.members.map { $0["name"].text } : key == "common.model" && mode == "host" && hostHarness == "claude-code" ? options["claude_models"].rows.map(\.text).filter { !$0.isEmpty } : [],
                           controlID: key == "member.which_seat" ? "member-seat-name" : key == "common.model" ? "member-model" : "")
        }
    }
    private func toggle(_ key: String, value: Binding<Bool>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Toggle(m.t(key), isOn: value).toggleStyle(SettingsToggleStyle()).labelsHidden()
            ReferenceLabel(m.t(key), size: 12.5, color: RelicStyle.secondary, lines: 0).onTapGesture { value.wrappedValue.toggle() }
        }
    }

    @ViewBuilder private var existingFields: some View {
        field("common.session", placeholder: "member.session_search", text: $search)
        FittingScroll(maxHeight: 246) {
            VStack(alignment: .leading, spacing: 4) {
                if loading || sessionsLoading { ReferenceLabel(m.t("member.finding_sessions"), size: 14, color: RelicStyle.muted, lines: 0) }
                if !loading && !sessionsLoading && sessions.isEmpty { ReferenceLabel(m.t("member.no_sessions"), size: 14, color: RelicStyle.muted, lines: 0) }
                if !search.isEmpty && !sessions.contains(where: { [$0["title"].text, $0["cwd"].text, $0["id"].text].joined(separator: " ").localizedCaseInsensitiveContains(search) }) { ReferenceLabel(m.t("member.no_match"), size: 14, color: RelicStyle.muted, lines: 0) }
                ForEach(Array(sessions.enumerated().filter { search.isEmpty || [$0.element["title"].text, $0.element["cwd"].text, $0.element["id"].text].joined(separator: " ").localizedCaseInsensitiveContains(search) }.prefix(80)), id: \.offset) { index, session in
                    Button { sessionIndex = String(index) } label: {
                        HStack(spacing: 8) {
                            OverviewChip(text: sessionHarnessLabel(session))
                            ReferenceLabel(session["title"].text.isEmpty ? session["id"].text : session["title"].text, size: 12.5).frame(maxWidth: .infinity, alignment: .leading)
                            ReferenceLabel(ReferenceText.clip(session["cwd"].text, to: 40), size: 11.5, color: RelicStyle.muted, monospaced: true).frame(maxWidth: 150, alignment: .leading)
                            if !Capabilities.automatic(m.platform, harness: session["harness"].text, surface: session["surface"].text) { OverviewChip(text: m.t("member.manual_delivery")).help(m.t("member.desktop_manual")) }
                            if session["updated"].integer > 0 { ReferenceLabel(m.ago(Node(session["updated"].integer)), size: 12.5, color: RelicStyle.muted) }
                        }.padding(.horizontal, 8).padding(.vertical, 6)
                            .modifier(RecordedSurface(background: sessionIndex == String(index) ? RelicStyle.accent.opacity(0.14) : .clear, radius: 8, kind: "list-row", selected: sessionIndex == String(index)))
                    }.buttonStyle(.plain).help(sessionLabel(session))
                }
                if !problems.isEmpty { ReferenceLabel(problems.map(\.text).joined(separator: m.t("member.problem_sep")), size: 11.5, color: RelicStyle.muted, lines: 0) }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.padding(7).modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 10, kind: "region"))
        field("member.which_seat", placeholder: "member.seat_placeholder", text: $name)
        field("member.role_new", placeholder: "member.role_placeholder", text: $role)
    }
    private func sessionHarnessLabel(_ session: Node) -> String {
        let id = session["harness"].text
        let title = harnesses.first { $0["id"].text == id }?["title"].text ?? id
        return ["gui", "cli"].contains(session["surface"].text) ? m.t(session["surface"].text == "gui" ? "member.harness_gui" : "member.harness_cli", ["harness": title]) : title
    }

    @ViewBuilder private var appFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            ReferenceLabel(m.t("member.harness_label"), size: 12.5, color: RelicStyle.muted)
            Rows(harnesses.filter { !$0["later"].flag }) { option in
                HStack(spacing: 10) {
                    NativeRadio(selected: Binding(get: { harness == option["id"].text }, set: { if $0 { harness = option["id"].text } }))
                    VStack(alignment: .leading, spacing: 0) {
                        (Text(option["title"].text).font(RelicStyle.font(12.5, weight: 700)) + Text(" " + option["vendor"].text).font(RelicStyle.font(12.5, weight: 400)).foregroundColor(RelicStyle.muted)).fixedSize(horizontal: false, vertical: true)
                        ReferenceLabel(option["available"].flag ? m.t("member.connected", ["program": ReferenceText.clip(option["program"].text, to: 48)]) : option["problem"].text, size: 12, color: RelicStyle.muted, lines: 0)
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }.padding(.horizontal, 12).padding(.vertical, 10)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 10, kind: "card"))
                    .contentShape(Rectangle()).onTapGesture { if option["available"].flag { harness = option["id"].text } }.disabled(!option["available"].flag).recordedOpacity(option["available"].flag ? 1 : 0.5)
            }
            if harnesses.contains(where: { $0["later"].flag }) {
                FlowLayout(spacing: 6) {
                    ReferenceLabel(m.t("member.later_acp"), size: 12, color: RelicStyle.muted)
                    Rows(harnesses.filter { $0["later"].flag }) { item in OverviewChip(text: item["title"].text).help(item["vendor"].text + " · " + item["launch"].text) }
                }
            }
        }
        field("common.model", placeholder: "member.model_placeholder", text: $model)
        field("common.work_folder", placeholder: "member.folder_placeholder", text: $folder)
        toggle("member.make_secretary", value: $secretary)
    }

    @ViewBuilder private var hostFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            ReferenceLabel(m.t("member.where_run"), size: 12.5, color: RelicStyle.muted)
            LazyVGrid(columns: [.init(.flexible()), .init(.flexible())], alignment: .leading, spacing: 6) {
                ForEach(Capabilities.hostKinds(m.platform), id: \.self) { kind in
                    let parts = kind.split(separator: "/").map(String.init)
                    HStack(spacing: 10) {
                        NativeRadio(selected: Binding(get: { kind == hostHarness + "/" + surface }, set: { if $0 { hostHarness = parts[0]; surface = parts[1]; permission = options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.first?.text ?? "" } }))
                        ReferenceLabel(m.t(parts[1] == "gui" ? "member.harness_gui" : "member.harness_cli", ["harness": harnesses.first { $0["id"].text == parts[0] }?["title"].text ?? parts[0]]), size: 12.5, weight: 700, color: RelicStyle.secondary, lines: 0).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(.horizontal, 12).padding(.vertical, 10).modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 10, kind: "card"))
                }
            }
            if !Capabilities.automatic(m.platform, harness: original["harness"].text, surface: original["surface"].text) { ReferenceLabel(m.t("member.choose_supported_host"), size: 14, color: RelicStyle.muted, lines: 0) }
        }
        HStack(alignment: .top, spacing: 12) {
            field("common.model", placeholder: "member.model_placeholder", text: $model)
            NativeFormField(title: m.t("member.effort")) { ReferenceSelectField(title: m.t("member.effort"), selection: $effort, options: options["efforts"].rows.map { ($0.text, $0.text.isEmpty ? m.t("common.default_effort") : $0.text) }, pointSize: 12.5) }
        }
        field("member.work_folder", placeholder: "member.host_folder_placeholder", text: $folder)
        HStack(alignment: .top, spacing: 12) {
            NativeFormField(title: m.t("member.environment")) { ReferenceSelectField(title: m.t("member.environment"), selection: $environment, options: [("local", m.t("member.env_local")), ("worktree", m.t("member.env_worktree"))], pointSize: 12.5) }
            NativeFormField(title: m.t("member.permission")) { ReferenceSelectField(title: m.t("member.permission"), selection: $permission, options: options[hostHarness == "codex" ? "codex_sandboxes" : "claude_modes"].rows.map { ($0.text,$0.text) }, pointSize: 12.5) }
        }
        NativeFormField(title: m.t("member.env_vars")) { NativeTextArea(placeholder: m.t("member.env_placeholder"), text: $env, rows: 3, pointSize: 11.5, voice: false) }
        if m.editMember.isEmpty { toggle("member.start_now", value: $start) }
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
