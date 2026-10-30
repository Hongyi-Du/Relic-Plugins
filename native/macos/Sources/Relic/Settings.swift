import SwiftUI
import UserNotifications
import RelicCore

struct SettingsView: View {
    @EnvironmentObject var m: Model
    @State private var name = ""
    @State private var voiceTest = ""
    private let sections = [("profile", "settings.profile"), ("appearance", "settings.appearance"), ("language", "settings.language.title"), ("voice", "common.voice_input"), ("notify", "settings.notify"), ("harness", "common.harness"), ("about", "settings.about")]
    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                ReferenceLabel(m.t("common.settings"), size: 16, weight: 650)
                    .padding(.top, 4).padding(.horizontal, 10).padding(.bottom, 12)
                ForEach(sections, id: \.0) { key, title in
                    SettingsNavigationButton(title: m.t(title), icon: sectionIcon(key), selected: m.settingsSection == key) { m.settingsSection = key }
                }
                Spacer(minLength: 0)
            }.padding(.vertical, 14).padding(.horizontal, 10).frame(width: 220)
                .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 1), kind: "region"))
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ReferenceLabel(m.t(sections.first { $0.0 == m.settingsSection }?.1 ?? "settings.about"), size: 18, weight: 650).padding(.bottom, 14)
                    switch m.settingsSection {
                    case "profile": profile
                    case "appearance": appearance
                    case "language": language
                    case "voice": voice
                    case "notify": notifications
                    case "harness": HarnessSettings()
                    default: about
                    }
                }.padding(.horizontal, 28).padding(.top, 22).padding(.bottom, 28).frame(maxWidth: .infinity, alignment: .topLeading)
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        }.onAppear { name = m.preferences["name"].text }
    }
    private func sectionIcon(_ key: String) -> String { ["profile": "user", "appearance": "palette", "language": "globe", "voice": "mic", "notify": "bell", "harness": "plug", "about": "info"][key] ?? "gear" }
    func preference(_ key: String) -> Binding<String> { Binding(get: { m.preferences[key].text }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    func toggle(_ key: String) -> Binding<Bool> { Binding(get: { m.preferences[key].flag }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    private var profile: some View {
        VStack(spacing: 6) {
            SettingsRow(title: m.t("settings.avatar"), hint: m.t("settings.avatar_hint")) {
                HStack(spacing: 10) {
                    Avatar(member: "human", size: 60)
                    TextButton(m.t("common.change")) { m.run { try await pickAvatar(m) } }.buttonStyle(ReferenceButtonStyle(small: true))
                    if !m.preferences["avatar"].text.isEmpty { TextButton(m.t("settings.remove")) { m.run { try await m.post("/api/avatar", ["data": ""]); m.preferences = try await m.get("/api/prefs") } }.buttonStyle(ReferenceButtonStyle(small: true)) }
                }
            }
            SettingsRow(title: m.t("common.name"), hint: m.t("settings.name_hint"), last: true) {
                ReferenceInput(placeholder: m.t("common.you"), text: $name, commit: saveName).frame(width: 220)
            }
        }
    }
    private func saveName() { m.run { try await m.savePreferences(["name": name.trimmingCharacters(in: .whitespacesAndNewlines)]) } }
    private var appearance: some View {
        VStack(spacing: 6) {
            SettingsRow(title: m.t("settings.theme")) {
                SettingsSegments(options: Choices.themes.map { ($0.0, m.t($0.1)) }, selection: preference("theme"))
            }
            SettingsRow(title: m.t("settings.accent"), hint: m.t("settings.accent_hint")) {
                HStack(spacing: 8) {
                    ForEach(["clay", "ink", "indigo", "blue", "rose", "amber"], id: \.self) { color in
                        SettingsSwatch(name: color, selected: m.preferences["accent"].text == color) { m.run { try await m.savePreferences(["accent": color]) } }
                    }
                }
            }
            SettingsRow(title: m.t("settings.font_size")) {
                SettingsSegments(options: Choices.fonts.map { ($0.0, m.t($0.1)) }, selection: preference("font"))
            }
            SettingsRow(title: m.t("settings.density"), last: true) {
                SettingsSegments(options: Choices.densities.map { ($0.0, m.t($0.1)) }, selection: preference("density"))
            }
        }
    }
    private var language: some View {
        VStack(spacing: 6) {
            SettingsRow(title: m.t("settings.language.label"), hint: m.t("settings.language.hint")) {
                ReferenceSelectField(title: m.t("settings.language.label"), selection: preference("lang"), options: [("", m.t("settings.language.system", ["lang": Words.normalize(Locale.current.identifier)]))] + m.words.languages.map { ($0["code"].text, $0["name"].text) }).frame(width: 200)
            }
            SettingsRow(title: m.t("settings.auto_names.label"), hint: m.t("settings.auto_names.hint"), last: true) { ReferenceSwitch(m.t("settings.auto_names.label"), isOn: toggle("auto_names")) }
        }
    }
    private var voice: some View {
        VStack(alignment: .leading, spacing: 6) {
            SettingsRow(title: m.t("common.voice_input"), hint: m.t("settings.voice_hint")) {
                SettingsSegments(options: [("browser", m.t("settings.voice_browser")), ("off", m.t("settings.voice_off"))], selection: preference("voice"))
            }
            SettingsRow(title: m.t("settings.voice_try"), hint: m.t("settings.voice_supported_mac")) {
                TextField(m.t("settings.voice_try_here"), text: $voiceTest, axis: .vertical).textFieldStyle(.plain).labelsHidden()
                    .font(RelicStyle.font(14, weight: 400)).lineLimit(2...2)
                    .padding(.vertical, 7).padding(.leading, 10).padding(.trailing, 34).frame(width: 300, height: 60.8)
                    .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 9))
                    .overlay(alignment: .trailing) { VoiceButton(text: $voiceTest).padding(.trailing, 4) }
            }
            ReferenceLabel(m.t("settings.voice_mac"), size: 12.5, color: RelicStyle.muted, lineHeight: 21.25, lines: 0).padding(.top, 10)
        }
    }
    private var notifications: some View {
        VStack(spacing: 6) {
            SettingsRow(title: m.t("settings.desktop_notify"), hint: m.t("settings.desktop_notify_hint")) {
                ReferenceSwitch(m.t("settings.desktop_notify"), isOn: Binding(get: { m.preferences["notify"].flag }, set: { value in m.run { try await m.saveSettings(language: m.words.language, notify: value) } }))
            }
            SettingsRow(title: m.t("settings.notify_test"), last: true) { TextButton(m.t("settings.notify_send_test")) { m.run { try await m.authorizeNotifications(); m.notify(m.t("settings.notify_on")) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
        }
    }
    private var about: some View {
        VStack(alignment: .leading, spacing: 6) {
            SettingsRow(title: m.t("settings.data_folder"), hint: m.preferences["data"].text.isEmpty ? "~/.relic" : m.preferences["data"].text) { TextButton(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "data"]) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
            SettingsRow(title: m.t("settings.logs"), hint: m.t("settings.logs_hint")) { TextButton(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "logs"]) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
            SettingsRow(title: m.t("settings.local_server"), hint: m.t("settings.local_server_hint", ["port": m.preferences["port"].text])) { OverviewChip(text: "v" + m.preferences["version"].text) }
            SettingsRow(title: m.t("settings.install_app"), hint: m.t("settings.install_app_done"), last: true) { OverviewChip(text: m.t("settings.installed"), tone: "ok") }
        }
    }
}

private struct SettingsRow<Content: View>: View {
    let title: String
    var hint = ""
    var last = false
    @ViewBuilder let content: () -> Content
    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                ReferenceLabel(title, size: 13.5, weight: 600, lines: 0)
                if !hint.isEmpty { ReferenceLabel(hint, size: 12.5, color: RelicStyle.muted, lines: 0) }
            }.frame(maxWidth: .infinity, alignment: .leading)
            content().fixedSize(horizontal: true, vertical: false)
        }.padding(.vertical, 14).padding(.bottom, last ? 0 : 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: last ? 0 : 1, trailing: 0), kind: "region"))
    }
}

