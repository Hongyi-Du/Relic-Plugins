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
            SettingsRow(title: m.t("settings.auto_names.label"), hint: m.t("settings.auto_names.hint"), last: true) { Toggle(m.t("settings.auto_names.label"), isOn: toggle("auto_names")).toggleStyle(SettingsToggleStyle()).labelsHidden() }
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
                Toggle(m.t("settings.desktop_notify"), isOn: Binding(get: { m.preferences["notify"].flag }, set: { value in m.run { try await m.saveSettings(language: m.words.language, notify: value) } })).toggleStyle(SettingsToggleStyle()).labelsHidden()
            }
            SettingsRow(title: m.t("settings.notify_test"), last: true) { TextButton(m.t("settings.notify_send_test")) { m.run { try await m.authorizeNotifications(); m.notify(m.t("settings.notify_on")) } }.buttonStyle(ReferenceButtonStyle(small: true)) }
        }
    }
    private var about: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Relic · " + m.preferences["version"].text).font(RelicStyle.font(20, weight: 600)).padding(.vertical, 10)
            SettingsRow(title: m.t("settings.data_folder"), hint: m.preferences["data"].text) { Button(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "data"]) } } }
            SettingsRow(title: m.t("settings.logs"), hint: m.t("settings.logs_hint")) { Button(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "logs"]) } } }
            SettingsRow(title: m.t("settings.local_server"), hint: m.t("settings.local_server_hint", ["port": m.preferences["port"].text])) { SmallBadge(text: m.t("settings.connected"), color: RelicStyle.green) }
            Text(m.t("settings.install_app_done")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).padding(.top, 14)
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
        VStack(alignment: .leading, spacing: 0) {
            Text(m.t("settings.harness_intro")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true).padding(.bottom, 8)
            ForEach(["node", "npm"], id: \.self) { id in
                SettingsRow(title: id == "node" ? "Node.js" : "npm", hint: m.t("settings.runtime_path_hint")) { pathRow(id, title: id == "node" ? "Node.js" : "npm") }
            }
            Text(m.t("settings.desktop_connections")).font(RelicStyle.font(15, weight: 600)).padding(.top, 22)
            SettingsRow(title: "Codex / ChatGPT", hint: m.platform["desktop_transport"]["reason"].text) { SmallBadge(text: m.t(m.platform["desktop_transport"]["available"].flag ? "settings.connected" : "settings.not_connected"), color: m.platform["desktop_transport"]["available"].flag ? RelicStyle.green : RelicStyle.muted) }
            SettingsRow(title: "Claude Desktop", hint: m.t("settings.claude_desktop_hint")) {
                Toggle("Claude Desktop", isOn: Binding(get: { m.platform["claude_desktop"]["enabled"].flag }, set: { value in m.run { m.platform = try await m.post("/api/platform", ["claude_desktop_enabled": value, "probe": true]) } })).toggleStyle(SettingsToggleStyle()).labelsHidden()
            }
            SettingsRow(title: m.t("settings.desktop_probe"), hint: m.t("settings.desktop_probe_hint")) { Button(m.t("settings.desktop_probe")) { m.run { m.platform = try await m.post("/api/platform", ["probe": true]) } } }
            VStack(spacing: 10) { Rows(harnesses.filter { !$0["later"].flag }) { harness in
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(harness["available"].flag ? m.t("settings.connected") : harness["problem"].text).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.secondary)
                        SettingsRow(title: m.t("settings.program")) { pathRow(harness["id"].text, title: m.t("settings.program")) }
                        Text(m.t(harness["adapter_installed"].flag ? "settings.adapter_version" : "settings.adapter_missing", ["adapter": harness["adapter"].text, "version": harness["adapter_version"].text])).accessibilityLabel(m.t("settings.adapter"))
                        Text("Node.js · " + (harness["node"].text.isEmpty ? m.t("settings.not_found") : harness["node"].text))
                        Text(m.t("settings.default_mode") + " · " + (harness["mode"].text.isEmpty ? m.t(harness["note"].text.isEmpty ? "settings.adapter_default" : "settings.adapter_default_note", ["note": harness["note"].text]) : harness["mode"].text))
                        Text(m.t("settings.models") + " · " + harness["models"].rows.map(\.text).joined(separator: m.t("settings.models_sep")))
                        Button(m.t(harness["adapter_installed"].flag ? "settings.reinstall_adapter" : "settings.install_adapter")) { m.run { m.installLogs[harness["id"].text] = [harness["install"].text]; try await m.post("/api/harnesses/" + Client.segment(harness["id"].text) + "/install", [:]) } }
                        if let lines = m.installLogs[harness["id"].text] { Text(lines.joined(separator: "\n")).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                    }.font(RelicStyle.font(12, weight: 400)).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 10)
                } label: {
                    HStack { Text(harness["title"].text).font(RelicStyle.font(13, weight: 600)); Text(harness["vendor"].text).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted); Spacer() }
                }.relicCard()
            } }.padding(.vertical, 16)
            DisclosureGroup(m.t("settings.later")) {
                VStack(alignment: .leading, spacing: 10) {
                    Rows(harnesses.filter { $0["later"].flag }) { Text($0["title"].text + " · " + $0["vendor"].text + " · " + $0["launch"].text) }
                    Text(m.t("settings.later_hint")).foregroundStyle(RelicStyle.muted)
                }.font(RelicStyle.font(12, weight: 400)).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
            }
        }.task { paths = m.preferences["paths"].object.mapValues { Node($0).text }; m.run { harnesses = try await m.get("/api/harnesses").rows } }
        .onChange(of: m.installLogs.mapValues { $0.count }) { if m.installLogs.values.contains(where: { $0.last == m.t("settings.install_done") }) { m.run { harnesses = try await m.get("/api/harnesses").rows } } }
    }
    func pathRow(_ id: String, title: String) -> some View {
        HStack(spacing: 6) {
            TextField(title, text: Binding(get: { paths[id] ?? "" }, set: { paths[id] = $0 }), prompt: Text(m.t("settings.auto_find"))).labelsHidden().textFieldStyle(.roundedBorder).help(title)
            Button(m.t("common.save")) { m.run { var saved = m.preferences["paths"].object; saved[id] = paths[id] ?? ""; try await m.savePreferences(["paths": saved]); m.notice = m.t("settings.path_saved") } }
        }
    }
}
