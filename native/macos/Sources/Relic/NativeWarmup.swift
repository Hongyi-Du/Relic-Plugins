import SwiftUI
import AppKit

/// Shown, invisibly, only while the first organization loads. Creating one
/// native List row with a label and a selectable passage moves AppKit's
/// one-time table, TextKit and font setup into launch, instead of blocking
/// the first chat that appears after the data arrives.
struct NativeWarmup: View {
    var body: some View {
        List {
            ReferenceLabel("Relic 组织 Organization", size: 13.3, weight: 600)
            SelectableText(value: AttributedString("原生界面准备中。 Preparing native text."), pointSize: 14, lineHeight: 23.1)
        }
        .listStyle(.plain)
        .frame(width: 360, height: 120)
        .opacity(0)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .onAppear { TextRenderingWarmup.draw() }
    }
}

/// Draws a few passages of message text once, offscreen, at launch, through
/// the text view, layout manager and styles a message's body uses. In CI the
/// person-shape profile's first message row held its display update for
/// 184-369 ms while its layout took 10-15 ms of it: the rest went to Core
/// Animation's commit, where layer-backed views draw, for text drawn there
/// for the first time (runs 41733608162, 41736953859, 41738519218). The warm
/// list above is transparent; these passages are drawn into bitmaps at 1x
/// and the screen's scale, so fonts, CJK fallback and glyphs are first used
/// here, before any data arrives.
@MainActor enum TextRenderingWarmup {
    private static var drawn = false
    static func draw() {
        guard !drawn else { return }
        drawn = true
        let trace = UIWorkTrace.begin("warmup.text"); defer { UIWorkTrace.end(trace) }
        let source = "原生界面准备中，正在载入组织与消息。 Preparing the native interface: **重点 strong**, *强调 emphasis*, `代码 inline code` and [链接 link](https://example.invalid/relic)."
        let inline = (try? AttributedString(markdown: source, options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source)
        let passages = [
            NativeTextStyle.render(inline, size: 14),
            NativeTextStyle.render(AttributedString("交付检查 Delivery check · 响应检查 Response check"), size: 14, weight: .semibold),
            NativeTextStyle.render(AttributedString("for chat in chats:\n    inspect(chat)  # 代码 code"), size: 11.25, lineHeight: 19.375, monospaced: true),
            NativeTextStyle.render(AttributedString("项目 结果 窗口 消息 Table cell"), size: 13.02)
        ]
        let scales = Set([1, NSScreen.main?.backingScaleFactor ?? 2])
        for passage in passages {
            let storage = NSTextStorage(), layout = InlineCodeLayoutManager()
            let container = NSTextContainer(containerSize: NSSize(width: 420, height: CGFloat.greatestFiniteMagnitude))
            container.lineFragmentPadding = 0
            storage.addLayoutManager(layout); layout.addTextContainer(container)
            let view = QuoteTextView(frame: NSRect(x: 0, y: 0, width: 420, height: 96), textContainer: container)
            view.isEditable = false; view.drawsBackground = false; view.textContainerInset = .zero
            view.textStorage?.setAttributedString(passage)
            layout.ensureLayout(for: container)
            for scale in scales {
                guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(420 * scale), pixelsHigh: Int(96 * scale),
                                                    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                                    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { continue }
                bitmap.size = view.bounds.size
                view.cacheDisplay(in: view.bounds, to: bitmap)
            }
        }
    }
}
