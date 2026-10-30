import SwiftUI

struct NativeRadio: NSViewRepresentable {
    @Binding var selected: Bool
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(radioButtonWithTitle: "", target: context.coordinator, action: #selector(Coordinator.changed(_:)))
        button.contentTintColor = NSColor(RelicStyle.accent)
        updateNSView(button, context: context); return button
    }
    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.parent = self; button.state = selected ? .on : .off; button.isEnabled = enabled
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSButton, context: Context) -> CGSize? { CGSize(width: 13, height: 13) }
    final class Coordinator: NSObject {
        var parent: NativeRadio
        init(_ parent: NativeRadio) { self.parent = parent }
        @objc func changed(_ sender: NSButton) { parent.selected = true }
    }
}

struct NativeCheck: NSViewRepresentable {
    @Binding var checked: Bool
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(checkboxWithTitle: "", target: context.coordinator, action: #selector(Coordinator.changed(_:)))
        button.contentTintColor = NSColor(RelicStyle.accent)
        updateNSView(button, context: context); return button
    }
    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.parent = self; button.state = checked ? .on : .off; button.isEnabled = enabled
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSButton, context: Context) -> CGSize? { CGSize(width: 13, height: 13) }
    final class Coordinator: NSObject {
        var parent: NativeCheck
        init(_ parent: NativeCheck) { self.parent = parent }
        @objc func changed(_ sender: NSButton) { parent.checked = sender.state == .on }
    }
}

struct SettingsNavigationButton: View {
    let title: String, icon: String
    let selected: Bool
    let action: () -> Void
    @State private var hovered = false
    @State private var identity = "relic-tab/settings/" + UUID().uuidString
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                ReferenceIcon(name: icon, size: 16, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary)
                ReferenceLabel(title, weight: selected ? 600 : 400, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary, owner: identity)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.padding(.horizontal, 10).frame(height: 34)
                .modifier(RecordedSurface(background: selected ? RelicStyle.selected : hovered ? RelicStyle.hover : .clear, radius: 8, hovered: hovered, selected: selected))
        }.buttonStyle(.plain).onHover { hovered = $0 }.accessibilityIdentifier(identity).accessibilityLabel(title).help(title)
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct SettingsSegments: View {
    let options: [(String, String)]
    @Binding var selection: String
    var body: some View {
        HStack(spacing: 2) {
            ForEach(options, id: \.0) { value, title in
                TextButton(title, size: 12, weight: 400, color: value == selection ? RelicStyle.ink : RelicStyle.secondary, height: 23.2, padding: 9) { selection = value }
                    .buttonStyle(.plain)
                    .modifier(RecordedSurface(background: value == selection ? RelicStyle.card : .clear, radius: 6, shadows: value == selection ? SurfaceShadow.small : [], selected: value == selection))
                    .accessibilityAddTraits(value == selection ? .isSelected : [])
            }
        }.padding(2).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "region"))
    }
}

struct SettingsSwatch: View {
    let name: String
    let selected: Bool
    let action: () -> Void
    // The reference swatches keep their fixed colors in either appearance.
    private var color: Color { let rgb: UInt32 = ["clay": 0xC8643F, "ink": 0x3A3936, "indigo": 0x5B61D6, "blue": 0x2F6BD8, "rose": 0xC4456C, "amber": 0xB9821D][name] ?? 0xC8643F; return RelicStyle.color(rgb, rgb) }
    var body: some View {
        Button(action: action) {
            Color.clear.frame(width: 24, height: 24).modifier(RecordedSurface(background: color, radius: 12))
                .overlay { if selected { Circle().strokeBorder(RelicStyle.background, lineWidth: 2).frame(width: 28, height: 28); Circle().strokeBorder(RelicStyle.ink, lineWidth: 2).frame(width: 32, height: 32) } }
        }.buttonStyle(.plain).help(name).accessibilityLabel(name).accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct ReferenceInput: View {
    @Environment(\.nativeControlColor) private var textColor
    let placeholder: String
    @Binding var text: String
    var commit: () -> Void = {}
    var height: CGFloat = 38.4
    var pointSize: CGFloat = 14
    var monospaced = false
    var voice = true
    var suggestions: [String] = []
    var controlID = ""
    @State private var suggestionAnchor = CGRect.zero
    @FocusState private var focused: Bool
    @State private var identity = "relic-input/" + UUID().uuidString
    @EnvironmentObject var m: Model
    private var inputIdentity: String { controlID.isEmpty ? identity : "relic-input/" + controlID }
    var body: some View {
        TextField(placeholder, text: $text, prompt: Text(placeholder).foregroundStyle(RelicStyle.placeholder)).textFieldStyle(.plain).font(monospaced ? Font(RelicStyle.monoFont(pointSize)) : RelicStyle.font(pointSize, weight: 400)).foregroundStyle(textColor)
            .accessibilityIdentifier(inputIdentity)
            .focused($focused).onSubmit { focused = false }
            .onKeyPress(.downArrow) {
                guard !suggestions.isEmpty else { return .ignored }
                if m.inputSuggestions?.id == inputIdentity { m.inputSuggestions?.move(1) } else { openSuggestions() }
                return .handled
            }
            .onKeyPress(.upArrow) { guard m.inputSuggestions?.id == inputIdentity else { return .ignored }; m.inputSuggestions?.move(-1); return .handled }
            .onKeyPress(.return) {
                guard let menu = m.inputSuggestions, menu.id == inputIdentity, menu.values.indices.contains(menu.selected) else { return .ignored }
                menu.choose(menu.values[menu.selected]); m.inputSuggestions = nil; return .handled
            }
            .onKeyPress(.escape) { guard m.inputSuggestions?.id == inputIdentity else { return .ignored }; m.inputSuggestions = nil; return .handled }
            .onChange(of: focused) { old, new in if old && !new { closeSuggestions(); commit() } }
            .onChange(of: text) { if m.inputSuggestions?.id == inputIdentity { openSuggestions() } }
            .padding(.leading, 10).padding(.trailing, !voice || m.preferences["voice"].text == "off" ? 10 : 35).frame(height: height)
            .modifier(RecordedSurface(background: RelicStyle.background, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.55) : RelicStyle.border, borderWidth: 1, radius: 9, owner: inputIdentity))
            .overlay(alignment: .trailing) { if voice && m.preferences["voice"].text != "off" { VoiceButton(text: $text).padding(.trailing, 5) } }
            .background(GeometryReader { proxy in Color.clear.preference(key: InputSuggestionAnchor.self, value: proxy.frame(in: .named("relic-window"))) })
            .onPreferenceChange(InputSuggestionAnchor.self) { suggestionAnchor = $0 }
            .onDisappear { closeSuggestions() }
    }
    private func closeSuggestions() { if m.inputSuggestions?.id == inputIdentity { m.inputSuggestions = nil } }
    private func openSuggestions() {
        let values = suggestions.filter { text.isEmpty || $0.localizedCaseInsensitiveContains(text) }
        guard !values.isEmpty else { closeSuggestions(); return }
        m.inputSuggestions = InputSuggestionsState(id: inputIdentity, controlID: controlID, anchor: suggestionAnchor, values: values) { value in
            text = value; m.inputSuggestions = nil; commit()
        }
    }
}
