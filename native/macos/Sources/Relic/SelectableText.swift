import SwiftUI
import AppKit

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
    let value: AttributedString
    var scale: CGFloat = 1
    var weight: NSFont.Weight = .regular
    var color: Color = RelicStyle.ink
    var pointSize: CGFloat? = nil
    var lineHeight: CGFloat? = nil
    var monospaced = false
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSTextView {
        let view = QuoteTextView()
        view.isEditable = false; view.isSelectable = true; view.drawsBackground = false
        view.isRichText = true; view.isHorizontallyResizable = false; view.isVerticallyResizable = true
        view.textContainerInset = .zero; view.textContainer?.lineFragmentPadding = 0
        view.textContainer?.widthTracksTextView = true; view.delegate = context.coordinator
        updateNSView(view, context: context); return view
    }
    func updateNSView(_ view: NSTextView, context: Context) {
        context.coordinator.parent = self
        if let selectable = view as? QuoteTextView {
            selectable.measuredOpacity = opacity
            selectable.quoteTitle = m.t("common.quote")
            selectable.quote = { text in m.setQuote(text, from: author.isEmpty ? m.t("common.quote") : author) }
        }
        let rendered = NSMutableAttributedString(attributedString: NSAttributedString(value))
        let range = NSRange(location: 0, length: rendered.length)
        let paragraph = NSMutableParagraphStyle()
        let baseSize: CGFloat = pointSize ?? (m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14) * scale
        paragraph.minimumLineHeight = lineHeight ?? baseSize * 1.65; paragraph.maximumLineHeight = paragraph.minimumLineHeight
        let baseFont = monospaced ? RelicStyle.monoFont(baseSize) : RelicStyle.nativeFont(baseSize, weight: weight == .bold ? 700 : weight == .semibold ? 600 : 400)
        rendered.addAttributes([.font: baseFont, .foregroundColor: NSColor(color), .paragraphStyle: paragraph], range: range)
        view.linkTextAttributes = [.foregroundColor: NSColor(RelicStyle.accent)]
        // Preserve inline Markdown emphasis/code traits after applying the base font.
        for run in value.runs {
            guard let intent = run.inlinePresentationIntent else { continue }
            let prefix = String(value.characters[..<run.range.lowerBound]), text = String(value.characters[run.range])
            let nsRange = NSRange(location: (prefix as NSString).length, length: (text as NSString).length)
            var font = RelicStyle.nativeFont(baseSize, weight: weight == .bold ? 700 : weight == .semibold ? 600 : 400)
            if intent.contains(.code) { font = RelicStyle.monoFont(baseSize * 0.9) }
            if intent.contains(.stronglyEmphasized) { font = NSFontManager.shared.convert(font, toHaveTrait: .boldFontMask) }
            if intent.contains(.emphasized) { font = NSFontManager.shared.convert(font, toHaveTrait: .italicFontMask) }
            rendered.addAttribute(.font, value: font, range: nsRange)
        }
        if view.attributedString() != rendered {
            let selected = view.selectedRange(); view.textStorage?.setAttributedString(rendered)
            if selected.location + selected.length <= rendered.length { view.setSelectedRange(selected) }
            view.invalidateIntrinsicContentSize()
        }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextView, context: Context) -> CGSize? {
        let offered = proposal.width ?? (monospaced ? 100_000 : 400)
        let available = offered.isFinite ? max(1, offered) : 400
        // Measure a separate TextKit layout. SwiftUI probes several widths before
        // assigning the final frame; mutating the live container here leaves the
        // last probe width behind and can draw a second line outside its height.
        let storage = NSTextStorage(attributedString: nsView.attributedString())
        let layout = NSLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 100_000, height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        layout.ensureLayout(for: container)
        // CSS shrink-to-fit is based on the unwrapped preferred width. Using the
        // longest already-wrapped line incorrectly narrows the entire bubble.
        let width = max(1, min(available, ceil(layout.usedRect(for: container).width)))
        container.containerSize.width = width
        layout.ensureLayout(for: container)
        return CGSize(width: width, height: max(1, ceil(layout.usedRect(for: container).height)))
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: SelectableText
        init(_ parent: SelectableText) { self.parent = parent }
        func textViewDidChangeSelection(_ notification: Notification) {
            guard let view = notification.object as? NSTextView else { return }
            if view.selectedRange().length > 0 {
                parent.m.selectedText = (view.string as NSString).substring(with: view.selectedRange()); parent.m.selectedAuthor = parent.author; parent.m.selectedTextView = view
            } else if parent.m.selectedTextView === view { parent.m.selectedText = ""; parent.m.selectedAuthor = ""; parent.m.selectedTextView = nil }
        }
        func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
            if let url = link as? URL { parent.openURL(url); return true }
            if let text = link as? String, let url = URL(string: text) { parent.openURL(url); return true }; return false
        }
    }
}

final class QuoteTextView: NSTextView {
    var measuredOpacity: Double = 1
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
    @objc private func quoteSelection() { guard selectedRange().length > 0 else { return }; quote?((string as NSString).substring(with: selectedRange())); setSelectedRange(NSRange(location: selectedRange().location, length: 0)) }
}
