import SwiftUI
import RelicCore

// The inspector uses the reference's compact blocks. All drawing remains native.
struct OverviewBlock<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        LazyVStack(alignment: .leading, spacing: 8) { content }
            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16).padding(.vertical, 14).padding(.bottom, 1)
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card"))
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 6
    var centerRows = false
    var rowAlignment: HorizontalAlignment = .leading
    private func positions(_ subviews: Subviews, width: CGFloat) -> (points: [CGPoint], sizes: [CGSize], size: CGSize) {
        var points: [CGPoint] = [], x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, maxX: CGFloat = 0
        var sizes: [CGSize] = [], rowStart = 0
        var rows: [(Range<Int>, CGFloat)] = []
        func finishRow() {
            if rowStart < points.count { rows.append((rowStart..<points.count, points.last!.x + sizes.last!.width)) }
            if centerRows { for index in rowStart..<points.count { points[index].y += (line - sizes[index].height) / 2 } }
            rowStart = points.count
        }
        for view in subviews {
            let intrinsic = view.sizeThatFits(.unspecified)
            let size = intrinsic.width > width ? view.sizeThatFits(ProposedViewSize(width: width, height: nil)) : intrinsic
            if x > 0 && x + size.width > width { finishRow(); y += line + spacing; x = 0; line = 0 }
            points.append(CGPoint(x: x, y: y)); sizes.append(size); maxX = max(maxX, x + size.width)
            x += size.width + spacing; line = max(line, size.height)
        }
        finishRow()
        if rowAlignment == .trailing {
            for (range, rowWidth) in rows { for index in range { points[index].x += maxX - rowWidth } }
        }
        return (points, sizes, CGSize(width: maxX, height: y + line))
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        positions(subviews, width: proposal.width ?? .infinity).size
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = positions(subviews, width: bounds.width)
        for (index, view) in subviews.enumerated() { view.place(at: CGPoint(x: bounds.minX + result.points[index].x, y: bounds.minY + result.points[index].y), proposal: ProposedViewSize(result.sizes[index])) }
    }
}

struct OverviewChip: View {
    let text: String
    var tone = ""
    @State private var identity = "relic-chip/" + UUID().uuidString
    private var foreground: Color {
        switch tone { case "ok": return RelicStyle.green; case "warn": return RelicStyle.amber; case "bad": return RelicStyle.red; case "sec": return RelicStyle.violet; case "accent": return RelicStyle.accent; default: return RelicStyle.secondary }
    }
    private var background: Color {
        switch tone { case "ok": return RelicStyle.green.opacity(0.14); case "warn": return RelicStyle.amberSoft; case "bad": return RelicStyle.redSoft; case "sec": return RelicStyle.violetSoft; case "accent": return RelicStyle.accent.opacity(0.13); default: return RelicStyle.hover }
    }
    var body: some View {
        ReferenceLabel(text, size: 11.5, color: foreground, lineHeight: 20, owner: identity, truncates: false).fixedSize()
            .frame(height: 20).padding(.horizontal, 8).padding(.vertical, 1)
            .modifier(RecordedSurface(background: background, radius: 10, kind: "chip", owner: identity))
            .accessibilityElement(children: .contain).accessibilityLabel("").accessibilityIdentifier(identity)
    }
}

struct ReferenceButtonStyle: ButtonStyle {
    var primary = false
    var small = false
    var danger = false
    var ghost = false
    func makeBody(configuration: Configuration) -> some View {
        StyledButton(configuration: configuration, primary: primary, small: small, danger: danger, ghost: ghost)
    }
    private struct StyledButton: View {
        let configuration: Configuration
        let primary: Bool, small: Bool, danger: Bool, ghost: Bool
        @Environment(\.isEnabled) private var enabled
        @State private var hovered = false
        var body: some View {
            configuration.label.font(RelicStyle.font(small ? 12 : 13, weight: 600))
                .foregroundStyle(primary ? RelicStyle.background : danger ? RelicStyle.red : RelicStyle.ink)
                // CSS border-box includes one painted border on each side in
                // addition to the 9/13px content padding.
                .padding(.horizontal, small ? 10 : 14).frame(height: small ? 26 : 32)
                .modifier(RecordedSurface(background: primary ? RelicStyle.ink : hovered || configuration.isPressed ? RelicStyle.hover : ghost ? .clear : RelicStyle.card,
                    border: primary ? RelicStyle.ink : ghost ? .clear : RelicStyle.border, borderWidth: 1, radius: small ? 7 : 9, hovered: hovered))
                .recordedOpacity(enabled ? 1 : 0.45).onHover { hovered = $0 }
        }
    }
}

/// The same native TextKit label is used for sizing, drawing and accessibility
/// evidence. A compound SwiftUI Button otherwise hides its text renderer.
struct ReferenceActionButton: View {
    let title: String
    var primary = false
    var small = false
    var danger = false
    var ghost = false
    let action: () -> Void
    init(_ title: String, primary: Bool = false, small: Bool = false, danger: Bool = false, ghost: Bool = false, action: @escaping () -> Void) {
        self.title = title; self.primary = primary; self.small = small
        self.danger = danger; self.ghost = ghost; self.action = action
    }
    var body: some View {
        TextButton(title, size: small ? 12 : 13, weight: 600,
                   color: primary ? RelicStyle.background : danger ? RelicStyle.red : RelicStyle.ink,
                   action: action)
            .buttonStyle(ReferenceButtonStyle(primary: primary, small: small, danger: danger, ghost: ghost))
    }
}

struct OverviewLink: View {
    let text: String
    var icon = "chev"
    var leading = false
    let action: () -> Void
    @State private var hovered = false
    @State private var identity = "relic-text-button/overview-link/" + UUID().uuidString
    private var color: Color { hovered ? RelicStyle.accent : RelicStyle.muted }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if leading { ReferenceIcon(name: icon, size: icon == "plus" ? 13 : 12, color: color, owner: identity) }
                ReferenceLabel(text, size: 12, color: color, lines: 0, owner: identity)
                if !leading && !icon.isEmpty { ReferenceIcon(name: icon, size: 12, color: color, owner: identity) }
            }.frame(minHeight: 19.2)
                .modifier(RecordedSurface(background: .clear, owner: identity, hovered: hovered))
        }.buttonStyle(.plain).onHover { hovered = $0 }
            .accessibilityIdentifier(identity).accessibilityLabel(text)
    }
}

struct OverviewPicker: View {
    let title: String
    @Binding var selection: String
    let options: [(String, String)]
    var body: some View {
        HStack(spacing: 10) {
            ReferenceLabel(title, size: 12.5, color: RelicStyle.secondary).fixedSize()
            ReferenceSelectField(title: title, selection: $selection, options: options)
        }
    }
}

struct OverviewRow<Leading: View, Trailing: View>: View {
    let title: String, subtitle: String
    var struck = false
    var owner: String? = nil
    @ViewBuilder var leading: Leading
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: 9) {
            leading
            VStack(alignment: .leading, spacing: 0) {
                ReferenceLabel(title, size: 13, weight: 600, owner: owner, struck: struck).frame(minHeight: 20.8)
                ReferenceLabel(subtitle, size: 12, color: RelicStyle.muted, owner: owner).frame(minHeight: 19.2)
            }.frame(maxWidth: .infinity, alignment: .leading)
            trailing
        }.padding(.horizontal, 8).padding(.vertical, 6).padding(.horizontal, -8)
            .accessibilityElement(children: .contain)
    }
}
