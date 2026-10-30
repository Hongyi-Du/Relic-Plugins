import SwiftUI
import RelicCore

// The inspector uses the reference's compact blocks. All drawing remains native.
struct OverviewBlock<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) { content }
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
        ReferenceLabel(text, size: 11.5, color: foreground, lineHeight: 20, owner: identity).fixedSize()
            .frame(height: 20).padding(.horizontal, 8).padding(.vertical, 1)
            .modifier(RecordedSurface(background: background, radius: 10, kind: "chip", owner: identity))
            .accessibilityElement(children: .ignore).accessibilityLabel(text).accessibilityIdentifier(identity)
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
                .padding(.horizontal, small ? 9 : 13).frame(height: small ? 26 : 32)
                .modifier(RecordedSurface(background: primary ? RelicStyle.ink : hovered || configuration.isPressed ? RelicStyle.hover : ghost ? .clear : RelicStyle.card,
                    border: primary ? RelicStyle.ink : ghost ? .clear : RelicStyle.border, borderWidth: 1, radius: small ? 7 : 9, hovered: hovered))
                .recordedOpacity(enabled ? 1 : 0.45).onHover { hovered = $0 }
        }
    }
}

struct OverviewLink: View {
    let text: String
    var icon = "chev"
    var leading = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if leading { ReferenceIcon(name: icon, size: icon == "plus" ? 13 : 12, color: RelicStyle.muted) }
                Text(text).font(RelicStyle.font(12, weight: 400))
                if !leading && !icon.isEmpty { ReferenceIcon(name: icon, size: 12, color: RelicStyle.muted) }
            }.foregroundStyle(RelicStyle.muted).frame(minHeight: 19.2)
        }.buttonStyle(.plain)
    }
}

struct OverviewToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: 8) {
                Circle().fill(.white).frame(width: 14, height: 14)
                    .shadow(color: .black.opacity(0.25), radius: 1, x: 0, y: 1)
                    .frame(width: 28, alignment: configuration.isOn ? .trailing : .leading).padding(2)
                    .modifier(RecordedSurface(background: configuration.isOn ? RelicStyle.accent : RelicStyle.border, radius: 9))
                configuration.label.font(RelicStyle.font(12.5, weight: 400)).foregroundStyle(RelicStyle.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }.buttonStyle(.plain).accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }.toggleStyle(.checkbox).accessibilityIdentifier("relic-toggle")
        }
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
    @ViewBuilder var leading: Leading
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: 9) {
            leading
            VStack(alignment: .leading, spacing: 0) {
                Text(title).font(RelicStyle.font(13, weight: 600)).strikethrough(struck).lineLimit(1).frame(minHeight: 20.8)
                Text(subtitle).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.muted).lineLimit(1).frame(minHeight: 19.2)
            }.frame(maxWidth: .infinity, alignment: .leading)
            trailing
        }.padding(.horizontal, 8).padding(.vertical, 6).padding(.horizontal, -8)
            .accessibilityElement(children: .contain)
    }
}
