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
            List(sections, id: \.0) { key, title in
                Button { m.settingsSection = key } label: { Label(m.t(title), systemImage: sectionIcon(key)).font(.system(size: 13)).lineLimit(2).padding(.vertical, 7).frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(QuietButtonStyle(selected: m.settingsSection == key)).help(m.t(title)).listRowSeparator(.hidden)
            }.listStyle(.sidebar).scrollContentBackground(.hidden).frame(width: 210).background(RelicStyle.sidebar)
            ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(m.t(sections.first { $0.0 == m.settingsSection }?.1 ?? "settings.about")).font(.system(size: 17, weight: .semibold)).padding(.bottom, 12)
                        switch m.settingsSection {
                        case "profile": profile
                        case "appearance": appearance
                        case "language": language
                        case "voice": voice
                        case "notify": notifications
                        case "harness": HarnessSettings()
                        default: about
                        }
                    }.padding(.horizontal, 24).padding(.vertical, 20).frame(maxWidth: .infinity, alignment: .topLeading)
                }.frame(minWidth: 390)
        }.frame(minWidth: 580, idealWidth: 760, maxWidth: 900, minHeight: 400, idealHeight: 530, maxHeight: 550).onAppear { name = m.preferences["name"].text }
    }
    private func sectionIcon(_ key: String) -> String { ["profile": "person.crop.circle", "appearance": "paintpalette", "language": "globe", "voice": "mic", "notify": "bell", "harness": "puzzlepiece.extension", "about": "info.circle"][key] ?? "gearshape" }
    func preference(_ key: String) -> Binding<String> { Binding(get: { m.preferences[key].text }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    func toggle(_ key: String) -> Binding<Bool> { Binding(get: { m.preferences[key].flag }, set: { value in m.run { try await m.savePreferences([key: value]) } }) }
    private var profile: some View {
        VStack(spacing: 0) {
            SettingsRow(title: m.t("settings.avatar"), hint: m.t("settings.avatar_hint")) {
                HStack(spacing: 10) {
                    Avatar(member: "human", size: 52)
                    Button(m.t("common.change")) { m.run { try await pickAvatar(m) } }
                    if !m.preferences["avatar"].text.isEmpty { Button(m.t("settings.remove")) { m.run { try await m.post("/api/avatar", ["data": ""]); m.preferences = try await m.get("/api/prefs") } } }
                }
            }
            SettingsRow(title: m.t("common.name"), hint: m.t("settings.name_hint")) {
                VStack(alignment: .trailing, spacing: 8) {
                    TextField(m.t("common.you"), text: $name).textFieldStyle(.roundedBorder).onSubmit(saveName).dictation($name)
                    Button(m.t("common.save"), action: saveName)
                }
            }
        }
    }
    private func saveName() { m.run { try await m.savePreferences(["name": name.trimmingCharacters(in: .whitespacesAndNewlines)]) } }
    private var appearance: some View {
        VStack(spacing: 0) {
            SettingsRow(title: m.t("settings.theme")) {
                Picker(m.t("settings.theme"), selection: preference("theme")) { ForEach(Choices.themes, id: \.0) { value, key in Text(m.t(key)).tag(value) } }.pickerStyle(.segmented).labelsHidden()
            }
            SettingsRow(title: m.t("settings.accent"), hint: m.t("settings.accent_hint")) {
                HStack(spacing: 10) { ForEach(Choices.accents, id: \.0) { color, key in Button { m.run { try await m.savePreferences(["accent": color]) } } label: { Circle().fill(accent(color)).frame(width: 26, height: 26).overlay { if m.preferences["accent"].text == color { Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundStyle(.white) } } }.buttonStyle(.plain).accessibilityLabel(m.t(key)).help(m.t(key)) } }
            }
            SettingsRow(title: m.t("settings.font_size")) {
                Picker(m.t("settings.font_size"), selection: preference("font")) { ForEach(Choices.fonts, id: \.0) { value, key in Text(m.t(key)).tag(value) } }.pickerStyle(.segmented).labelsHidden()
            }
            SettingsRow(title: m.t("settings.density")) {
                Picker(m.t("settings.density"), selection: preference("density")) { ForEach(Choices.densities, id: \.0) { value, key in Text(m.t(key)).tag(value) } }.pickerStyle(.segmented).labelsHidden()
            }
        }
    }
    private var language: some View {
        VStack(spacing: 0) {
            SettingsRow(title: m.t("settings.language.label"), hint: m.t("settings.language.hint")) {
                VStack(alignment: .trailing, spacing: 8) {
                    Picker(m.t("settings.language.label"), selection: Binding(get: { m.words.language }, set: { value in m.run { try await m.saveSettings(language: value, notify: m.preferences["notify"].flag) } })) { Rows(m.words.languages) { Text($0["name"].text).tag($0["code"].text) } }.labelsHidden()
                    Button(m.t("settings.language.system", ["lang": m.words.languages.first(where: { $0["code"].text == Words.normalize(Locale.current.identifier) })?["name"].text ?? Words.normalize(Locale.current.identifier)])) { m.run { try await m.savePreferences(["lang": Words.normalize(Locale.current.identifier)]) } }.font(.system(size: 11.5)).buttonStyle(.link)
                }
            }
            SettingsRow(title: m.t("settings.auto_names.label"), hint: m.t("settings.auto_names.hint")) { Toggle(m.t("settings.auto_names.label"), isOn: toggle("auto_names")).toggleStyle(.switch).labelsHidden() }
        }
    }
    private var voice: some View {
        VStack(alignment: .leading, spacing: 0) {
            SettingsRow(title: m.t("common.voice_input"), hint: m.t("settings.voice_hint")) {
                Picker(m.t("common.voice_input"), selection: preference("voice")) { Text(m.t("native.speech")).tag("browser"); Text(m.t("settings.voice_off")).tag("off") }.labelsHidden()
            }
            SettingsRow(title: m.t("settings.voice_try")) {
                HStack(alignment: .bottom) {
                    TextField(m.t("settings.voice_try_here"), text: $voiceTest, axis: .vertical).textFieldStyle(.plain).labelsHidden().lineLimit(3...6)
                    VoiceButton(text: $voiceTest).labelStyle(.iconOnly)
                }.padding(9).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.border))
            }
            Text(m.t("settings.voice_mac")).font(.system(size: 12)).foregroundStyle(RelicStyle.muted).fixedSize(horizontal: false, vertical: true).padding(.top, 14)
        }
    }
    private var notifications: some View {
        VStack(spacing: 0) {
            SettingsRow(title: m.t("settings.desktop_notify"), hint: m.t("settings.desktop_notify_hint")) {
                Toggle(m.t("settings.desktop_notify"), isOn: Binding(get: { m.preferences["notify"].flag }, set: { value in m.run { try await m.saveSettings(language: m.words.language, notify: value) } })).toggleStyle(.switch).labelsHidden()
            }
            SettingsRow(title: m.t("settings.notify_test")) { Button(m.t("settings.notify_send_test")) { m.run { try await m.authorizeNotifications(); m.notify(m.t("settings.notify_on")) } } }
        }
    }
    private var about: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Relic · " + m.preferences["version"].text).font(.system(size: 20, weight: .semibold)).padding(.vertical, 10)
            SettingsRow(title: m.t("settings.data_folder"), hint: m.preferences["data"].text) { Button(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "data"]) } } }
            SettingsRow(title: m.t("settings.logs"), hint: m.t("settings.logs_hint")) { Button(m.t("common.open")) { m.run { try await m.post("/api/open", ["what": "logs"]) } } }
            SettingsRow(title: m.t("settings.local_server"), hint: m.t("settings.local_server_hint", ["port": m.preferences["port"].text])) { SmallBadge(text: m.t("settings.connected"), color: RelicStyle.green) }
            Text(m.t("settings.install_app_done")).font(.system(size: 12)).foregroundStyle(RelicStyle.muted).padding(.top, 14)
        }
    }
}

