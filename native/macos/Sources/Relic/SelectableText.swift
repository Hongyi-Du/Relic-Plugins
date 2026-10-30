import SwiftUI
import AppKit
import CoreText

// Native text selection supplies the exact selected passage to the Quote command.
struct SelectedAuthorKey: EnvironmentKey { static let defaultValue = "" }
extension EnvironmentValues {
    var selectedAuthor: String { get { self[SelectedAuthorKey.self] } set { self[SelectedAuthorKey.self] = newValue } }
}

struct SelectableText: NSViewRepresentable {
    @EnvironmentObject var m: Model
    @Environment(\.openURL) private var openURL
    @Environment(\.selectedAuthor) private var author
    @Environment(\.captureOpacity) private var opacity
    @Environment(\.captureRegion) private var region
    let value: AttributedString
    var scale: CGFloat = 1
    var weight: NSFont.Weight = .regular
    var color: Color = RelicStyle.ink
    var pointSize: CGFloat? = nil
    var lineHeight: CGFloat? = nil
    var monospaced = false
    var uniformSource = false
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSTextView {
        let storage = NSTextStorage(), layout = InlineCodeLayoutManager()
        layout.recordDraws = VisualCapture.enabled
        let container = NSTextContainer(containerSize: NSSize(width: 400, height: CGFloat.greatestFiniteMagnitude))
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        let view = QuoteTextView(frame: .zero, textContainer: container)
        view.sourceStorage = storage
        view.isEditable = false; view.isSelectable = true; view.drawsBackground = false
        view.focusRingType = .none
        view.isRichText = true; view.isHorizontallyResizable = false; view.isVerticallyResizable = false
        view.textContainerInset = .zero; view.textContainer?.lineFragmentPadding = 0
        view.textContainer?.widthTracksTextView = true; view.textContainer?.heightTracksTextView = false; view.delegate = context.coordinator
        updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: NSTextView, context: Context) {
        context.coordinator.parent = self
        if let selectable = view as? QuoteTextView {
            selectable.measuredOpacity = opacity
            selectable.productionRegion = region
            selectable.quoteTitle = m.t("common.quote")
            selectable.quote = { text in m.setQuote(text, from: author.isEmpty ? m.t("common.quote") : author) }
        }
        let baseSize: CGFloat = pointSize ?? (m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14) * scale
        let rendered = NativeTextStyle.render(value, size: baseSize, weight: weight, color: color, lineHeight: lineHeight, monospaced: monospaced, uniformSource: uniformSource)
        view.linkTextAttributes = [.foregroundColor: NSColor(RelicStyle.accent)]
        if view.attributedString() != rendered {
            let selected = view.selectedRange(); view.textStorage?.setAttributedString(rendered)
            if selected.location + selected.length <= rendered.length { view.setSelectedRange(selected) }
            view.invalidateIntrinsicContentSize()
        }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextView, context: Context) -> CGSize? {
        let offered = proposal.width ?? (monospaced ? 100_000 : 400)
        let available = offered.isFinite ? max(1, offered) : 400
        return NativeTextStyle.contentSize(nsView.attributedString(), available: available)
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: SelectableText
        init(_ parent: SelectableText) { self.parent = parent }
        func textViewDidChangeSelection(_ notification: Notification) {
            guard let view = notification.object as? NSTextView else { return }
            if view.selectedRange().length > 0 {
                parent.m.selectedText = NativeInlineCode.source(view.attributedString().attributedSubstring(from: view.selectedRange())); parent.m.selectedAuthor = parent.author; parent.m.selectedTextView = view
            } else if parent.m.selectedTextView === view { parent.m.selectedText = ""; parent.m.selectedAuthor = ""; parent.m.selectedTextView = nil }
        }
        func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
            if let url = link as? URL { parent.openURL(url); return true }
            if let text = link as? String, let url = URL(string: text) { parent.openURL(url); return true }; return false
        }
    }
}

extension NativeTextStyle {
    static func contentSize(_ value: NSAttributedString, available: CGFloat) -> CGSize {
        // Measure a separate TextKit layout. SwiftUI probes several widths before
        // assigning the final frame; mutating the live container here leaves the
        // last probe width behind and can draw a second line outside its height.
        let storage = NSTextStorage(attributedString: value)
        let layout = NSLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 100_000, height: CGFloat.greatestFiniteMagnitude))
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        layout.ensureLayout(for: container)
        // CSS shrink-to-fit is based on the unwrapped preferred width. Using the
        // longest already-wrapped line incorrectly narrows the entire bubble.
        let width = max(1, min(available, ceil(layout.usedRect(for: container).width)))
        container.containerSize.width = width
        layout.ensureLayout(for: container)
        // A read-only pre-wrap block retains its terminal newline for selection,
        // but has no insertion line after it. TextKit's usedRect includes that
        // extra editing line; measure the actual glyph-bearing fragments instead.
        var bottom: CGFloat = 0
        layout.enumerateLineFragments(forGlyphRange: layout.glyphRange(for: container)) { line, _, _, _, _ in bottom = max(bottom, line.maxY) }
        return CGSize(width: width, height: max(1, bottom))
    }
}

