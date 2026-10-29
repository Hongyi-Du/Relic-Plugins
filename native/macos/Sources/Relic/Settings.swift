import SwiftUI
import UserNotifications
import RelicCore

struct SettingsView: View {
    @EnvironmentObject var m: Model
    @State private var name = ""
    @State private var voiceTest = ""
    private let sections = [("profile", "settings.profile"), ("appearance", "settings.appearance"), ("language", "settings.language.title"), ("voice", "common.voice_input"), ("notify", "settings.notify"), ("harness", "common.harness"), ("about", "settings.about")]
    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 16) { ForEach(sections, id: \.0) { key, title in Button(m.t(title)) { m.settingsSection = key }.buttonStyle(.plain).fontWeight(m.settingsSection == key ? .bold : .regular) }; Spacer() }.padding(12).frame(width: 180)
            Form {
                switch m.settingsSection {
                case "profile": profile
                case "appearance": appearance
                case "language": language
                case "voice": voice
                case "notify": notifications
                case "harness": HarnessSettings()
                default: about
                }
            }.formStyle(.grouped).frame(minWidth: 540)
        }.frame(width: 820, height: 620).onAppear { name = m.preferences["name"].text }
    }
    func preference(_ key: String) -> Binding<String> { Binding(get: { m.preferences[key].text }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    func toggle(_ key: String) -> Binding<Bool> { Binding(get: { m.preferences[key].flag }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    private var profile: some View {
        Section(m.t("settings.profile")) {
            HStack { Avatar(member: "human", size: 60); Button(m.t("common.change")) { m.run { try await pickAvatar(m) } }; Button(m.t("settings.remove")) { m.run { try await m.post("/api/avatar", ["data": ""]); m.preferences = try await m.get("/api/prefs") } } }
            Text(m.t("settings.avatar_hint")).font(.caption)
            TextField(m.t("common.name"), text: $name).onSubmit { m.run { try await m.savePreferences(["name": name]) } }
            Text(m.t("settings.name_hint")).font(.caption)
            Button(m.t("common.save")) { m.run { try await m.savePreferences(["name": name]) } }
        }
    }
    private var appearance: some View {
        Section(m.t("settings.appearance")) {
            Picker(m.t("settings.theme"), selection: preference("theme")) { ForEach(["system", "light", "dark"], id: \.self) { Text(m.t("common.theme_" + $0)).tag($0) } }
            HStack { Text(m.t("settings.accent")); ForEach(["clay", "ink", "indigo", "blue", "rose", "amber"], id: \.self) { color in Button { m.run { try await m.savePreferences(["accent": color]) } } label: { Circle().fill(accent(color)).frame(width: 24, height: 24).overlay { if m.preferences["accent"].text == color { Image(systemName: "checkmark").foregroundStyle(.white) } } }.buttonStyle(.plain).accessibilityLabel(color) } }
            Text(m.t("settings.accent_hint")).font(.caption)
            Picker(m.t("settings.font_size"), selection: preference("font")) { ForEach(["small", "medium", "large"], id: \.self) { Text(m.t("common.size_" + $0)).tag($0) } }
            Picker(m.t("settings.density"), selection: preference("density")) { ForEach(["comfortable", "compact"], id: \.self) { Text(m.t("settings.density_" + $0)).tag($0) } }
        }
    }
    private var language: some View {
        Section(m.t("settings.language.title")) {
            Picker(m.t("settings.language.label"), selection: Binding(get: { m.words.language }, set: { value in m.run { try await m.saveSettings(language: value, notify: m.preferences["notify"].flag) } })) { Rows(m.words.languages) { Text($0["name"].text).tag($0["code"].text) } }
            Text(m.t("settings.language.hint")).font(.caption)
            Toggle(m.t("settings.auto_names.label"), isOn: toggle("auto_names")); Text(m.t("settings.auto_names.hint")).font(.caption)
        }
    }
    private var voice: some View {
        Section(m.t("common.voice_input")) {
            Picker(m.t("common.voice_input"), selection: preference("voice")) { Text(m.t("native.speech")).tag("browser"); Text(m.t("settings.voice_off")).tag("off") }
            Text(m.t("settings.voice_hint")); TextField(m.t("settings.voice_try_here"), text: $voiceTest, axis: .vertical); VoiceButton(text: $voiceTest)
            Text(m.t("settings.voice_mac")).font(.caption)
        }
    }
    private var notifications: some View {
        Section(m.t("settings.notify")) {
            Toggle(m.t("settings.desktop_notify"), isOn: Binding(get: { m.preferences["notify"].flag }, set: { value in m.run { try await m.saveSettings(language: m.words.language, notify: value) } }))
            Text(m.t("settings.desktop_notify_hint"))
            Button(m.t("settings.notify_send_test")) { m.run { let allowed = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]); if allowed { m.notify(m.t("settings.notify_on")) } else { throw RelicError.message(m.t("settings.notify_denied")) } } }
        }
    }
    private var about: some View {
        Section(m.t("settings.about")) {
            Text("Relic · " + m.preferences["version"].text).font(.title2)
            Text(m.t("settings.data_folder")); Text(m.preferences["data"].text).textSelection(.enabled)
            Button(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "data"]) } }
            Text(m.t("settings.logs_hint")); Button(m.t("settings.logs")) { m.run { try await m.post("/api/open", ["what": "logs"]) } }
            Text(m.t("settings.local_server_hint", ["port": m.preferences["port"].text])); Text(m.t("settings.install_app_done"))
        }
    }
}

