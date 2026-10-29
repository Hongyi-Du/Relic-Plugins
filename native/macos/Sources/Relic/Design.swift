import SwiftUI
import AppKit
import CoreText

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
    static let faint = color(0xB8B5AF, 0x5F5D58)
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
    static let redSoft = color(0xFBEAE6, 0x3D2622)
    static let red = color(0xC2412D, 0xEE8A78)
    static func mix(_ first: Color, _ second: Color, fraction: CGFloat) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            var result = NSColor.clear
            appearance.performAsCurrentDrawingAppearance {
                let a = NSColor(first).usingColorSpace(.sRGB) ?? .clear
                let b = NSColor(second).usingColorSpace(.sRGB) ?? .clear
                result = NSColor(srgbRed: a.redComponent * fraction + b.redComponent * (1 - fraction), green: a.greenComponent * fraction + b.greenComponent * (1 - fraction), blue: a.blueComponent * fraction + b.blueComponent * (1 - fraction), alpha: a.alphaComponent * fraction + b.alphaComponent * (1 - fraction))
            }
            return result
        })
    }
    static func font(_ size: CGFloat, weight: Int) -> Font {
        Font(nativeFont(size, weight: weight))
    }
    static func monoFont(_ size: CGFloat) -> NSFont {
        NSFont(name: "Menlo-Regular", size: size) ?? NSFont.monospacedSystemFont(ofSize: size, weight: .regular)
    }
    static func nativeFont(_ size: CGFloat, weight: Int) -> NSFont {
        // app.css reaches PingFang SC on macOS after the Windows-only faces.
        // Select its real installed face, including the CSS 500/550 boundary.
        let face = weight >= 550 ? "Semibold" : weight >= 500 ? "Medium" : weight >= 400 ? "Regular" : weight >= 300 ? "Light" : weight >= 200 ? "Ultralight" : "Thin"
        if let font = NSFont(name: "PingFangSC-" + face, size: size) {
            // PingFangUI resolves to a variable font on current macOS. The same
            // PostScript face has different advances without optical sizing;
            // use its public automatic optical-size setting, as the reference does.
            let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontOpticalSizeAttribute: "auto"] as CFDictionary)
            return CTFontCreateCopyWithAttributes(font as CTFont, size, nil, descriptor) as NSFont
        }
        let points: [(Int, CGFloat)] = [(100, -0.8), (200, -0.6), (300, -0.4), (400, 0), (500, 0.23), (600, 0.3), (700, 0.4), (800, 0.56), (900, 0.62)]
        var value = CGFloat.zero
        for index in 1..<points.count where weight >= points[index - 1].0 && weight <= points[index].0 {
            let a = points[index - 1], b = points[index]
            value = a.1 + CGFloat(weight - a.0) / CGFloat(b.0 - a.0) * (b.1 - a.1); break
        }
        return NSFont.systemFont(ofSize: size, weight: NSFont.Weight(rawValue: value))
    }
    static func avatar(_ id: String, background: Bool, dark: Bool) -> Color {
        // app.js hue() hashes Unicode code points with unsigned 32-bit overflow.
        let hash = id.unicodeScalars.reduce(UInt32(7)) { ($0 &* 31) &+ $1.value }
        let hues = [18, 30, 42, 205, 222, 248, 272, 300, 330, 350, 190, 12]
        let hue = Double(hues[Int(hash % UInt32(hues.count))]) / 360
        let saturation: Double = background ? (dark ? 0.18 : 0.40) : (dark ? 0.45 : 0.38)
        let lightness: Double = background ? (dark ? 0.24 : 0.90) : (dark ? 0.78 : 0.34)
        let value = lightness + saturation * min(lightness, 1 - lightness)
        return Color(hue: hue, saturation: value == 0 ? 0 : 2 * (1 - lightness / value), brightness: value)
    }
    static func state(_ value: String) -> Color {
        switch value { case "working", "running": return green; case "active": return mix(green, faint, fraction: 0.55); case "waiting", "starting", "blocked": return amber; case "error", "failed": return red; default: return muted }
    }
}

struct QuietButtonStyle: ButtonStyle {
    var selected = false
    var selectionApplicable = false
    func makeBody(configuration: Configuration) -> some View {
        QuietBody(configuration: configuration, selected: selected, selectionApplicable: selectionApplicable)
    }
    private struct QuietBody: View {
        let configuration: Configuration
        let selected: Bool
        let selectionApplicable: Bool
        @State private var hovering = false
        @Environment(\.isEnabled) private var enabled
        var body: some View {
            configuration.label.contentShape(RoundedRectangle(cornerRadius: 7))
                .modifier(RecordedSurface(background: selected ? RelicStyle.selected : hovering || configuration.isPressed ? RelicStyle.hover : .clear, radius: 7, hovered: hovering, selected: selectionApplicable ? selected : nil))
                .foregroundStyle(enabled ? RelicStyle.ink : RelicStyle.faint).onHover { hovering = $0 }
        }
    }
}

