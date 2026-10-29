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
    let value: AttributedString
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
            selectable.quoteTitle = m.t("common.quote")
            selectable.quote = { text in m.setQuote(text, from: author.isEmpty ? m.t("common.quote") : author) }
        }
        let rendered = NSMutableAttributedString(attributedString: NSAttributedString(value))
        let range = NSRange(location: 0, length: rendered.length)
        rendered.addAttributes([.font: NSFont.systemFont(ofSize: m.preferences["font"].text == "large" ? 16 : m.preferences["font"].text == "small" ? 12 : 14), .foregroundColor: NSColor.labelColor], range: range)
        // Preserve inline Markdown emphasis/code traits after applying the base font.
        for run in value.runs {
            guard let intent = run.inlinePresentationIntent else { continue }
            let prefix = String(value.characters[..<run.range.lowerBound]), text = String(value.characters[run.range])
            let nsRange = NSRange(location: (prefix as NSString).length, length: (text as NSString).length)
            var font = NSFont.systemFont(ofSize: m.preferences["font"].text == "large" ? 16 : m.preferences["font"].text == "small" ? 12 : 14)
            if intent.contains(.code) { font = .monospacedSystemFont(ofSize: font.pointSize, weight: .regular) }
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
        let width = max(1, proposal.width ?? 400)
        guard let container = nsView.textContainer, let layout = nsView.layoutManager else { return nil }
        container.containerSize = NSSize(width: width, height: .greatestFiniteMagnitude)
        layout.ensureLayout(for: container)
        return CGSize(width: width, height: max(20, ceil(layout.usedRect(for: container).height)))
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
