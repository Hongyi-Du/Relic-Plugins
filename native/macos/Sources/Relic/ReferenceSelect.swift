import AppKit
import SwiftUI

// A real AppKit popup owns its selected value, keyboard navigation and menu.
// Its accessibility value is the current option, distinct from the field label.
struct ReferenceSelect: NSViewRepresentable {
    @Environment(\.nativeControlColor) private var textColor
    let title: String
    @Binding var selection: String
    let options: [(String, String)]
    var pointSize: CGFloat = 14
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSPopUpButton {
        let view = NSPopUpButton(frame: .zero, pullsDown: false)
        view.isBordered = false; view.font = RelicStyle.nativeFont(pointSize, weight: 400)
        view.target = context.coordinator; view.action = #selector(Coordinator.changed(_:))
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: NSPopUpButton, context: Context) {
        context.coordinator.parent = self
        view.font = RelicStyle.nativeFont(pointSize, weight: 400)
        if view.itemTitles != options.map(\.1) {
            view.removeAllItems()
            for (index, option) in options.enumerated() { view.addItem(withTitle: option.1); view.lastItem?.tag = index }
        }
        if let index = options.firstIndex(where: { $0.0 == selection }) { view.selectItem(at: index) }
        view.attributedTitle = NSAttributedString(string: view.title, attributes: [.font: RelicStyle.nativeFont(pointSize, weight: 400), .foregroundColor: NSColor(textColor), .tracking: 0])
        view.setAccessibilityLabel(title); view.setAccessibilityIdentifier("relic-dropdown/" + title)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSPopUpButton, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? nsView.intrinsicContentSize.width, height: pointSize * 1.6)
    }
    final class Coordinator: NSObject {
        var parent: ReferenceSelect
        init(_ parent: ReferenceSelect) { self.parent = parent }
        @objc func changed(_ sender: NSPopUpButton) {
            let index = sender.indexOfSelectedItem
            if parent.options.indices.contains(index) { parent.selection = parent.options[index].0 }
        }
    }
}

struct ReferenceSelectField: View {
    let title: String
    @Binding var selection: String
    let options: [(String, String)]
    var pointSize: CGFloat = 14
    var body: some View {
        ReferenceSelect(title: title, selection: $selection, options: options, pointSize: pointSize).padding(.horizontal, 9).frame(height: pointSize * 1.6 + 16)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 9, owner: "relic-dropdown/" + title))
    }
}
