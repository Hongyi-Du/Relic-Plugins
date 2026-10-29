import SwiftUI

struct SettingsToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            Circle().fill(.white).frame(width: 14, height: 14)
                .shadow(color: .black.opacity(0.25), radius: 1, x: 0, y: 1)
                .frame(width: 28, alignment: configuration.isOn ? .trailing : .leading).padding(2)
                .modifier(RecordedSurface(background: configuration.isOn ? RelicStyle.accent : RelicStyle.border, radius: 9))
        }.buttonStyle(.plain).accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }.toggleStyle(.checkbox).accessibilityIdentifier("relic-toggle")
        }
    }
}

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

struct SettingsNavigationButton: View {
    let title: String, icon: String
    let selected: Bool
    let action: () -> Void
    @State private var hovered = false
    @State private var identity = "relic-text-button/" + UUID().uuidString
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                ReferenceIcon(name: icon, size: 16, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary)
                ReferenceLabel(title, weight: selected ? 600 : 400, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary, owner: identity)
                Spacer(minLength: 0)
            }.padding(.horizontal, 10).frame(height: 34)
                .modifier(RecordedSurface(background: selected ? RelicStyle.selected : hovered ? RelicStyle.hover : .clear, radius: 8, hovered: hovered, selected: selected))
        }.buttonStyle(.plain).onHover { hovered = $0 }.accessibilityIdentifier(identity).accessibilityLabel(title)
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
    let placeholder: String
    @Binding var text: String
    var commit: () -> Void = {}
    var height: CGFloat = 38.4
    var pointSize: CGFloat = 14
    var monospaced = false
    var voice = true
    var suggestions: [String] = []
    @State private var showingSuggestions = false
    @FocusState private var focused: Bool
    @State private var identity = "relic-input/" + UUID().uuidString
    @EnvironmentObject var m: Model
    var body: some View {
        TextField(placeholder, text: $text).textFieldStyle(.plain).font(monospaced ? Font(RelicStyle.monoFont(pointSize)) : RelicStyle.font(pointSize, weight: 400))
            .accessibilityIdentifier(identity)
            .focused($focused).onSubmit { focused = false }
            .onKeyPress(.downArrow) {
                guard !suggestions.isEmpty else { return .ignored }
                showingSuggestions = true; return .handled
            }
            .onChange(of: focused) { old, new in if old && !new { commit() } }
            .padding(.leading, 10).padding(.trailing, !voice || m.preferences["voice"].text == "off" ? 10 : 35).frame(height: height)
            .modifier(RecordedSurface(background: RelicStyle.background, border: focused ? RelicStyle.accent : RelicStyle.border, borderWidth: 1, radius: 9, owner: identity))
            .overlay(alignment: .trailing) { if voice && m.preferences["voice"].text != "off" { VoiceButton(text: $text).padding(.trailing, 5) } }
            .popover(isPresented: $showingSuggestions, arrowEdge: .bottom) {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(suggestions.filter { text.isEmpty || $0.localizedCaseInsensitiveContains(text) }, id: \.self) { value in
                        TextButton(value, weight: 400, height: 28, padding: 10) { text = value; showingSuggestions = false; commit() }.buttonStyle(QuietButtonStyle())
                    }
                }.padding(4).background(RelicStyle.card)
            }
    }
}