struct HarnessSettings: View {
    @EnvironmentObject var m: Model
    @State private var harnesses: [Node] = []
    @State private var paths: [String: String] = [:]
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ReferenceLabel(m.t("settings.harness_intro"), size: 12.5, color: RelicStyle.muted, lines: 0).padding(.bottom, 12)
            ForEach(["node", "npm"], id: \.self) { id in
                SettingsRow(title: id == "node" ? "Node.js" : "npm", hint: m.t("settings.runtime_path_hint")) { pathRow(id, placeholder: m.t("settings.auto_find")).frame(width: 280) }
            }
            ReferenceLabel(m.t("settings.desktop_connections"), size: 18, weight: 650).padding(.bottom, 8)
            SettingsRow(title: "Codex / ChatGPT", hint: m.platform["desktop_transport"]["reason"].text.isEmpty ? m.t("settings.desktop_probe_hint") : m.platform["desktop_transport"]["reason"].text) { OverviewChip(text: m.t(m.platform["desktop_transport"]["available"].flag ? "settings.connected" : "settings.not_connected"), tone: m.platform["desktop_transport"]["available"].flag ? "ok" : "") }
            SettingsRow(title: "Claude Desktop", hint: m.platform["claude_desktop"]["reason"].text.isEmpty ? m.t("settings.claude_desktop_hint") : m.platform["claude_desktop"]["reason"].text) {
                ReferenceSwitch("Claude Desktop", isOn: Binding(get: { m.platform["claude_desktop"]["enabled"].flag }, set: { value in m.run { m.platform = try await m.post("/api/platform", ["claude_desktop_enabled": value, "probe": true]) } }))
            }
            ReferenceLabel(m.t("settings.claude_desktop_hint"), size: 14, color: RelicStyle.muted, lines: 0)
            SettingsRow(title: m.t("settings.desktop_probe"), hint: m.t("settings.desktop_probe_hint")) { TextButton(m.t("settings.desktop_probe")) { m.run { m.platform = try await m.post("/api/platform", ["probe": true]) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
            Rows(harnesses.filter { !$0["later"].flag }) { harness in
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        ReferenceLabel(harness["title"].text, size: 14, weight: 700)
                        ReferenceLabel(harness["vendor"].text, size: 14, color: RelicStyle.muted)
                        Spacer(minLength: 0)
                        TextButton(m.t(harness["adapter_installed"].flag ? "settings.reinstall_adapter" : "settings.install_adapter")) { m.run { m.installLogs[harness["id"].text] = ["$ " + harness["install"].text]; try await m.post("/api/harnesses/" + Client.segment(harness["id"].text) + "/install", [:]) } }.buttonStyle(ReferenceButtonStyle(small: true))
                    }
                    VStack(alignment: .leading, spacing: 7) {
                        row(m.t("common.status")) { OverviewChip(text: harness["available"].flag ? m.t("settings.connected") : harness["problem"].text.isEmpty ? m.t("settings.not_connected") : harness["problem"].text, tone: harness["available"].flag ? "ok" : "bad") }
                        row(m.t("settings.program")) { pathRow(harness["id"].text, placeholder: harness["program"].text.isEmpty ? m.t("settings.auto_find") : harness["program"].text, small: true) }
                        row(m.t("settings.adapter")) { text(m.t(harness["adapter_installed"].flag ? "settings.adapter_version" : "settings.adapter_missing", ["adapter": harness["adapter"].text, "version": harness["adapter_version"].text])) }
                        row("Node.js") { text(harness["node"].text.isEmpty ? m.t("settings.not_found") : harness["node"].text) }
                        row(m.t("settings.default_mode")) { text(harness["mode"].text.isEmpty ? m.t(harness["note"].text.isEmpty ? "settings.adapter_default" : "settings.adapter_default_note", ["note": harness["note"].text]) : harness["mode"].text) }
                        if !harness["models"].rows.isEmpty { row(m.t("settings.models")) { text(harness["models"].rows.map(\.text).joined(separator: m.t("settings.models_sep"))) } }
                    }.padding(.vertical, 12.5)
                    if let lines = m.installLogs[harness["id"].text] {
                        FittingScroll(maxHeight: 144) { SelectableText(value: AttributedString(lines.joined(separator: "\n")), pointSize: 11.5, lineHeight: 17.25, monospaced: true).frame(maxWidth: .infinity, alignment: .leading) }
                            .padding(8).modifier(RecordedSurface(background: RelicStyle.code, radius: 8, kind: "code"))
                    }
                }.padding(14).modifier(RecordedSurface(background: .clear, border: RelicStyle.line, borderWidth: 1, radius: 12, kind: "card")).padding(.bottom, 10)
            }
            ReferenceLabel(m.t("settings.later"), size: 15, weight: 650).padding(.top, 12).padding(.bottom, 8)
            VStack(alignment: .leading, spacing: 6) {
                Rows(harnesses.filter { $0["later"].flag }) { harness in
                    HStack(alignment: .top, spacing: 10) {
                        (Text(harness["title"].text).font(RelicStyle.font(12.5, weight: 700)) + Text(" " + harness["vendor"].text).font(RelicStyle.font(12.5, weight: 400)).foregroundColor(RelicStyle.muted)).fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                        ReferenceLabel(harness["launch"].text, size: 12.5, color: RelicStyle.muted, lines: 0, monospaced: true)
                    }.padding(.horizontal, 10).padding(.vertical, 8).modifier(RecordedSurface(background: .clear, border: RelicStyle.border, borderWidth: 1, radius: 10, kind: "row", borderDash: [3, 3]))
                }
            }
            ReferenceLabel(m.t("settings.later_hint"), size: 12, color: RelicStyle.muted, lines: 0).padding(.top, 8)
        }.task { paths = m.preferences["paths"].object.mapValues { Node($0).text }; m.run { harnesses = try await m.get("/api/harnesses").rows } }
        .onChange(of: m.installLogs.mapValues { $0.count }) { if m.installLogs.values.contains(where: { $0.last == m.t("settings.install_done") }) { m.run { harnesses = try await m.get("/api/harnesses").rows } } }
    }
    private func text(_ value: String) -> some View { ReferenceLabel(value, size: 12.5, lines: 0) }
    private func row<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .top, spacing: 12) { ReferenceLabel(label, size: 12.5, color: RelicStyle.muted, lines: 0).frame(width: 76, alignment: .leading); content().frame(maxWidth: .infinity, alignment: .leading) }
    }
    private func pathRow(_ id: String, placeholder: String, small: Bool = false) -> some View {
        HStack(alignment: .top, spacing: 6) {
            ReferenceInput(placeholder: placeholder, text: Binding(get: { paths[id] ?? "" }, set: { paths[id] = $0 }), height: small ? 35.2 : 38.4, pointSize: small ? 12 : 14, monospaced: true, voice: false)
            TextButton(m.t("common.save")) { m.run { var saved = m.preferences["paths"].object; saved[id] = (paths[id] ?? "").trimmingCharacters(in: .whitespacesAndNewlines); try await m.savePreferences(["paths": saved]); m.notice = m.t("settings.path_saved"); harnesses = try await m.get("/api/harnesses").rows } }.buttonStyle(ReferenceButtonStyle(small: true))
        }
    }
}
