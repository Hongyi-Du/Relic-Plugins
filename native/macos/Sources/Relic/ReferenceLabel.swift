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
    var struck = false
    var accessibleName: String? = nil
    var controlLabel = false
    var stateOwner: String? = nil
    var textGlyphIcon = false
    var truncates = true
    @Environment(\.captureOpacity) private var opacity
    @Environment(\.captureRegion) private var region
    @Environment(\.nativeElementParent) private var nativeParent
    init(_ text: String, size: CGFloat = 14, weight: Int = 400, color: Color = RelicStyle.ink, lineHeight: CGFloat? = nil, lines: Int = 1, alignment: NSTextAlignment = .left, owner: String? = nil, monospaced: Bool = false, pathWrapping: Bool = false, struck: Bool = false, accessibleName: String? = nil, controlLabel: Bool = false, textGlyphIcon: Bool = false, stateOwner: String? = nil, truncates: Bool = true) {
        self.text = text; self.size = size; self.weight = weight; self.color = color
        self.lineHeight = lineHeight; self.lines = lines; self.alignment = alignment; self.owner = owner
        self.monospaced = monospaced
        self.pathWrapping = pathWrapping
        self.struck = struck
        self.accessibleName = accessibleName
        self.controlLabel = controlLabel
        self.stateOwner = stateOwner
        self.textGlyphIcon = textGlyphIcon
        self.truncates = truncates
    }
    private var containerBreakMode: NSLineBreakMode { lines > 0 ? (truncates ? .byTruncatingTail : .byClipping) : .byWordWrapping }
    func makeNSView(context: Context) -> ReferenceLabelView {
        let view = makeLabelView()
        updateNSView(view, context: context); return view
    }
    func makeLabelView() -> ReferenceLabelView {
        let storage = NSTextStorage(), layout = NativeGlyphLayoutManager()
        layout.drawsGlyphsIntoCurrentContext = true
        let container = NSTextContainer(containerSize: NSSize(width: 400, height: CGFloat.greatestFiniteMagnitude))
        layout.recordDraws = VisualCapture.enabled
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        let view = ReferenceLabelView(frame: .zero, textContainer: container)
        view.sourceStorage = storage
        view.pathLineBreaks.enabled = pathWrapping; layout.delegate = view.pathLineBreaks
        view.isEditable = false; view.isSelectable = false; view.drawsBackground = false
        view.focusRingType = .none
        view.layerContentsRedrawPolicy = .onSetNeedsDisplay
        // SwiftUI assigns the measured frame. TextKit must not resize it during
        // draw or AX inspection after that layout has been committed.
        view.isRichText = true; view.isHorizontallyResizable = false; view.isVerticallyResizable = false
        view.textContainerInset = .zero; view.textContainer?.lineFragmentPadding = 0
        view.textContainer?.widthTracksTextView = true
        view.textContainer?.heightTracksTextView = false
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.textContainer?.maximumNumberOfLines = lines
        view.textContainer?.lineBreakMode = containerBreakMode
        view.textStorage?.setAttributedString(attributedText)
        view.hasExplicitAccessibilityName = accessibleName != nil
        view.textGlyphIcon = textGlyphIcon
        view.setAccessibilityLabel(accessibleName ?? text)
        return view
    }
    var attributedText: NSAttributedString {
        let paragraph = NSMutableParagraphStyle()
        paragraph.minimumLineHeight = lineHeight ?? size * 1.6; paragraph.maximumLineHeight = paragraph.minimumLineHeight
        paragraph.alignment = alignment
        paragraph.lineBreakMode = lines == 1 ? containerBreakMode : .byWordWrapping
        let font = monospaced ? (weight >= 600 ? RelicStyle.convertedFont(RelicStyle.monoFont(size), trait: .boldFontMask) : RelicStyle.monoFont(size)) : RelicStyle.nativeFont(size, weight: weight)
        var attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor(color), .paragraphStyle: paragraph, .tracking: 0,
            .baselineOffset: NativeLineMetrics.baselineOffset(font: font, lineHeight: paragraph.minimumLineHeight),
            .relicLabelSpan: "uniform-production-label", .relicConfiguredFontWeight: weight]
        if struck { attributes[.strikethroughStyle] = NSUnderlineStyle.single.rawValue }
        return NSAttributedString(string: text, attributes: attributes)
    }
    func updateNSView(_ view: ReferenceLabelView, context: Context) {
        let value = attributedText
        view.pathLineBreaks.enabled = pathWrapping
        view.textContainer?.maximumNumberOfLines = lines
        view.textContainer?.lineBreakMode = containerBreakMode
        view.measuredOpacity = opacity; view.productionOwner = owner
        view.productionControlLabelOwner = stateOwner ?? (controlLabel ? owner : nil)
        view.productionParent = nativeParent
        view.productionRegion = region
        if view.attributedString() != value { view.textStorage?.setAttributedString(value); view.invalidateIntrinsicContentSize() }
        view.hasExplicitAccessibilityName = accessibleName != nil
        view.textGlyphIcon = textGlyphIcon
        view.setAccessibilityLabel(accessibleName ?? text)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: ReferenceLabelView, context: Context) -> CGSize? {
        let width = (proposal.width?.isFinite == true ? proposal.width : nil) ?? 100_000
        let storage = NSTextStorage(attributedString: nsView.attributedString()), layout = NSLayoutManager()
        layout.delegate = nsView.pathLineBreaks
        let container = NSTextContainer(containerSize: CGSize(width: max(0.01, width), height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0; container.maximumNumberOfLines = lines
        container.lineBreakMode = containerBreakMode
        storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        let used = layout.usedRect(for: container)
        return CGSize(width: min(width, ceil(used.width)), height: max(lineHeight ?? size * 1.6, used.height))
    }
}

final class ReferenceLabelView: ReadOnlyTextView {
    var sourceStorage: NSTextStorage?
    let pathLineBreaks = PathLineBreaks()
    var measuredOpacity: Double = 1
    var productionOwner: String?
    var productionControlLabelOwner: String?
    var productionParent: String?
    var productionRegion = "window"
    var hasExplicitAccessibilityName = false
    var textGlyphIcon = false
    private var backingImage: CGImage?
    private var backingSource: NSAttributedString?
    private var backingBounds = NSRect.zero, backingFrame = NSRect.zero
    private var backingWindow: ObjectIdentifier?
    private var backingScale: CGFloat = 1
    private var backingDraw: [String: Any]?
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func accessibilityRole() -> NSAccessibility.Role? { .staticText }
    override var wantsUpdateLayer: Bool { true }
    override func makeBackingLayer() -> CALayer { CALayer() }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance(); needsDisplay = true
    }
    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties(); needsDisplay = true
    }
    override func setFrameSize(_ newSize: NSSize) {
        let changed = frame.size != newSize
        super.setFrameSize(newSize)
        if changed { needsDisplay = true }
    }
    override func updateLayer() {
        guard let layer else { return }
        let scale = window?.backingScaleFactor ?? 1
        guard bounds.width > 0, bounds.height > 0, bounds.width.isFinite, bounds.height.isFinite,
              let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: Int(ceil(bounds.width * scale)), height: Int(ceil(bounds.height * scale)),
                bitsPerComponent: 8, bytesPerRow: 0, space: space,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else {
            layer.contents = nil; backingImage = nil; backingSource = nil; backingDraw = nil
            return
        }
        context.translateBy(x: 0, y: CGFloat(context.height))
        context.scaleBy(x: scale, y: -scale)
        context.translateBy(x: -bounds.minX, y: -bounds.minY)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
        draw(bounds)
        NSGraphicsContext.restoreGraphicsState()
        guard let image = context.makeImage() else { return }
        // Submit the actual native raster to this view's own backing layer.
        // No AppKit editable-text ContentLayer or private image representation
        // participates in this drawing path.
        layer.contentsScale = scale; layer.contentsGravity = .topLeft; layer.contents = image
        backingImage = image; backingSource = textStorage.map { NSAttributedString(attributedString: $0) }
        backingBounds = bounds; backingFrame = frame; backingScale = scale
        backingWindow = window.map(ObjectIdentifier.init)
        backingDraw = (layoutManager as? NativeGlyphLayoutManager)?.lastDraw
    }
    func backingPaintObservation() -> [String: Any] {
        let contents = layer?.contents as AnyObject?
        let matches = backingImage.map { contents === $0 } ?? false
        let current = matches && backingSource.map { source in textStorage.map { source.isEqual(to: $0) } ?? false } == true
            && backingBounds == bounds && backingFrame == frame && backingWindow == window.map(ObjectIdentifier.init)
            && layer?.contentsScale == backingScale && layer?.contentsGravity == .topLeft
        return ["source": "production ReferenceLabelView.updateLayer native sRGB image",
            "current": current, "view_identity": String(describing: ObjectIdentifier(self)),
            "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "image_identity": backingImage.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
            "layer_contents_is_same_image": matches, "scale": backingScale,
            "image_width": backingImage?.width as Any? ?? NSNull(), "image_height": backingImage?.height as Any? ?? NSNull(),
            "local_bounds": ElementCapture.box(backingBounds), "native_frame": ElementCapture.box(backingFrame),
            "glyph_draw": backingDraw as Any? ?? NSNull(), "final_png_attribution_proven": false]
    }
    override func draw(_ dirtyRect: NSRect) {
        // These labels are never editable or selectable. Draw their actual
        // TextKit layout directly, so AppKit's editable-text content layers do
        // not contribute another unowned drawing path behind native controls.
        // The same manager supplies shaping, truncation, decoration and the
        // observed showCGGlyphs callbacks; no second text shaping is involved.
        guard let manager = layoutManager, let container = textContainer,
              NSGraphicsContext.current != nil else { return }
        manager.ensureLayout(for: container)
        let glyphs = manager.glyphRange(for: container)
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect: bounds.intersection(dirtyRect)).addClip()
        manager.drawBackground(forGlyphRange: glyphs, at: textContainerOrigin)
        manager.drawGlyphs(forGlyphRange: glyphs, at: textContainerOrigin)
        NSGraphicsContext.restoreGraphicsState()
    }
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
    var fillsWidth = false
    var identifier: String? = nil
    let action: () -> Void
    @State private var automaticIdentity = "relic-text-button/" + UUID().uuidString
    private var identity: String { identifier ?? automaticIdentity }
    init(_ title: String, role: ButtonRole? = nil, size: CGFloat = 12, weight: Int = 600, color: Color = RelicStyle.ink, height: CGFloat? = nil, padding: CGFloat = 0, lines: Int = 1, fillsWidth: Bool = false, identifier: String? = nil, action: @escaping () -> Void) {
        self.title = title; self.role = role; self.size = size; self.weight = weight; self.color = color
        self.height = height; self.padding = padding; self.lines = lines; self.action = action
        self.identifier = identifier
        self.fillsWidth = fillsWidth
    }
    var body: some View {
        Button(role: role, action: action) {
            ReferenceLabel(title, size: size, weight: weight, color: color, lines: lines, owner: identity, truncates: false)
                .padding(.horizontal, padding).frame(height: height).frame(maxWidth: fillsWidth ? .infinity : nil)
                .contentShape(Rectangle())
        }
            .accessibilityIdentifier(identity).accessibilityLabel(title)
    }
}
