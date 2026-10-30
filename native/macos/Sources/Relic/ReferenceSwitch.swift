import AppKit
import SwiftUI

// A real checkbox owns the 32x18 hit target and AX state. SwiftUI draws its
// track/knob; no synthetic accessibility representation stretches over a label.
struct ReferenceSwitch: View {
    let title: String
    @Binding var isOn: Bool
    var accessibleName: String? = nil
    @State private var identity = "relic-toggle/" + UUID().uuidString
    init(_ title: String, isOn: Binding<Bool>, accessibleName: String? = nil) { self.title = title; _isOn = isOn; self.accessibleName = accessibleName }
    var body: some View {
        Color.clear.frame(width: 14, height: 14)
            .modifier(RecordedSurface(background: .white, radius: 7, kind: "card",
                shadows: [SurfaceShadow(color: .black.opacity(0.25), radius: 1, x: 0, y: 1)]))
            .environment(\.nativeElementParent, identity)
            .frame(width: 28, alignment: isOn ? .trailing : .leading).padding(2)
            .modifier(RecordedSurface(background: isOn ? RelicStyle.accent : RelicStyle.border, radius: 9, owner: identity))
            .overlay { NativeSwitchControl(title: accessibleName ?? title, isOn: $isOn, identity: identity).frame(width: 32, height: 18) }
    }
}

struct ReferenceSwitchRow: View {
    let title: String
    @Binding var isOn: Bool
    @Environment(\.isEnabled) private var enabled
    init(_ title: String, isOn: Binding<Bool>) { self.title = title; _isOn = isOn }
    var body: some View {
        HStack(spacing: 8) {
            ReferenceSwitch(title, isOn: $isOn)
            ReferenceLabel(title, size: 12.5, color: RelicStyle.secondary, lines: 0, accessibleName: "")
                .fixedSize(horizontal: false, vertical: true)
                .onTapGesture { if enabled { isOn.toggle() } }
        }
    }
}

struct NativeSwitchControl: NSViewRepresentable {
    let title: String
    @Binding var isOn: Bool
    let identity: String
    @Environment(\.isEnabled) private var enabled
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    @MainActor static func makeButton() -> NSButton {
        let button = ReferenceSwitchButton(frame: NSRect(x: 0, y: 0, width: 32, height: 18))
        button.cell = NativeSwitchCell(textCell: "")
        button.setButtonType(.switch); button.title = ""; button.isBordered = false
        button.focusRingType = .none
        return button
    }
    func makeNSView(context: Context) -> NSButton {
        let button = Self.makeButton()
        button.target = context.coordinator; button.action = #selector(Coordinator.changed(_:))
        updateNSView(button, context: context); return button
    }
    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.parent = self
        button.state = isOn ? .on : .off; button.isEnabled = enabled
        button.setAccessibilityLabel(title); button.setAccessibilityIdentifier(identity)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSButton, context: Context) -> CGSize? { CGSize(width: 32, height: 18) }
    final class Coordinator: NSObject {
        var parent: NativeSwitchControl
        init(_ parent: NativeSwitchControl) { self.parent = parent }
        @objc func changed(_ sender: NSButton) { parent.isOn = sender.state == .on }
    }
}

final class ReferenceSwitchButton: NSButton {
    // A custom painted cell has no built-in bezel/glyph AX provider. The real
    // control exposes its own role, current native state and full hit frame.
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityChildren() -> [Any]? { [] }
    // Bezel alignment insets otherwise expand a 32x18 SwiftUI proposal to a
    // 36x22 actual view/hit frame, despite the custom empty cell.
    override var alignmentRectInsets: NSEdgeInsets { NSEdgeInsets(top: 0, left: 0, bottom: 0, right: 0) }
    override func accessibilityRole() -> NSAccessibility.Role? { .checkBox }
    override func accessibilityValue() -> Any? { NSNumber(value: state.rawValue) }
    override func isAccessibilityEnabled() -> Bool { isEnabled }
    override func accessibilityFrame() -> NSRect {
        guard let window else { return super.accessibilityFrame() }
        return window.convertToScreen(convert(bounds, to: nil))
    }
    override func accessibilityPerformPress() -> Bool {
        guard isEnabled else { return false }
        performClick(nil); return true
    }
}

private final class NativeSwitchCell: NSButtonCell {
    // All visible paint belongs to the adjacent production track/knob views.
    override func draw(withFrame cellFrame: NSRect, in controlView: NSView) {}
    override func isAccessibilityElement() -> Bool { false }
}