struct IconButton: View {
    let title: String
    let icon: String
    var selected = false
    var badge = 0
    var size: CGFloat = 18
    var height: CGFloat = 30
    var width: CGFloat = 30
    @Environment(\.isEnabled) private var enabled
    @State private var identity = "relic-icon-button/" + UUID().uuidString
    let action: () -> Void
    var body: some View {
        Button(action: action) { ReferenceIcon(name: icon, size: size, color: !enabled ? RelicStyle.faint : selected ? RelicStyle.ink : RelicStyle.secondary, owner: identity).frame(width: width, height: height) }
            .buttonStyle(QuietButtonStyle(selected: selected)).foregroundStyle(RelicStyle.secondary)
            .help(title).accessibilityLabel(title).accessibilityIdentifier(identity)
            .overlay(alignment: .topTrailing) { if badge > 0 { Text(String(badge)).font(RelicStyle.font(10, weight: 700)).foregroundStyle(.white).padding(.horizontal, 4).frame(minWidth: 15, minHeight: 15).background(RelicStyle.red, in: RoundedRectangle(cornerRadius: 8)).allowsHitTesting(false) } }
    }
}

struct RelicLogo: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 15).fill(LinearGradient(colors: [Color(red: 46/255, green: 44/255, blue: 41/255), Color(red: 27/255, green: 26/255, blue: 24/255)], startPoint: .top, endPoint: .bottom))
            if let path = try? VectorPath.parse("M21 47V17h12.8c6.4 0 10.2 3.5 10.2 8.9 0 4.2-2.3 7.2-6.2 8.3L45 47h-7.6l-6.4-12.1H27.9V47H21zm6.9-17.8h5.9c2.8 0 4.3-1.3 4.3-3.6s-1.5-3.6-4.3-3.6h-5.9v7.2z") { Path(path).fill(.white) }
            Circle().fill(Color(red: 217/255, green: 119/255, blue: 87/255)).frame(width: 8.4, height: 8.4).position(x: 47.5, y: 46.5)
        }.frame(width: 64, height: 64).scaleEffect(18/64).frame(width: 18, height: 18).accessibilityHidden(true)
    }
}

struct ChipButton: View {
    let title: String
    let help: String
    let icon: String
    var selected = false
    let action: () -> Void
    @State private var hovered = false
    @State private var identity = "relic-chip-button/" + UUID().uuidString
    private var color: Color { selected ? RelicStyle.violet : hovered ? RelicStyle.ink : RelicStyle.secondary }
    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) { ReferenceIcon(name: icon, size: 15, color: color, owner: identity); ReferenceLabel(title, size: 12.5, color: color, owner: identity) }
                .foregroundStyle(color).padding(.horizontal, 11).frame(height: 28)
                .modifier(RecordedSurface(background: selected ? RelicStyle.violetSoft : hovered ? RelicStyle.hover : RelicStyle.card,
                    border: selected ? RelicStyle.violet.opacity(0.45) : RelicStyle.border, borderWidth: 1, radius: 14, owner: identity, hovered: hovered))
        }.buttonStyle(.plain).help(help).onHover { hovered = $0 }
            .accessibilityIdentifier(identity).accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}

struct SmallBadge: View {
    let text: String
    var color: Color = RelicStyle.secondary
    var body: some View { Text(text).font(RelicStyle.font(10.5, weight: 600)).lineLimit(1).padding(.horizontal, 6).padding(.vertical, 2).foregroundStyle(color).background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 5)).help(text) }
}

struct StateDot: View {
    let state: String
    let border: Color
    var body: some View {
        Color.clear.frame(width: 10, height: 10)
            .modifier(RecordedSurface(background: state == "vacant" ? .clear : RelicStyle.state(state), border: border, borderWidth: 2, radius: 5, kind: "state-dot", insetRingWidth: state == "vacant" ? 1.5 : 0, insetRingColor: RelicStyle.faint))
    }
}

extension View {
    func relicCard(_ color: Color = RelicStyle.card) -> some View {
        padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: color, border: RelicStyle.line, borderWidth: 1, radius: 12, kind: "card"))
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
