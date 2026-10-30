import SwiftUI
import AppKit

// Native TextKit draws these labels and exposes the same glyph layout to the
// inspector. This also retains individual labels inside complex SwiftUI buttons.
struct ReferenceLabel: NSViewRepresentable {
    let text: String
    var size: CGFloat = 14
    var weight: Int = 400
    var color: Color = RelicStyle.ink
    var lineHeight: CGFloat? = nil
    var lines: Int = 1
    var alignment: NSTextAlignment = .left
    var owner: String? = nil
    var monospaced = false
    var pathWrapping = false
    @Environment(\.captureOpacity) private var opacity
    @Environment(\.captureRegion) private var region
    @Environment(\.nativeElementParent) private var nativeParent
    init(_ text: String, size: CGFloat = 14, weight: Int = 400, color: Color = RelicStyle.ink, lineHeight: CGFloat? = nil, lines: Int = 1, alignment: NSTextAlignment = .left, owner: String? = nil, monospaced: Bool = false, pathWrapping: Bool = false) {
        self.text = text; self.size = size; self.weight = weight; self.color = color
        self.lineHeight = lineHeight; self.lines = lines; self.alignment = alignment; self.owner = owner
        self.monospaced = monospaced
        self.pathWrapping = pathWrapping
    }
    func makeNSView(context: Context) -> ReferenceLabelView {
        let view = makeLabelView()
        updateNSView(view, context: context); return view
    }
    func makeLabelView() -> ReferenceLabelView {
        let storage = NSTextStorage(), layout = NativeGlyphLayoutManager()
        let container = NSTextContainer(containerSize: NSSize(width: 400, height: CGFloat.greatestFiniteMagnitude))
        layout.recordDraws = VisualCapture.enabled
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        let view = ReferenceLabelView(frame: .zero, textContainer: container)
        view.sourceStorage = storage
        view.pathLineBreaks.enabled = pathWrapping; layout.delegate = view.pathLineBreaks
        view.isEditable = false; view.isSelectable = false; view.drawsBackground = false
        // SwiftUI assigns the measured frame. TextKit must not resize it during
        // draw or AX inspection after that layout has been committed.
        view.isRichText = true; view.isHorizontallyResizable = false; view.isVerticallyResizable = false
        view.textContainerInset = .zero; view.textContainer?.lineFragmentPadding = 0
        view.textContainer?.widthTracksTextView = true
        view.textContainer?.heightTracksTextView = false
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.textContainer?.maximumNumberOfLines = lines
        view.textContainer?.lineBreakMode = lines > 0 ? .byTruncatingTail : .byWordWrapping
        view.textStorage?.setAttributedString(attributedText)
        return view
    }
    var attributedText: NSAttributedString {
        let paragraph = NSMutableParagraphStyle()
        paragraph.minimumLineHeight = lineHeight ?? size * 1.6; paragraph.maximumLineHeight = paragraph.minimumLineHeight
        paragraph.alignment = alignment
        paragraph.lineBreakMode = lines == 1 ? .byTruncatingTail : .byWordWrapping
        return NSAttributedString(string: text, attributes: [.font: monospaced ? RelicStyle.monoFont(size) : RelicStyle.nativeFont(size, weight: weight), .foregroundColor: NSColor(color), .paragraphStyle: paragraph, .tracking: 0, .relicLabelSpan: "uniform-production-label"])
    }
    func updateNSView(_ view: ReferenceLabelView, context: Context) {
        let value = attributedText
        view.pathLineBreaks.enabled = pathWrapping
        view.textContainer?.maximumNumberOfLines = lines
        view.textContainer?.lineBreakMode = lines > 0 ? .byTruncatingTail : .byWordWrapping
        view.measuredOpacity = opacity; view.productionOwner = owner
        view.productionParent = nativeParent
        view.productionRegion = region
        if view.attributedString() != value { view.textStorage?.setAttributedString(value); view.invalidateIntrinsicContentSize() }
        view.setAccessibilityLabel(text)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: ReferenceLabelView, context: Context) -> CGSize? {
        let width = (proposal.width?.isFinite == true ? proposal.width : nil) ?? 100_000
        let storage = NSTextStorage(attributedString: nsView.attributedString()), layout = NSLayoutManager()
        layout.delegate = nsView.pathLineBreaks
        let container = NSTextContainer(containerSize: CGSize(width: max(0.01, width), height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0; container.maximumNumberOfLines = lines
        container.lineBreakMode = lines > 0 ? .byTruncatingTail : .byWordWrapping
        storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        let used = layout.usedRect(for: container)
        return CGSize(width: min(width, ceil(used.width)), height: max(lineHeight ?? size * 1.6, used.height))
    }
}

final class ReferenceLabelView: NSTextView {
    var sourceStorage: NSTextStorage?
    let pathLineBreaks = PathLineBreaks()
    var measuredOpacity: Double = 1
    var productionOwner: String?
    var productionParent: String?
    var productionRegion = "window"
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func accessibilityRole() -> NSAccessibility.Role? { .staticText }
}

/// AppKit treats a slash in a path as a convenient word boundary. The reference
/// keeps slash-separated Latin text together, preferring ordinary word/hyphen
/// breaks and breaking an overlong segment only when it cannot fit a whole line.
/// Keep the source string unchanged; this participates in actual TextKit layout.
final class PathLineBreaks: NSObject, NSLayoutManagerDelegate {
    var enabled = false
    func layoutManager(_ layoutManager: NSLayoutManager, shouldBreakLineByWordBeforeCharacterAt charIndex: Int) -> Bool {
        guard enabled, let text = layoutManager.textStorage?.string as NSString?, charIndex > 0, charIndex < text.length else { return true }
        return text.character(at: charIndex - 1) != 0x2f
    }
}

struct TextButton: View {
    let title: String
    var role: ButtonRole? = nil
    var size: CGFloat = 12
    var weight = 600
    var color: Color = RelicStyle.ink
    var height: CGFloat? = nil
    var padding: CGFloat = 0
    var lines = 1
    let action: () -> Void
    @State private var identity = "relic-text-button/" + UUID().uuidString
    init(_ title: String, role: ButtonRole? = nil, size: CGFloat = 12, weight: Int = 600, color: Color = RelicStyle.ink, height: CGFloat? = nil, padding: CGFloat = 0, lines: Int = 1, action: @escaping () -> Void) {
        self.title = title; self.role = role; self.size = size; self.weight = weight; self.color = color
        self.height = height; self.padding = padding; self.lines = lines; self.action = action
    }
    var body: some View {
        Button(role: role, action: action) { ReferenceLabel(title, size: size, weight: weight, color: color, lines: lines, owner: identity).padding(.horizontal, padding).frame(height: height) }
            .accessibilityIdentifier(identity).accessibilityLabel(title)
    }
}