final class QuoteTextView: ReadOnlyTextView {
    var sourceStorage: NSTextStorage?
    var measuredOpacity: Double = 1
    var productionRegion = "window"
    var quoteTitle = ""
    var quote: ((String) -> Void)?
    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        if selectedRange().length > 0 {
            let item = NSMenuItem(title: quoteTitle, action: #selector(quoteSelection), keyEquivalent: ""); item.target = self
            menu.insertItem(.separator(), at: 0); menu.insertItem(item, at: 0)
        }
        return menu
    }
    override func copy(_ sender: Any?) {
        guard selectedRange().length > 0 else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(NativeInlineCode.source(attributedString().attributedSubstring(from: selectedRange())), forType: .string)
    }
    @objc private func quoteSelection() { guard selectedRange().length > 0 else { return }; quote?(NativeInlineCode.source(attributedString().attributedSubstring(from: selectedRange()))); setSelectedRange(NSRange(location: selectedRange().location, length: 0)) }
}

// One attributed-text builder is used for native drawing and intrinsic sizing.
// Width comes from TextKit, so a horizontal code scroller cannot expand a short
// message's bubble to the whole available conversation column.
enum NativeTextStyle {
    static func render(_ value: AttributedString, size baseSize: CGFloat, weight: NSFont.Weight = .regular, color: Color = RelicStyle.ink, lineHeight: CGFloat? = nil, monospaced: Bool = false, uniformSource: Bool = false) -> NSAttributedString {
        let rendered = NSMutableAttributedString(attributedString: NSAttributedString(value))
        let range = NSRange(location: 0, length: rendered.length)
        let paragraph = NSMutableParagraphStyle()
        paragraph.minimumLineHeight = lineHeight ?? baseSize * 1.65; paragraph.maximumLineHeight = paragraph.minimumLineHeight
        let baseFont = monospaced ? RelicStyle.monoFont(baseSize) : RelicStyle.nativeFont(baseSize, weight: weight == .bold ? 700 : weight == .semibold ? 600 : 400)
        if monospaced {
            let space = NSAttributedString(string: " ", attributes: [.font: baseFont, .tracking: 0])
            paragraph.tabStops = []
            paragraph.defaultTabInterval = CTLineGetTypographicBounds(CTLineCreateWithAttributedString(space), nil, nil, nil) * 8
        }
        // Keep character spacing explicit in both drawing and intrinsic sizing.
        // The CI advance regression separately checks the resolved font metrics.
        rendered.addAttributes([.font: baseFont, .foregroundColor: NSColor(color), .paragraphStyle: paragraph, .tracking: 0,
            .baselineOffset: NativeLineMetrics.baselineOffset(font: baseFont, lineHeight: paragraph.minimumLineHeight),
            .relicConfiguredFontWeight: monospaced ? 400 : weight == .bold ? 700 : weight == .semibold ? 600 : 400], range: range)
        // Preserve inline Markdown emphasis/code traits after applying the base font.
        var codeRanges: [NSRange] = []
        for run in value.runs {
            guard let intent = run.inlinePresentationIntent else { continue }
            let prefix = String(value.characters[..<run.range.lowerBound]), text = String(value.characters[run.range])
            let nsRange = NSRange(location: (prefix as NSString).length, length: (text as NSString).length)
            var font = RelicStyle.nativeFont(baseSize, weight: weight == .bold ? 700 : weight == .semibold ? 600 : 400)
            if intent.contains(.code) { font = RelicStyle.monoFont(baseSize * 0.9); codeRanges.append(nsRange) }
            if intent.contains(.stronglyEmphasized) { font = RelicStyle.convertedFont(font, trait: .boldFontMask) }
            if intent.contains(.emphasized) { font = RelicStyle.convertedFont(font, trait: .italicFontMask) }
            rendered.addAttribute(.font, value: font, range: nsRange)
            rendered.addAttribute(.relicConfiguredFontWeight, value: intent.contains(.stronglyEmphasized) ? 700 : intent.contains(.code) ? 400 : weight == .bold ? 700 : weight == .semibold ? 600 : 400, range: nsRange)
        }
        NativeInlineCode.decorate(rendered, ranges: codeRanges)
        if uniformSource && codeRanges.isEmpty && value.runs.allSatisfy({ $0.inlinePresentationIntent == nil && $0.link == nil }) {
            // A raw tool-output string is one production text element. Preserve
            // that source boundary when TextKit fixes fallback font attributes.
            rendered.addAttribute(.relicLabelSpan, value: "uniform-production-label", range: NSRange(location: 0, length: rendered.length))
        }
        return rendered
    }
    static func preferredWidth(_ value: NSAttributedString) -> CGFloat {
        let storage = NSTextStorage(attributedString: value), layout = NSLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 100_000, height: CGFloat.greatestFiniteMagnitude))
        container.lineFragmentPadding = 0; storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        return ceil(layout.usedRect(for: container).width)
    }
}
