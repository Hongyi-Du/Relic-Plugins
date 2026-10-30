import AppKit
import SwiftUI

// A real AppKit popup owns its selected value, keyboard navigation and menu.
// Its accessibility value is the current option, distinct from the field label.
struct ReferenceSelect: NSViewRepresentable {
    @Environment(\.nativeControlColor) private var textColor
    @Environment(\.isEnabled) private var enabled
    let title: String
    @Binding var selection: String
    let options: [(String, String)]
    var pointSize: CGFloat = 14
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> ReferencePopUpButton {
        let view = ReferencePopUpButton(frame: .zero, pullsDown: false)
        view.cell = ReferencePopUpCell(textCell: "", pullsDown: false)
        (view.cell as? NSPopUpButtonCell)?.arrowPosition = .noArrow
        view.isBordered = false; view.font = RelicStyle.nativeFont(pointSize, weight: 400)
        view.target = context.coordinator; view.action = #selector(Coordinator.changed(_:))
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: ReferencePopUpButton, context: Context) {
        context.coordinator.parent = self
        view.font = RelicStyle.nativeFont(pointSize, weight: 400)
        view.isEnabled = enabled; view.arrowColor = NSColor(textColor)
        if view.itemTitles != options.map(\.1) {
            view.removeAllItems()
            for (index, option) in options.enumerated() { view.addItem(withTitle: option.1); view.lastItem?.tag = index }
        }
        if let index = options.firstIndex(where: { $0.0 == selection }) { view.selectItem(at: index) }
        view.attributedTitle = NSAttributedString(string: view.title, attributes: [.font: RelicStyle.nativeFont(pointSize, weight: 400), .foregroundColor: NSColor(textColor), .tracking: 0])
        view.setAccessibilityLabel(title); view.setAccessibilityIdentifier("relic-dropdown/" + title)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: ReferencePopUpButton, context: Context) -> CGSize? {
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

/// Preserve the real AppKit popup's selection, menu and keyboard handling while
/// drawing the reference's single 8x4 downward chevron, with a 2px square-cap
/// stroke. Its frame comes from the production control, never a reference box.
final class ReferencePopUpButton: NSPopUpButton {
    var arrowColor: NSColor = .labelColor { didSet { needsDisplay = true } }
    private(set) var arrowDraw: [String: Any]?
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let center = CGPoint(x: bounds.maxX - 8, y: floor(bounds.midY))
        let direction: CGFloat = isFlipped ? 1 : -1
        let points = [CGPoint(x: center.x - 4, y: center.y - 2 * direction),
                      CGPoint(x: center.x, y: center.y + 2 * direction),
                      CGPoint(x: center.x + 4, y: center.y - 2 * direction)]
        let path = NSBezierPath(); path.move(to: points[0]); path.line(to: points[1]); path.line(to: points[2])
        path.lineWidth = 2; path.lineCapStyle = .butt; path.lineJoinStyle = .miter
        arrowColor.setStroke(); path.stroke()
        if VisualCapture.enabled {
            arrowDraw = ["provider": "production ReferencePopUpButton.draw", "points_local": points.map { ["x": $0.x, "y": $0.y] },
                "line_width": 2, "line_cap": "butt", "line_join": "miter", "color": ElementCapture.rgba(arrowColor),
                "flipped": isFlipped, "draw_returned": true]
        }
    }
}

final class ReferencePopUpCell: NSPopUpButtonCell {
    override func titleRect(forBounds rect: NSRect) -> NSRect {
        super.titleRect(forBounds: NSRect(x: rect.minX, y: rect.minY, width: max(0, rect.width - 16), height: rect.height))
    }
}

struct ReferenceSelectField: View {
    let title: String
    @Binding var selection: String
    let options: [(String, String)]
    var pointSize: CGFloat = 14
    var body: some View {
        ReferenceSelect(title: title, selection: $selection, options: options, pointSize: pointSize).padding(.leading, 9).padding(.trailing, 1).frame(height: pointSize * 1.6 + 16)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 9, owner: "relic-dropdown/" + title))
    }
}