struct HarnessSettings: View {
    @EnvironmentObject var m: Model
    @State private var harnesses: [Node] = []
    @State private var paths: [String: String] = [:]
    var body: some View {
        Section(m.t("common.harness")) {
            Text(m.t("settings.harness_intro"))
            ForEach(["node", "npm"], id: \.self) { id in pathRow(id, title: id == "node" ? "Node.js" : "npm") }
            Text(m.t("settings.runtime_path_hint")).font(.caption)
            Text(m.t("settings.desktop_connections")).font(.headline)
            Text("Codex / ChatGPT · " + m.t(m.platform["desktop_transport"]["available"].flag ? "settings.connected" : "settings.not_connected"))
            Text(m.platform["desktop_transport"]["reason"].text).font(.caption)
            Toggle("Claude Desktop", isOn: Binding(get: { m.platform["claude_desktop"]["enabled"].flag }, set: { value in m.run { m.platform = try await m.post("/api/platform", ["claude_desktop_enabled": value, "probe": true]) } }))
            Text(m.t("settings.claude_desktop_hint")).font(.caption)
            Button(m.t("settings.desktop_probe")) { m.run { m.platform = try await m.post("/api/platform", ["probe": true]) } }.help(m.t("settings.desktop_probe_hint"))
            Rows(harnesses.filter { !$0["later"].flag }) { harness in
                DisclosureGroup(harness["title"].text + " · " + harness["vendor"].text) {
                    Text(harness["available"].flag ? m.t("settings.connected") : harness["problem"].text)
                    pathRow(harness["id"].text, title: m.t("settings.program"))
                    Text(m.t(harness["adapter_installed"].flag ? "settings.adapter_version" : "settings.adapter_missing", ["adapter": harness["adapter"].text, "version": harness["adapter_version"].text]))
                    Text("Node.js · " + (harness["node"].text.isEmpty ? m.t("settings.not_found") : harness["node"].text))
                    Text(m.t("settings.default_mode") + " · " + (harness["mode"].text.isEmpty ? m.t("settings.adapter_default") : harness["mode"].text))
                    Text(m.t("settings.models") + " · " + harness["models"].rows.map(\.text).joined(separator: m.t("settings.models_sep")))
                    Button(m.t(harness["adapter_installed"].flag ? "settings.reinstall_adapter" : "settings.install_adapter")) { m.run { m.installLogs[harness["id"].text] = [harness["install"].text]; try await m.post("/api/harnesses/" + Client.segment(harness["id"].text) + "/install", [:]) } }
                    if let lines = m.installLogs[harness["id"].text] { Text(lines.joined(separator: "\n")).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                }
            }
            DisclosureGroup(m.t("settings.later")) { Rows(harnesses.filter { $0["later"].flag }) { Text($0["title"].text + " · " + $0["vendor"].text + " · " + $0["launch"].text) }; Text(m.t("settings.later_hint")) }
        }.task { paths = m.preferences["paths"].object.mapValues { Node($0).text }; m.run { harnesses = try await m.get("/api/harnesses").rows } }
        .onChange(of: m.installLogs.mapValues { $0.count }) { if m.installLogs.values.contains(where: { $0.last == m.t("settings.install_done") }) { m.run { harnesses = try await m.get("/api/harnesses").rows } } }
    }
    func pathRow(_ id: String, title: String) -> some View {
        HStack { TextField(title, text: Binding(get: { paths[id] ?? "" }, set: { paths[id] = $0 }), prompt: Text(m.t("settings.auto_find"))); Button(m.t("common.save")) { m.run { var saved = m.preferences["paths"].object; saved[id] = paths[id] ?? ""; try await m.savePreferences(["paths": saved]) } } }
    }
}
