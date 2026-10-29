import SwiftUI
import AppKit

// app.css tokens expressed as native dynamic colors; no secondary vocabulary.
enum RelicStyle {
    static func color(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let hex = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: 1)
        })
    }
    static let background = color(0xFFFFFF, 0x1F1F1E)
    static let sidebar = color(0xF8F7F5, 0x191918)
    static let hover = color(0xEFEEEA, 0x262624)
    static let selected = color(0xE7E5DF, 0x2F2E2B)
    static let ink = color(0x1B1B1A, 0xECEAE5)
    static let secondary = color(0x5A5853, 0xB8B5AE)
    static let muted = color(0x8F8C86, 0x8A877F)
    static let line = color(0xECEAE6, 0x2C2B29)
    static let border = color(0xDEDBD4, 0x3A3936)
    static let bubble = color(0xF4F3F0, 0x2A2A28)
    static let mine = color(0xF8ECE7, 0x473027)
    static let card = color(0xFFFFFF, 0x252523)
    static let code = color(0xF6F5F2, 0x232321)
    static let accent = color(0xC8643F, 0xC8643F)
    static let amber = color(0xB7791F, 0xE2B15A)
    static let amberSoft = color(0xFBF3E2, 0x3A3020)
    static let violet = color(0x7058B8, 0xA894E0)
    static let violetSoft = color(0xEFEBF8, 0x2E2A3D)
    static let green = color(0x3E9B5E, 0x6CC287)
    static let red = color(0xC2412D, 0xEE8A78)
    static func state(_ value: String) -> Color {
        switch value { case "working", "running", "active": return green; case "waiting", "starting", "blocked": return amber; case "error", "failed": return red; default: return muted }
    }
}

struct QuietButtonStyle: ButtonStyle {
    var selected = false
    func makeBody(configuration: Configuration) -> some View {
        QuietBody(configuration: configuration, selected: selected)
    }
    private struct QuietBody: View {
        let configuration: Configuration
        let selected: Bool
        @State private var hovering = false
        @Environment(\.isEnabled) private var enabled
        var body: some View {
            configuration.label.contentShape(RoundedRectangle(cornerRadius: 7))
                .background(selected ? RelicStyle.selected : hovering || configuration.isPressed ? RelicStyle.hover : .clear, in: RoundedRectangle(cornerRadius: 7))
                .opacity(enabled ? 1 : 0.35).onHover { hovering = $0 }
        }
    }
}

struct IconButton: View {
    let title: String
    let icon: String
    var selected = false
    var badge = 0
    let action: () -> Void
    var body: some View {
        Button(action: action) { Image(systemName: icon).font(.system(size: 14, weight: .medium)).frame(width: 30, height: 28) }
            .buttonStyle(QuietButtonStyle(selected: selected)).foregroundStyle(RelicStyle.secondary)
            .overlay(alignment: .topTrailing) { if badge > 0 { Text(String(badge)).font(.system(size: 9, weight: .bold)).foregroundStyle(.white).padding(.horizontal, 3).frame(minWidth: 12, minHeight: 12).background(RelicStyle.accent, in: Capsule()).allowsHitTesting(false) } }
            .help(title).accessibilityLabel(title)
    }
}

struct SmallBadge: View {
    let text: String
    var color: Color = RelicStyle.secondary
    var body: some View { Text(text).font(.system(size: 10.5, weight: .semibold)).lineLimit(1).padding(.horizontal, 6).padding(.vertical, 2).foregroundStyle(color).background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 5)).help(text) }
}

extension View {
    func relicCard(_ color: Color = RelicStyle.card) -> some View {
        padding(12).frame(maxWidth: .infinity, alignment: .leading).background(color, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(RelicStyle.line, lineWidth: 1))
    }
}

// A native sheet retains its window/shadow, while its SwiftUI surface defines
// the reference's corner radius. This also renders faithfully into the CI PNG.
struct SheetSurface: NSViewRepresentable {
    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ view: Probe, context: Context) {}
    final class Probe: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() { window?.isOpaque = false; window?.backgroundColor = .clear; window?.hasShadow = true }
    }
}
