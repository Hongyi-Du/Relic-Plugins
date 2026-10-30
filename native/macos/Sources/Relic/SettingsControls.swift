import SwiftUI

struct NativeRadio: NSViewRepresentable {
    @Binding var selected: Bool
    var accessibleName = ""
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(radioButtonWithTitle: "", target: context.coordinator, action: #selector(Coordinator.changed(_:)))
        button.contentTintColor = NSColor(RelicStyle.accent)
        updateNSView(button, context: context); return button
    }
    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.parent = self; button.state = selected ? .on : .off; button.isEnabled = enabled
        button.setAccessibilityLabel(accessibleName)
        button.cell?.setAccessibilityLabel(accessibleName)
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
    let key: String
    let title: String, icon: String
    let selected: Bool
    let action: () -> Void
    @State private var hovered = false
    @State private var trace = SettingsNavigationTrace()
    private var identity: String { "relic-tab/settings/" + key }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                ReferenceIcon(name: icon, size: 16, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary)
                ReferenceLabel(title, weight: selected ? 600 : 400, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary, owner: identity)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.padding(.horizontal, 10).frame(height: 34)
                .modifier(RecordedSurface(background: selected ? RelicStyle.selected : hovered ? RelicStyle.hover : .clear, radius: 8, owner: identity, hovered: hovered, selected: selected))
        }.buttonStyle(.plain).onHover { hovered = $0; trace.receivedHover($0) }.accessibilityIdentifier(identity).accessibilityLabel(title).help(title)
            .accessibilityAddTraits(selected ? .isSelected : [])
            .background(SettingsNavigationProbe(key: key, owner: identity, selected: selected, hovered: hovered, trace: trace))
    }
}

struct SettingsSegments: View {
    let options: [(String, String)]
    @Binding var selection: String
    @State private var identity = UUID().uuidString
    var body: some View {
        HStack(spacing: 2) {
            ForEach(options, id: \.0) { value, title in
                TextButton(title, size: 12, weight: 400, color: value == selection ? RelicStyle.ink : RelicStyle.secondary, height: 23.2, padding: 9, identifier: "relic-tab/segment/" + identity + "/" + value) { selection = value }
                    .buttonStyle(.plain)
                    .modifier(RecordedSurface(background: value == selection ? RelicStyle.card : .clear, radius: 6, owner: "relic-tab/segment/" + identity + "/" + value, shadows: value == selection ? SurfaceShadow.small : [], selected: value == selection))
                    .accessibilityAddTraits(value == selection ? .isSelected : [])
            }
        }.padding(2).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "card"))
    }
}

struct SettingsSwatch: View {
    let name: String
    let selected: Bool
    let action: () -> Void
    @State private var identity = "relic-icon-button/swatch/" + UUID().uuidString
    // The reference swatches keep their fixed colors in either appearance.
    private var color: Color { let rgb: UInt32 = ["clay": 0xC8643F, "ink": 0x3A3936, "indigo": 0x5B61D6, "blue": 0x2F6BD8, "rose": 0xC4456C, "amber": 0xB9821D][name] ?? 0xC8643F; return RelicStyle.color(rgb, rgb) }
    var body: some View {
        Button(action: action) {
            Color.clear.frame(width: 24, height: 24)
                .modifier(RecordedSurface(background: color, border: .clear, borderWidth: 2, radius: 12, kind: "icon-button", owner: identity,
                    selected: selected, rings: selected ? [SurfaceRing(width: 2, color: RelicStyle.background), SurfaceRing(width: 4, color: RelicStyle.ink)] : []))
        }.buttonStyle(.plain).help(name).accessibilityIdentifier(identity).accessibilityLabel(name).accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct ReferenceInput: View {
    @Environment(\.nativeControlColor) private var textColor
    @Environment(\.nativeFieldLabel) private var fieldLabel
    @Environment(\.captureRegion) private var region
    let placeholder: String
    @Binding var text: String
    var commit: () -> Void = {}
    var height: CGFloat = 38.4
    var pointSize: CGFloat = 14
    var monospaced = false
    var voice = true
    var suggestions: [String] = []
    var controlID = ""
    var initiallyFocused = false
    @State private var suggestionAnchor = CGRect.zero
    @State private var focused = false
    @State private var identity = "relic-input/" + UUID().uuidString
    @EnvironmentObject var m: Model
    private var inputIdentity: String { controlID.isEmpty ? identity : "relic-input/" + controlID }
    var body: some View {
        ObservedSearchField(placeholder: placeholder,
            accessibleName: fieldLabel.map { $0 + (voice ? " " + m.t("common.voice_input") : "") } ?? placeholder,
            text: $text, focused: $focused,
            configuration: .init(identifier: inputIdentity, region: region, pointSize: pointSize,
                lineHeight: pointSize * 1.6, monospaced: monospaced, color: textColor), command: handleCommand)
            .onChange(of: focused) { old, new in if old && !new { closeSuggestions(); commit() } }
            .onChange(of: text) { if m.inputSuggestions?.id == inputIdentity { openSuggestions() } }
            .padding(.leading, 10).padding(.trailing, !voice || m.preferences["voice"].text == "off" ? 10 : 35).frame(height: height)
            .modifier(RecordedSurface(background: RelicStyle.background, border: focused ? RelicStyle.mix(RelicStyle.accent, RelicStyle.border, fraction: 0.55) : RelicStyle.border, borderWidth: 1, radius: 9, owner: inputIdentity))
            .overlay(alignment: .trailing) { if voice && m.preferences["voice"].text != "off" { VoiceButton(text: $text).padding(.trailing, 5) } }
            .background(GeometryReader { proxy in Color.clear.preference(key: InputSuggestionAnchor.self, value: proxy.frame(in: .named("relic-window"))) })
            .onPreferenceChange(InputSuggestionAnchor.self) { suggestionAnchor = $0 }
            .task { if initiallyFocused { await Task.yield(); focused = true } }
            .onDisappear { closeSuggestions() }
    }
    private func handleCommand(_ command: ObservedSearchField.Command) -> Bool {
        switch command {
        case .down:
            guard !suggestions.isEmpty else { return false }
            if m.inputSuggestions?.id == inputIdentity { m.inputSuggestions?.move(1) } else { openSuggestions() }
        case .up:
            guard m.inputSuggestions?.id == inputIdentity else { return false }
            m.inputSuggestions?.move(-1)
        case .submit:
            if let menu = m.inputSuggestions, menu.id == inputIdentity, menu.values.indices.contains(menu.selected) {
                menu.choose(menu.values[menu.selected]); m.inputSuggestions = nil
            } else { focused = false }
        case .cancel:
            guard m.inputSuggestions?.id == inputIdentity else { return false }
            m.inputSuggestions = nil
        }
        return true
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