private struct SettingsRow<Content: View>: View {
    let title: String
    var hint = ""
    @ViewBuilder let content: () -> Content
    var body: some View {
        HStack(alignment: .top, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.system(size: 13, weight: .medium))
                if !hint.isEmpty { Text(hint).font(.system(size: 12)).foregroundStyle(RelicStyle.muted).textSelection(.enabled).fixedSize(horizontal: false, vertical: true) }
            }.frame(maxWidth: .infinity, alignment: .leading)
            content().frame(width: 220, alignment: .trailing)
        }.padding(.vertical, 16).frame(maxWidth: .infinity, alignment: .leading).overlay(alignment: .bottom) { RelicStyle.line.frame(height: 1) }
    }
}

struct HarnessSettings: View {
    @EnvironmentObject var m: Model
    @State private var harnesses: [Node] = []
    @State private var paths: [String: String] = [:]
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(m.t("settings.harness_intro")).font(.system(size: 12)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true).padding(.bottom, 8)
            ForEach(["node", "npm"], id: \.self) { id in
                SettingsRow(title: id == "node" ? "Node.js" : "npm", hint: m.t("settings.runtime_path_hint")) { pathRow(id, title: id == "node" ? "Node.js" : "npm") }
            }
            Text(m.t("settings.desktop_connections")).font(.system(size: 15, weight: .semibold)).padding(.top, 22)
            SettingsRow(title: "Codex / ChatGPT", hint: m.platform["desktop_transport"]["reason"].text) { SmallBadge(text: m.t(m.platform["desktop_transport"]["available"].flag ? "settings.connected" : "settings.not_connected"), color: m.platform["desktop_transport"]["available"].flag ? RelicStyle.green : RelicStyle.muted) }
            SettingsRow(title: "Claude Desktop", hint: m.t("settings.claude_desktop_hint")) {
                Toggle("Claude Desktop", isOn: Binding(get: { m.platform["claude_desktop"]["enabled"].flag }, set: { value in m.run { m.platform = try await m.post("/api/platform", ["claude_desktop_enabled": value, "probe": true]) } })).toggleStyle(.switch).labelsHidden()
            }
            SettingsRow(title: m.t("settings.desktop_probe"), hint: m.t("settings.desktop_probe_hint")) { Button(m.t("settings.desktop_probe")) { m.run { m.platform = try await m.post("/api/platform", ["probe": true]) } } }
            VStack(spacing: 10) { Rows(harnesses.filter { !$0["later"].flag }) { harness in
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(harness["available"].flag ? m.t("settings.connected") : harness["problem"].text).font(.system(size: 12)).foregroundStyle(RelicStyle.secondary)
                        SettingsRow(title: m.t("settings.program")) { pathRow(harness["id"].text, title: m.t("settings.program")) }
                        Text(m.t(harness["adapter_installed"].flag ? "settings.adapter_version" : "settings.adapter_missing", ["adapter": harness["adapter"].text, "version": harness["adapter_version"].text])).accessibilityLabel(m.t("settings.adapter"))
                        Text("Node.js · " + (harness["node"].text.isEmpty ? m.t("settings.not_found") : harness["node"].text))
                        Text(m.t("settings.default_mode") + " · " + (harness["mode"].text.isEmpty ? m.t(harness["note"].text.isEmpty ? "settings.adapter_default" : "settings.adapter_default_note", ["note": harness["note"].text]) : harness["mode"].text))
                        Text(m.t("settings.models") + " · " + harness["models"].rows.map(\.text).joined(separator: m.t("settings.models_sep")))
                        Button(m.t(harness["adapter_installed"].flag ? "settings.reinstall_adapter" : "settings.install_adapter")) { m.run { m.installLogs[harness["id"].text] = [harness["install"].text]; try await m.post("/api/harnesses/" + Client.segment(harness["id"].text) + "/install", [:]) } }
                        if let lines = m.installLogs[harness["id"].text] { Text(lines.joined(separator: "\n")).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                    }.font(.system(size: 12)).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 10)
                } label: {
                    HStack { Text(harness["title"].text).font(.system(size: 13, weight: .semibold)); Text(harness["vendor"].text).font(.system(size: 12)).foregroundStyle(RelicStyle.muted); Spacer() }
                }.relicCard()
            } }.padding(.vertical, 16)
            DisclosureGroup(m.t("settings.later")) {
                VStack(alignment: .leading, spacing: 10) {
                    Rows(harnesses.filter { $0["later"].flag }) { Text($0["title"].text + " · " + $0["vendor"].text + " · " + $0["launch"].text) }
                    Text(m.t("settings.later_hint")).foregroundStyle(RelicStyle.muted)
                }.font(.system(size: 12)).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
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
