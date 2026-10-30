import AppKit
import SwiftUI
import RelicCore
import RelicAX
import CoreText

// Measurements come from the live production accessibility/view tree and PNG.
// This exporter never reads the reference's element data or substitutes its values.
@MainActor enum ElementCapture {
    static func nativeButtonTitle(_ object: AnyObject) -> String? {
        if let button = object as? NSButton { return button.title }
        if let cell = object as? NSButtonCell { return (cell.controlView as? NSButton)?.title ?? cell.title }
        return nil
    }
    static func topLeft(_ screen: NSRect, in content: NSRect) -> NSRect {
        NSRect(x: screen.minX - content.minX, y: content.maxY - screen.maxY, width: screen.width, height: screen.height)
    }
    static func box(_ rect: NSRect) -> [String: Double] {
        ["x": Double(rect.minX), "y": Double(rect.minY), "width": Double(rect.width), "height": Double(rect.height)]
    }
    static func rect(_ value: Any?) -> NSRect {
        guard let box = value as? [String: Double], let x = box["x"], let y = box["y"], let width = box["width"], let height = box["height"] else { return .null }
        return NSRect(x: x, y: y, width: width, height: height)
    }
    static func assignedRegion(identifier: String, textRegion: String?, inherited: String, geometric: String) -> String {
        if identifier.hasPrefix("relic-region/") { return String(identifier.dropFirst("relic-region/".count)) }
        if let textRegion { return textRegion }
        return inherited == "window" ? geometric : inherited
    }
    static func kind(_ role: String) -> String {
        switch role {
        case "AXButton", "AXDisclosureTriangle": return "button"
        case "AXStaticText": return "text"
        case "AXTextField", "AXTextArea", "AXSearchField": return "input"
        case "AXCheckBox": return "checkbox"
        case "AXRadioButton": return "checkbox"
        case "AXPopUpButton", "AXComboBox": return "dropdown"
        case "AXLink": return "link"
        case "AXImage": return "image"
        case "AXMenuItem": return "menu-item"
        case "AXMenu", "AXTabGroup", "AXRadioGroup", "AXOpaqueProviderGroup": return "region"
        case "AXRow": return "list-row"
        case "AXList", "AXOutline", "AXTable": return "region"
        case "AXSplitter", "AXSplitGroup": return "divider"
        case "AXScrollArea": return "region"
        case "AXScrollBar": return "scrollbar"
        case "AXGrowArea": return "resize-handle"
        case "AXGroup", "AXLayoutArea": return "region"
        default: return "unknown"
        }
    }
    static func accessibleName(role: String, label: String, value: String) -> String {
        // AXStaticText exposes its spoken text as AXValue when there is no
        // explicit AXLabel. Editable values and numeric control states are
        // never promoted to names.
        label.isEmpty && role == "AXStaticText" ? value : label
    }
    static func cssWeight(_ font: NSFont) -> Int {
        let traits = font.fontDescriptor.object(forKey: .traits) as? [NSFontDescriptor.TraitKey: Any]
        let value = (traits?[.weight] as? NSNumber)?.doubleValue ?? 0
        let weights: [(Double, Int)] = [(-0.8, 100), (-0.6, 200), (-0.4, 300), (0, 400), (0.23, 500), (0.3, 600), (0.4, 700), (0.56, 800), (0.62, 900)]
        if value <= weights[0].0 { return weights[0].1 }
        for index in 1..<weights.count where value <= weights[index].0 {
            let lower = weights[index - 1], upper = weights[index]
            return Int((Double(lower.1) + (value - lower.0) / (upper.0 - lower.0) * Double(upper.1 - lower.1)).rounded())
        }
        return weights.last!.1
    }
    static func rgba(_ color: NSColor?) -> Any {
        guard let color = color?.usingColorSpace(.sRGB) else { return NSNull() }
        return [color.redComponent, color.greenComponent, color.blueComponent, color.alphaComponent].map { Double($0 * 255) }
    }
    private static func string(_ value: Any?) -> String {
        if let value = value as? String { return value }
        if let value = value as? NSAttributedString { return value.string }
        return ""
    }
    static func fontFromAX(_ attributes: [String: Any]) -> NSFont? {
        guard let name = attributes["AXFontName"] as? String, let size = attributes["AXFontSize"] as? NSNumber else { return nil }
        // Public system font factories preserve the actual face reported by AX.
        // NSFont(name: ".SFNS-…") silently substitutes Times New Roman on CI.
        if name.hasPrefix(".SFNS-"), attributes["AXFontFamily"] as? String == ".AppleSystemUIFont" {
            let weights: [String: NSFont.Weight] = ["ultralight": .ultraLight, "thin": .thin, "light": .light, "regular": .regular, "medium": .medium, "semibold": .semibold, "bold": .bold, "heavy": .heavy, "black": .black]
            guard let weight = weights[String(name.dropFirst(6)).lowercased()] else { return nil }
            return NSFont.systemFont(ofSize: CGFloat(size.doubleValue), weight: weight)
        }
        guard NSFontManager.shared.availableFonts.contains(name) else { return nil }
        return NSFont(name: name, size: CGFloat(size.doubleValue))
    }
    static func reshapedFonts(_ value: NSAttributedString) -> [[String: Any]] {
        let line = CTLineCreateWithAttributedString(value)
        return (CTLineGetGlyphRuns(line) as! [CTRun]).compactMap { run in
            let attributes = CTRunGetAttributes(run) as NSDictionary
            guard let rawFont = attributes[kCTFontAttributeName] else { return nil }
            let font = rawFont as! CTFont
            let variations = (CTFontCopyVariation(font) as? [NSNumber: NSNumber]).map { Dictionary(uniqueKeysWithValues: $0.map { ($0.key.stringValue, $0.value.doubleValue) }) }
            return ["family_name": CTFontCopyFamilyName(font) as String, "postscript_name": CTFontCopyPostScriptName(font) as String,
                    "glyph_count": CTRunGetGlyphCount(run), "provider": "CoreText shaping of the native attributed text",
                    "actual_variations": variations as Any? ?? NSNull(), "optical_size_attribute": CTFontCopyAttribute(font, kCTFontOpticalSizeAttribute).map { String(describing: $0) } as Any? ?? NSNull(),
                    "ascent": CTFontGetAscent(font), "descent": CTFontGetDescent(font), "leading": CTFontGetLeading(font)]
        }
    }
    private static func style(_ object: AnyObject, text: String) -> [String: Any] {
        var result: [String: Any] = ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull(), "backgroundColor": NSNull(), "borderColor": NSNull(), "borderWidth": NSNull(), "borderRadius": NSNull()]
        var font: NSFont?, foreground: NSColor?, background: NSColor?
        if let textView = object as? NSTextView {
            font = textView.font; foreground = textView.textColor; if textView.drawsBackground { background = textView.backgroundColor }
            if let editor = textView as? ComposerTextView, editor.string.isEmpty {
                font = editor.placeholderAttributes[.font] as? NSFont
                foreground = editor.placeholderAttributes[.foregroundColor] as? NSColor
            }
        }
        else if let field = object as? NSTextField { font = field.font; foreground = field.textColor; if field.drawsBackground { background = field.backgroundColor } }
        else if let cell = object as? NSTextFieldCell {
            // SwiftUI exposes its real NSTextFieldCell through AX, while the
            // owning NSTextField is an ignored backing view. Read that actual
            // cell instead of treating a cell as an unmeasured virtual control.
            font = cell.font; foreground = cell.textColor
            if cell.drawsBackground { background = cell.backgroundColor }
            if cell.stringValue.isEmpty {
                if let placeholder = cell.placeholderAttributedString, placeholder.length > 0 {
                    font = placeholder.attribute(.font, at: 0, effectiveRange: nil) as? NSFont ?? font
                    foreground = placeholder.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor
                    result["native_placeholder_attributes"] = Dictionary(uniqueKeysWithValues:
                        placeholder.attributes(at: 0, effectiveRange: nil).map { ($0.key.rawValue, String(describing: $0.value)) })
                } else { foreground = nil }
            }
            result["native_cell_control_identity"] = cell.controlView.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()
        }
        else if let cell = object as? ReferencePopUpCell {
            font = cell.font
            if cell.attributedTitle.length > 0 { foreground = cell.attributedTitle.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor }
            result["native_cell_control_identity"] = cell.controlView.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()
        }
        else if let popup = object as? NSPopUpButton {
            font = popup.font
            if popup.attributedTitle.length > 0 { foreground = popup.attributedTitle.attribute(.foregroundColor, at: 0, effectiveRange: nil) as? NSColor }
        }
        else if let control = object as? NSControl { font = control.font }
        if !text.isEmpty, let attributed = RelicAXText(object, NSRange(location: 0, length: (text as NSString).length)), attributed.length > 0 {
            let attributes = attributed.attributes(at: 0, effectiveRange: nil)
            font = (attributes[.font] as? NSFont) ?? font
            foreground = (attributes[.foregroundColor] as? NSColor) ?? foreground
            background = (attributes[.backgroundColor] as? NSColor) ?? background
            if let axFont = attributes[NSAttributedString.Key("AXFont")] as? [String: Any] {
                result["fontSize"] = axFont["AXFontSize"] ?? NSNull()
                result["fontFamily"] = axFont["AXFontFamily"] ?? axFont["AXFontName"] ?? NSNull()
                font = fontFromAX(axFont) ?? font
            }
            if let value = attributes[NSAttributedString.Key("AXForegroundColor")] {
                if let color = value as? NSColor { foreground = color }
                else if CFGetTypeID(value as CFTypeRef) == CGColor.typeID { foreground = NSColor(cgColor: value as! CGColor) }
            }
            // Preserve all platform attributes separately for audit, including
            // attributes not yet understood by the common normalizer.
            result["rawTextAttributes"] = Dictionary(uniqueKeysWithValues: attributes.map { ($0.key.rawValue, String(describing: $0.value)) })
        }
        if let font {
            result["fontSize"] = Double(font.pointSize); result["fontWeight"] = cssWeight(font); result["fontFamily"] = font.familyName ?? font.fontName
            result["native_reshaped_fonts"] = reshapedFonts(NSAttributedString(string: text, attributes: [.font: font]))
            result["rendered_fonts"] = NSNull() // Attribute/AX fonts do not prove the actual fallback glyph draw.
        }
        result["color"] = rgba(foreground); result["backgroundColor"] = rgba(background)
        return result
    }
    private static func samples(_ rect: NSRect, bitmap: NSBitmapImageRep) -> [[String: Any]] {
        let bounds = NSRect(x: 0, y: 0, width: CGFloat(bitmap.pixelsWide), height: CGFloat(bitmap.pixelsHigh))
        let visible = rect.intersection(bounds)
        guard !visible.isNull, visible.width > 0, visible.height > 0 else { return [] }
        return [0.1, 0.5, 0.9].flatMap { fy in [0.1, 0.5, 0.9].map { fx in
            let x = min(bitmap.pixelsWide - 1, max(0, Int(visible.minX + visible.width * fx)))
            let y = min(bitmap.pixelsHigh - 1, max(0, Int(visible.minY + visible.height * fy)))
            return ["x": x, "y": y, "rgba": CaptureRaster.sRGBPixel(bitmap, x: x, y: y) as Any? ?? NSNull(),
                    "source": "raw native PNG samples in its measured sRGB color space", "color_space": bitmap.colorSpace.localizedName as Any? ?? NSNull()]
        } }
    }
    static func textRuns(_ view: NSTextView) -> [[String: Any]] {
        // Merely reading layoutManager on TextKit 2 permanently switches its
        // renderer to TextKit 1 and removes its live content/selection views.
        // Preserve those controls and their AX evidence until their own layout
        // API can be measured; never mutate the UI while extracting evidence.
        guard view.textLayoutManager == nil else { return [] }
        var result: [[String: Any]] = []
        view.effectiveAppearance.performAsCurrentDrawingAppearance { result = measuredTextRuns(view) }
        return result
    }
    private static func measuredTextRuns(_ view: NSTextView) -> [[String: Any]] {
        guard let manager = view.layoutManager, let container = view.textContainer, let storage = view.textStorage else { return [] }
        manager.ensureLayout(for: container)
        var rows: [[String: Any]] = []
        var codeParents: [String: Int] = [:]
        let codeManager = manager as? InlineCodeLayoutManager
        let codeFragments = codeManager?.codeFragments(in: container) ?? []
        NativeTextSpans.enumerate(storage) { attributes, range, attributeRuns, fonts in
            if let group = attributes[.relicCodeGroup] as? String, codeParents[group] == nil {
                codeParents[group] = rows.count
                for fragment in codeFragments.filter({ $0.group == group }) {
                    let rect = fragment.rect.offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y)
                    rows.append(["text": "", "range": ["location": fragment.range.location, "length": fragment.range.length], "local_rect": NSValue(rect: rect), "lines": [box(rect)], "kind": "card",
                                 "layout": ["wrap": NSNull(), "truncation": NSNull(), "line_count": NSNull()],
                                 "style": ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull(), "backgroundColor": rgba(codeManager?.fill), "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 5,
                                           "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [5,5,5,5], "opacity": (view as? QuoteTextView)?.measuredOpacity ?? Double(view.alphaValue), "background_image": "none", "shadow": []],
                                 "attributes": ["source": "InlineCodeLayoutManager.drawBackground", "group": group, "horizontal_padding": 5, "vertical_padding": 1]])
                }
            }
            if attributes[.relicCodePadding] as? Bool == true { return }
            let text = (storage.string as NSString).substring(with: range)
            guard !text.isEmpty else { return }
            let glyphs = manager.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
            let inkEnvelope = manager.boundingRect(forGlyphRange: glyphs, in: container)
            let advances = NativeTextGeometry.advances(manager, container: container, characters: range)
            let drawing = manager as? NativeGlyphLayoutManager
            let drawnFonts = drawing?.fontEvidence(for: range, in: view)
                ?? ["status": "unmeasured", "reason": "No actual glyph callback observer", "fonts": NSNull()]
            let textOutline = TextOutlineCapture.inspect(view, range: range)
            let typographic = drawnFonts["status"] as? String == "measured-current-draw"
                ? drawing?.lastDraw.map { NativeTypographicGeometry.measure(advances: advances, draw: $0, characters: range, origin: view.textContainerOrigin) } : nil
            let measured = typographic?.envelope == nil ? advances : typographic!
            let rect = (measured.envelope ?? inkEnvelope).offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y)
            var lines: [[String: Double]] = []
            manager.enumerateLineFragments(forGlyphRange: glyphs) { fragment, used, _, lineRange, _ in
                let intersection = NSIntersectionRange(glyphs, lineRange)
                if intersection.length > 0 { lines.append(box(manager.boundingRect(forGlyphRange: intersection, in: container).offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y))) }
            }
            if measured.envelope != nil { lines = measured.rectangles.map { box($0.offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y)) } }
            let paragraph = attributes[.paragraphStyle] as? NSParagraphStyle
            // A multi-line clamp still wraps paragraphs before the final line.
            // Keep its paragraph wrapping and its container's final-line
            // truncation as independent measured native configuration values.
            let mode = container.maximumNumberOfLines == 1 ? container.lineBreakMode : paragraph?.lineBreakMode ?? container.lineBreakMode
            let tailMode = container.maximumNumberOfLines > 0 ? container.lineBreakMode : mode
            let wrap = mode == .byCharWrapping ? "character" : mode == .byWordWrapping ? "word" : "none"
            let truncation = [.byTruncatingHead, .byTruncatingMiddle, .byTruncatingTail].contains(tailMode) ? "ellipsis" : tailMode == .byClipping ? "clip" : "none"
            let font = attributes[.font] as? NSFont ?? view.font
            let measuredSizes = Set(fonts.map { Double($0.pointSize) })
            let measuredWeights = Set(fonts.map { cssWeight($0) })
            let breaks = NativeLineBreaks.inspect(view, range: range)
            let accessibleSpan = RelicAXText(view, range)
            let accessibleText = accessibleSpan.map { NativeInlineCode.source($0) }
            var measuredLayout: [String: Any] = ["wrap": wrap, "truncation": truncation, "line_count": lines.filter { ($0["width"] ?? 0) > 0 && ($0["height"] ?? 0) > 0 }.count]
            measuredLayout.merge(breaks.layout, uniquingKeysWith: { _, actual in actual })
            rows.append(["text": text, "range": ["location": range.location, "length": range.length],
                "local_rect": NSValue(rect: rect), "lines": lines,
                "text_bounds_quantity": typographic?.envelope != nil ? "native-insertion-advance-and-actual-font-typographic-extent" : advances.envelope == nil ? "glyph-envelope; advance unmeasured" : "native-line-insertion-advance-range",
                "native_insertion_geometry": advances.lines, "native_ink_envelope": box(inkEnvelope),
                "native_typographic_geometry": typographic.map { ["complete": $0.complete, "lines": $0.lines] as [String: Any] } as Any? ?? NSNull(),
                "native_line_break_configuration": ["paragraph_mode": paragraph?.lineBreakMode.rawValue as Any? ?? NSNull(),
                    "container_mode": container.lineBreakMode.rawValue, "maximum_lines": container.maximumNumberOfLines],
                "kind": (view as? ReferenceLabelView)?.textGlyphIcon == true ? "icon" : attributes[.link] == nil ? "text" : "link",
                "icon": (view as? ReferenceLabelView)?.textGlyphIcon == true ? ["source": "text-glyph", "glyph": text] as Any : NSNull(),
                "layout": measuredLayout, "line_break_configuration": breaks.evidence,
                "native_attribute_runs": attributeRuns,
                "native_font_drawing": drawnFonts,
                "native_text_outline": textOutline.evidence,
                "native_accessible_range": ["source": "actual AX attributed string for the rendered source range",
                    "value": accessibleText as Any? ?? NSNull(), "matches_rendered_text": accessibleText == text],
                "native_font_weight_configuration": ["value": attributes[.relicConfiguredFontWeight] ?? NSNull(),
                    "source": "actual native attributed text style input", "quantity": "configured weight, not resolved font weight or synthetic paint"],
                "native_structure": NativeElementStructure.evidence(view, parent: (view as? ReferenceLabelView)?.productionParent),
                "native_reshaped_fonts": reshapedFonts(storage.attributedSubstring(from: range)),
                "span_source": attributes[.relicLabelSpan] ?? "native-attributed-text-boundary",
                "style": ["fontSize": measuredSizes.count == 1 ? measuredSizes.first! as Any : NSNull(),
                          "fontWeight": measuredWeights.count == 1 ? measuredWeights.first! as Any : NSNull(),
                          "fontFamily": font?.familyName as Any? ?? NSNull(),
                          "rendered_fonts": drawnFonts["fonts"] ?? NSNull(),
                          "color": rgba(attributes[.foregroundColor] as? NSColor ?? view.textColor),
                          "backgroundColor": rgba(attributes[.backgroundColor] as? NSColor ?? .clear),
                          "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0],
                          "opacity": (view as? ReferenceLabelView)?.measuredOpacity ?? (view as? QuoteTextView)?.measuredOpacity ?? Double(view.alphaValue),
                          "background_image": "none", "shadow": attributes[.shadow] == nil ? [] as Any : NSNull(),
                          "outline": textOutline.paint],
                "attributes": Dictionary(uniqueKeysWithValues: attributes.map { ($0.key.rawValue, String(describing: $0.value)) })])
            if let group = attributes[.relicCodeGroup] as? String, let parent = codeParents[group] { rows[rows.count - 1]["parent_run"] = parent }
        }
        return rows
    }
    static func write(window: NSWindow, png: URL, item: Node, language: String, theme: String, captureErrors: [String] = []) throws {
        var result: Result<Void, Error>!
        (window.contentView?.effectiveAppearance ?? window.effectiveAppearance).performAsCurrentDrawingAppearance {
            result = Result { try writeMeasured(window: window, png: png, item: item, language: language, theme: theme, captureErrors: captureErrors) }
        }
        try result.get()
    }
    private static func writeMeasured(window: NSWindow, png: URL, item: Node, language: String, theme: String, captureErrors: [String]) throws {
        guard let content = window.contentView, let bitmap = NSBitmapImageRep(data: try Data(contentsOf: png)) else { throw RelicError.message("Cannot inspect captured native image") }
        try JSONSerialization.data(withJSONObject: ScrollGeometryTrace.receipt(), options: [.sortedKeys])
            .write(to: png.deletingPathExtension().appendingPathExtension("native-scroll.json"))
        let contentScreen = window.convertToScreen(content.convert(content.bounds, to: nil))
        let viewport = NSRect(origin: .zero, size: content.bounds.size)
        var raw: [[String: Any]] = [], elements: [[String: Any]] = [], seen = Set<ObjectIdentifier>()
        let regions = ElementRegionProbe.regions(in: contentScreen)
        func region(_ rect: NSRect, fallback: String) -> String {
            let point = NSPoint(x: rect.midX, y: rect.midY)
            return regions.filter { $0.rect.contains(point) }.min(by: { $0.rect.width * $0.rect.height < $1.rect.width * $1.rect.height })?.name ?? fallback
        }
        func visit(_ value: Any, path: String, parent: String?, inheritedRegion: String, clip: NSRect, suppressElements: Bool = false, scrollbarOwner: ReferenceScroller? = nil) {
            let object = value as AnyObject
            let attributes = RelicAXRead(object)
            let ax = Node(attributes)
            guard seen.insert(ObjectIdentifier(object)).inserted else { return }
            let role = ax["role"].text
            let scroller = (object as? ReferenceScroller) ?? scrollbarOwner
            let isThumb = role == "AXValueIndicator" && scroller != nil
            let axRect = topLeft((attributes["frame"] as? NSValue)?.rectValue ?? .zero, in: contentScreen)
            let paintedScreen = (role == "AXScrollBar" || isThumb) ? scroller.flatMap { ScrollbarCapture.screenBounds($0, thumb: isThumb) } : nil
            let rect = paintedScreen.map { topLeft($0, in: contentScreen) } ?? axRect
            let nativeClip = ((object as? NSView) ?? scroller).flatMap { NativeVisibility.screenClip($0, limitingToBounds: false) }
            let activeClip = nativeClip.map { $0.isNull ? NSRect.null : clip.intersection(topLeft($0, in: contentScreen)) } ?? clip
            let visibleRect = rect.intersection(activeClip)
            let label = ax["label"].text, title = ax["title"].text, valueText = string(attributes["value"])
            let accessibleName = Self.accessibleName(role: role, label: label, value: valueText)
            let isIcon = role == "AXButton" && ax["identifier"].text.hasPrefix("relic-icon-button/")
            let elementKind = isThumb ? "scrollbar-thumb" : ax["identifier"].text.hasPrefix("relic-state-dot/") ? "state-dot" : ax["identifier"].text.hasPrefix("relic-divider/") ? "divider" : ax["identifier"].text.hasPrefix("relic-resize-handle/") ? "resize-handle" : isIcon ? "icon-button" : ax["identifier"].text.hasPrefix("relic-toggle/") ? "toggle" : ax["identifier"].text.hasPrefix("relic-avatar/") ? "avatar" : ax["identifier"].text.hasPrefix("relic-chart-node/") ? "chart-node" : ax["identifier"].text.hasPrefix("relic-tab/") ? "tab" : ax["identifier"].text.hasPrefix("relic-menu-item/") ? "menu-item" : ax["identifier"].text.hasPrefix("relic-chip/") ? "chip" : ax["identifier"].text.hasPrefix("relic-badge/") ? "badge" : ax["identifier"].text.hasPrefix("relic-list-row/") || ax["identifier"].text.hasPrefix("relic-org/") ? "list-row" : kind(role)
            let text: String
            if isIcon || ax["identifier"].text == "relic-profile-button" || ax["identifier"].text.hasPrefix("relic-badged-button/") || ax["identifier"].text.hasPrefix("relic-row/") || ["region", "image", "divider", "chart-node", "avatar", "menu-item", "list-row", "resize-handle", "toggle"].contains(elementKind) { text = "" }
            else if elementKind == "input" { text = valueText.isEmpty ? ax["placeholder"].text : valueText }
            else if elementKind == "dropdown" { text = valueText }
            else if ["AXRadioButton", "AXCheckBox"].contains(role), let actualTitle = Self.nativeButtonTitle(object) { text = actualTitle }
            else { text = !valueText.isEmpty && role == "AXStaticText" ? valueText : !title.isEmpty ? title : label }
            let identifier = ax["identifier"].text
            let textRegion = (object as? ReferenceLabelView)?.productionRegion ?? (object as? QuoteTextView)?.productionRegion
            let assignedRegion = path == "window" ? "window" : Self.assignedRegion(identifier: identifier, textRegion: textRegion, inherited: inheritedRegion, geometric: region(rect, fallback: inheritedRegion))
            let visible = !ax["hidden"].flag && !visibleRect.isNull && visibleRect.width > 0 && visibleRect.height > 0
            var node: [String: Any] = ["id": path, "parent": parent as Any? ?? NSNull(), "role": role, "subrole": ax["subrole"].text, "kind": elementKind, "text": text, "name": label, "title": title, "value": valueText, "placeholder": ax["placeholder"].text, "identifier": ax["identifier"].text, "help": ax["help"].text, "region": assignedRegion, "rect": box(rect), "visibleRect": visibleRect.isNull ? NSNull() : box(visibleRect), "visible": visible, "axElement": ax["element"].flag, "order": raw.count, "source": "live-AppKit-AX-selectors", "class": String(describing: type(of: object))]
            node["state"] = ["enabled": attributes["enabled"] ?? NSNull(), "focused": attributes["focused"] ?? NSNull(), "selected": attributes["selected"] ?? NSNull(), "expanded": attributes["expanded"] ?? NSNull(), "indeterminate": ["AXCheckBox", "AXRadioButton"].contains(role) ? (attributes["value"] as? NSNumber).map { $0.intValue == 2 } as Any? ?? NSNull() : NSNull(), "checked": ["AXCheckBox", "AXRadioButton"].contains(role) ? (attributes["value"] as? NSNumber).map { $0.intValue == 1 } as Any? ?? NSNull() : NSNull()]
            if let viewport = object as? NSScrollView, let binding = ConversationKeyboardMount.observation(for: viewport) {
                node["native_keyboard_scroll"] = binding
            }
            node["style"] = style(object, text: text)
            if let logo = object as? NativeLogoView {
                node["native_image_draw"] = logo.lastDraw as Any? ?? NSNull()
                node["icon"] = logo.currentPaint() as Any? ?? NSNull()
                node["native_image_current_binding"] = ["view_identity": String(describing: ObjectIdentifier(logo)),
                    "window_identity": logo.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                    "local_bounds": box(logo.bounds), "paint_available": logo.currentPaint() != nil,
                    "quantity": "Current mounted view and completed native draw; final PNG contribution remains separate"]
                if let draw = logo.lastDraw {
                    var imageStyle = node["style"] as! [String: Any]
                    imageStyle.merge(["backgroundColor": [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0,
                        "borderRadius": draw["outer_clip_radius"]!, "corner_radii": Array(repeating: draw["outer_clip_radius"]!, count: 4),
                        "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4),
                        "opacity": NativeVisibility.opacity(logo), "background_image": "none", "shadow": []], uniquingKeysWith: { _, actual in actual })
                    node["style"] = imageStyle
                }
            }
            if let scroller, role == "AXScrollBar" || isThumb {
                node["ax_hit_bounds"] = box(axRect)
                ScrollbarCapture.apply(to: &node, scroller: scroller, thumb: isThumb)
            }
            node["pixelSamples"] = visible ? samples(visibleRect, bitmap: bitmap) : []
            node["native_visible_bounds"] = nativeClip.map { $0.isNull ? NSNull() as Any : box(topLeft($0, in: contentScreen)) } ?? NSNull()
            node["selectorEvidence"] = ["child_count": ax["child_count"].integer, "navigation_child_count": attributes["navigation_child_count"] ?? NSNull(), "child_classes": ax["child_classes"].rows.map(\.text), "errors": ax["errors"].rows.map(\.text), "element": attributes["element"] ?? NSNull(), "interaction": attributes["interaction"] ?? NSNull()]
            node["object_identity"] = String(describing: ObjectIdentifier(object))
            node["name"] = accessibleName
            node["native_ax_label"] = label
            node["native_name_source"] = label.isEmpty && role == "AXStaticText" ? "AXValue of static text" : "AXLabel"
            if let handle = object as? TextAreaResizeView { node["native_resize_handle"] = handle.observation() }
            if let popup = object as? ReferencePopUpButton { node["native_dropdown_arrow"] = popup.arrowDraw as Any? ?? NSNull() }
            if let scroller = object as? ReferenceScroller { node["native_scrollbar_paint"] = scroller.lastPaint as Any? ?? NSNull() }
            if let text = object as? NSTextView {
                node["native_text_layout_system"] = text.textLayoutManager == nil ? "TextKit1" : "TextKit2"
                if text.textLayoutManager == nil, let drawing = text.layoutManager as? NativeGlyphLayoutManager {
                    node["native_glyph_drawing"] = drawing.lastDraw as Any? ?? NSNull()
                }
            }
            if let view = object as? NSView {
                node["native_view_geometry"] = ["frame": box(view.frame), "bounds": box(view.bounds), "flipped": view.isFlipped,
                    "screen_bounds": view.window.map { box($0.convertToScreen(view.convert(view.bounds, to: nil))) } as Any? ?? NSNull(),
                    "superview_identity": view.superview.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()]
            }
            if let editor = object as? ComposerTextView { EditableTextCapture.attach(to: &node, view: editor, canvas: contentScreen) }
            let textView = (object as? NSTextView).flatMap { $0.isEditable || $0.textLayoutManager != nil ? nil : $0 }
            if textView != nil { node["projection_reason"] = "Read-only TextKit container; individual rendered attribute runs own the text" }
            if suppressElements { node["projection_reason"] = "Raw AX child retained; rendered text is owned by the TextKit run projection" }
            if object is ChartEdgeProbe.EdgeView { node["projection_reason"] = "Raw path AX retained; the same native path's measured stroke projection supplies its visible geometry" }
            raw.append(node)
            if visible && ax["element"].flag && textView == nil && !suppressElements && !(object is ChartEdgeProbe.EdgeView) { elements.append(node) }
            if let textView, !suppressElements, let textWindow = textView.window {
                for (index, run) in textRuns(textView).enumerated() {
                    let screen = textWindow.convertToScreen(textView.convert((run["local_rect"] as! NSValue).rectValue, to: nil))
                    let boxRect = topLeft(screen, in: contentScreen), visible = boxRect.intersection(activeClip)
                    var projected: [String: Any] = ["id": path + "/text-" + String(index), "parent": path, "kind": run["kind"]!, "region": assignedRegion,
                        "text": run["text"]!, "name": run["text"] as? String == accessibleName ? accessibleName : "", "rect": box(boxRect), "visibleRect": visible.isNull ? NSNull() : box(visible),
                        "style": run["style"]!, "layout": run["layout"]!, "source": "live-TextKit-layout",
                        "state": ["enabled": textView.isSelectable, "focused": false, "selected": NSNull(), "expanded": NSNull(), "checked": NSNull()],
                        "visible": !visible.isNull && visible.width > 0 && visible.height > 0,
                        "pixelSamples": samples(visible, bitmap: bitmap)]
                    if let parent = run["parent_run"] as? Int { projected["parent"] = path + "/text-" + String(parent) }
                    var evidence = run; evidence.removeValue(forKey: "local_rect"); evidence["local_bounds"] = box((run["local_rect"] as! NSValue).rectValue)
                    projected["projection"] = evidence
                    projected["icon"] = run["icon"] ?? NSNull()
                    projected["native_structure"] = run["native_structure"]
                    if let nativeLabel = textView as? ReferenceLabelView, nativeLabel.hasExplicitAccessibilityName,
                       let actualLabel = attributes["label"] as? String {
                        projected["name"] = actualLabel
                        projected["native_name_source"] = "Actual explicit AXLabel of the native text element; AXValue retains its visible text"
                    } else if let accessible = run["native_accessible_range"] as? [String: Any],
                       accessible["matches_rendered_text"] as? Bool == true, let value = accessible["value"] as? String {
                        projected["name"] = value
                        projected["native_name_source"] = "AX attributed range value of the read-only text fragment"
                    }
                    projected["native_name_evidence"] = ["owner_role": role, "owner_label": label, "owner_value": valueText, "complete_owner_text_matches_run": run["text"] as? String == accessibleName]
                    projected["text_bounds"] = (run["lines"] as! [[String: Double]]).map { line in
                        let local = NSRect(x: line["x"]!, y: line["y"]!, width: line["width"]!, height: line["height"]!)
                        return box(topLeft(textWindow.convertToScreen(textView.convert(local, to: nil)), in: contentScreen))
                    }
                    if let label = textView as? ReferenceLabelView, let owner = label.productionOwner { projected["production_owner"] = owner }
                    if let label = textView as? ReferenceLabelView, let owner = label.productionControlLabelOwner { projected["native_control_label_owner"] = owner }
                    raw.append(projected)
                    if projected["visible"] as? Bool == true { elements.append(projected) }
                }
            }
            let childClip = role == "AXScrollArea" ? activeClip.intersection(rect) : activeClip
            for (index, child) in RelicAXChildren(object).enumerated() { visit(child, path: path + "/" + String(index), parent: path, inheritedRegion: assignedRegion, clip: childClip, suppressElements: suppressElements || textView != nil, scrollbarOwner: scroller) }
            // Embedded AppKit controls can be absent from the hosting view's AX
            // children. Inspect their real view ancestry too; identity deduplication
            // prevents emitting a control twice when AX already exposed it.
            if let view = object as? NSView {
                for (index, child) in view.subviews.enumerated() {
                    visit(child, path: path + "/view-" + String(index), parent: path, inheritedRegion: assignedRegion, clip: childClip, suppressElements: suppressElements || textView != nil, scrollbarOwner: scroller)
                }
            }
        }
        visit(content, path: "window", parent: nil, inheritedRegion: "window", clip: viewport)
        for (index, child) in NSApp.windows.filter({ $0 !== window && $0.isVisible && $0.contentView != nil }).enumerated() {
            visit(child.contentView!, path: "surface-" + String(index), parent: nil, inheritedRegion: child === window.attachedSheet ? "dialog" : "menu", clip: viewport)
        }
        var surfaceGaps: [String] = []
        func bounds(_ node: [String: Any]) -> NSRect {
            guard let rect = node["rect"] as? [String: Double], let x = rect["x"], let y = rect["y"], let width = rect["width"], let height = rect["height"] else { return .null }
            return NSRect(x: x, y: y, width: width, height: height)
        }
        let surfaces = SurfacePaintProbe.snapshots(in: contentScreen) + TypingIndicatorView.snapshots(in: contentScreen)
        for surface in surfaces {
            let rect = (surface["rectValue"] as! NSValue).rectValue, visible = rect.intersection(Self.rect(surface["nativeVisibleBounds"])).intersection(viewport)
            guard !visible.isNull && visible.width > 0 && visible.height > 0 else { continue }
            guard (surface["style"] as? [String: Any])?["opacity"] as? Double != 0 else { continue }
            let owner = surface["owner"] as? String
            let candidates = elements.indices.filter { index in
                if let owner { return elements[index]["identifier"] as? String == owner }
                let other = bounds(elements[index])
                return ["button", "icon-button", "tab", "menu-item", "region", "card", "list-row", "chip", "badge", "avatar"].contains(elements[index]["kind"] as? String ?? "") &&
                    abs(rect.minX - other.minX) < 0.5 && abs(rect.minY - other.minY) < 0.5 &&
                    abs(rect.width - other.width) < 0.5 && abs(rect.height - other.height) < 0.5
            }
            let style = surface["style"] as! [String: Any]
            if candidates.count == 1, let index = candidates.first {
                var existing = elements[index]["style"] as! [String: Any]
                existing.merge(style, uniquingKeysWith: { _, actual in actual }); elements[index]["style"] = existing
                NativeSurfaceGeometry.attach(to: &elements[index], surface: surface, viewport: viewport)
                if let measuredRegion = surface["region"] as? String { elements[index]["region"] = measuredRegion }
                elements[index]["surface_evidence"] = surface["evidence"]!
                elements[index]["native_structure"] = surface["native_structure"]
                elements[index]["native_visible_bounds"] = surface["nativeVisibleBounds"]!
                if let kind = surface["kind"] as? String, elements[index]["kind"] as? String == "region" { elements[index]["kind"] = kind }
                if let hovered = surface["hovered"] as? Bool { elements[index]["hovered"] = hovered }
                if let selected = surface["selected"] as? Bool { elements[index]["recorded_selected"] = selected }
                if let expanded = surface["expanded"] as? Bool { elements[index]["recorded_expanded"] = expanded }
                if let current = surface["current"] as? Bool { elements[index]["recorded_current"] = current }
                if let unread = surface["unread"] as? Bool { elements[index]["recorded_unread"] = unread }
            } else if let kind = surface["kind"] as? String {
                var paintedStyle: [String: Any] = ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull()]
                paintedStyle.merge(style, uniquingKeysWith: { _, actual in actual })
                let node: [String: Any] = ["id": "surface-paint/" + String(elements.count), "parent": NSNull(), "kind": kind,
                    "identifier": owner as Any? ?? NSNull(),
                    "native_structure": surface["native_structure"] ?? NSNull(),
                    "text": "", "name": "", "region": surface["region"] ?? region(rect, fallback: "window"), "rect": box(rect), "visibleRect": box(visible),
                    "visible": true, "style": paintedStyle, "source": "live-native-surface-probe", "surface_evidence": surface["evidence"]!, "native_visible_bounds": surface["nativeVisibleBounds"]!,
                    "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()],
                    "pixelSamples": samples(visible, bitmap: bitmap)]
                raw.append(node); elements.append(node)
            } else {
                surfaceGaps.append("Unresolved production ButtonStyle paint ownership at " + String(describing: surface["bounds"]!) + "; candidates=" + String(candidates.count))
            }
        }
        // An AX-ignored avatar/badge can still own an actual native label.
        // Resolve only after its measured paint surface has been collected.
        surfaceGaps.append(contentsOf: ElementOwnership.attachLabels(to: &elements))
        let paint = ElementPaintProbe.snapshots(in: contentScreen)
        for sample in paint {
            let rect = topLeft((sample["screenRect"] as! NSValue).rectValue, in: contentScreen), visible = rect.intersection(Self.rect(sample["nativeVisibleBounds"])).intersection(viewport)
            guard !visible.isNull && visible.width > 0 && visible.height > 0 else { continue }
            guard sample["opacity"] as? Double != 0 else { continue }
            let owner = (sample["owner"] as? String).flatMap { identifier in elements.firstIndex { $0["identifier"] as? String == identifier } }
            let parent = owner.map { elements[$0]["id"]! } ?? NSNull()
            var evidence = sample["evidence"] as! [String: Any]
            evidence["owner_accessibility_identifier"] = sample["owner"]!
            let node: [String: Any] = ["id": sample["id"]!, "parent": parent, "kind": "icon", "text": "", "name": "",
                "native_structure": sample["native_structure"] ?? NSNull(),
                "region": sample["region"] ?? region(rect, fallback: "window"), "rect": box(rect), "visibleRect": box(visible),
                "visible": true, "source": "live-CoreGraphics-icon-draw", "projection": evidence, "native_visible_bounds": sample["nativeVisibleBounds"]!,
                "style": ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": sample["foreground"]!,
                          "backgroundColor": [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0],
                          "opacity": sample["opacity"]!, "background_image": "none", "shadow": [], "outline": sample["outline"]!,
                          "stroke_dash": [], "stroke_dash_offset": 0, "stroke_linecap": "round", "stroke_linejoin": "round", "stroke_width": sample["stroke_width"]!],
                "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()],
                "icon": sample["icon"]!, "pixelSamples": samples(visible, bitmap: bitmap)]
            raw.append(node)
            if let owner { elements.insert(node, at: owner + 1) } else { elements.append(node) }
        }

        var chartEdges: [[String: Any]] = []
        let edgeSamples = ChartEdgeProbe.snapshots(in: contentScreen)
        for sample in edgeSamples {
            let rect = (sample["rectValue"] as! NSValue).rectValue, width = sample["width"] as! Double
            // A vertical or horizontal path can have a zero-area geometric box
            // while its stroked paint is visible. Keep the actual path bounds.
            let nativeClip = Self.rect(sample["nativeVisibleBounds"]).intersection(viewport)
            let painted = rect.insetBy(dx: -width / 2, dy: -width / 2).intersection(nativeClip)
            guard !painted.isNull && painted.width > 0 && painted.height > 0 else { continue }
            guard sample["opacity"] as? Double != 0 else { continue }
            let evidence = sample["evidence"] as! [String: Any]
            let sx = evidence["scale_x"] as! Double, sy = evidence["scale_y"] as! Double
            if abs(sx - sy) > 0.0001 { surfaceGaps.append("Nonuniform chart edge transform needs directional stroke geometry: " + (sample["id"] as! String)) }
            if !(sample["name"] is String) { surfaceGaps.append("Actual chart edge AX label unavailable: " + (sample["id"] as! String)) }
            let clipped = rect.intersection(nativeClip)
            let node: [String: Any] = ["id": sample["id"]!, "parent": NSNull(), "kind": "chart-edge", "text": "", "name": sample["name"]!, "region": sample["region"] ?? region(rect, fallback: "dialog"), "rect": box(rect), "visibleRect": clipped.isNull ? NSNull() : box(clipped), "visible": true,
                "source": "live-native-chart-path", "projection": evidence, "icon": sample["icon"]!, "hovered": false, "native_visible_bounds": sample["nativeVisibleBounds"]!,
                "style": ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": sample["color"]!, "backgroundColor": [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_styles": ["none","none","none","none"], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0], "opacity": sample["opacity"]!, "background_image": "none", "shadow": [], "stroke_width": abs(sx - sy) > 0.0001 ? NSNull() : width as Any,
                          "stroke_dash": abs(sx - sy) > 0.0001 ? NSNull() : (evidence["stroke_dash"] as! [Double]).map { $0 * sx } as Any, "stroke_dash_offset": 0, "stroke_linecap": evidence["stroke_linecap"]!, "stroke_linejoin": evidence["stroke_linejoin"]!],
                "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()], "pixelSamples": samples(painted, bitmap: bitmap)]
            raw.append(node); chartEdges.append(node)
        }
        // ChartView's native ZStack draws edges before node controls. Preserve
        // that production layer order when supplementing AX with path paint.
        elements.insert(contentsOf: chartEdges, at: elements.firstIndex { $0["kind"] as? String == "chart-node" } ?? elements.count)
        surfaceGaps.append(contentsOf: ElementOwnership.attachMeasuredChildren(to: &elements))
        surfaceGaps.append(contentsOf: NativeControlState.attach(to: &elements))

        let stem = png.deletingPathExtension()
        let metadata: [String: Any] = ["version": 1, "client": "macos", "caseId": item["id"].text, "scene": item["scene"].text, "language": language, "theme": theme, "viewport": ["width": bitmap.pixelsWide, "height": bitmap.pixelsHigh], "coordinateSpace": "content-top-left-logical-pixels", "screenshot": png.lastPathComponent]
        var unmeasured = ["Paint-only SwiftUI decoration coverage beyond instrumented path icons", "Exact opaque-overlay occlusion", "Reading order for paint without an AX owner"]
        unmeasured.append(contentsOf: surfaceGaps)
        if raw.count < 2 || elements.isEmpty { unmeasured.append("AX extraction returned no descendant controls") }
        if RelicAXChildren(content).isEmpty { unmeasured.append("SwiftUI hosting view has no virtual AX descendants; AppKit subviews alone are incomplete") }
        var orders: [String: Int] = [:]
        let emittedIDs = Set(elements.compactMap { $0["id"] as? String })
        let rawParents = Dictionary(uniqueKeysWithValues: raw.compactMap { node -> (String, String)? in
            guard let id = node["id"] as? String, let parent = node["parent"] as? String else { return nil }; return (id, parent)
        })
        func emittedParent(_ node: [String: Any]) -> Any {
            var parent = node["parent"] as? String
            while let id = parent { if emittedIDs.contains(id) { return id }; parent = rawParents[id] }
            return NSNull()
        }
        let canonical = elements.map { node -> [String: Any] in
            let id = node["id"] as! String, region = node["region"] as! String, kind = node["kind"] as! String
            let sourceStyle = node["style"] as! [String: Any], sourceState = node["state"] as! [String: Any]
            let text = node["text"] as! String
            let styleKeys = ["font_size": "fontSize", "font_weight": "fontWeight", "foreground": "color", "background": "backgroundColor", "border_color": "borderColor", "border_width": "borderWidth", "corner_radius": "borderRadius",
                             "border_widths": "border_widths", "border_styles": "border_styles", "border_colors": "border_colors", "corner_radii": "corner_radii", "opacity": "opacity", "background_image": "background_image", "shadow": "shadow", "outline": "outline"]
            var actualStyle: [String: Any] = [:]
            for (key, original) in styleKeys {
                let value = sourceStyle[original] ?? NSNull()
                let applicable = (!key.hasPrefix("font_") || !text.isEmpty) && (key != "foreground" || !text.isEmpty || ["icon", "chart-edge"].contains(kind))
                actualStyle[key] = applicable ? value : NSNull()
                if applicable && value is NSNull { unmeasured.append(id + ":style." + key) }
            }
            actualStyle["rendered_fonts"] = text.isEmpty ? NSNull() : sourceStyle["rendered_fonts"] ?? NSNull()
            if !text.isEmpty && (sourceStyle["rendered_fonts"] == nil || sourceStyle["rendered_fonts"] is NSNull) { unmeasured.append(id + ":style.rendered_fonts") }
            if ["icon", "chart-edge"].contains(kind) {
                for key in ["stroke_width", "stroke_dash", "stroke_dash_offset", "stroke_linecap", "stroke_linejoin"] {
                    actualStyle[key] = sourceStyle[key] ?? NSNull()
                    if sourceStyle[key] == nil || sourceStyle[key] is NSNull { unmeasured.append(id + ":style." + key) }
                }
            }
            let isControl = ["button", "icon-button", "input", "checkbox", "toggle", "tab", "dropdown", "link", "menu-item", "chart-node", "list-row", "resize-handle", "scrollbar", "scrollbar-thumb"].contains(kind)
            let order = orders[region, default: 0]; orders[region] = order + 1
            let pointer = NSEvent.mouseLocation
            let pointerOutside = !contentScreen.contains(pointer)
            var state: [String: Any] = ["enabled": isControl ? sourceState["enabled"]! : NSNull(), "selected": node["recorded_selected"] ?? (["tab", "list-row"].contains(kind) ? sourceState["selected"]! : NSNull()), "checked": ["checkbox", "toggle"].contains(kind) ? sourceState["checked"]! : NSNull(), "indeterminate": ["checkbox", "toggle"].contains(kind) ? sourceState["indeterminate"] ?? NSNull() : NSNull(), "expanded": node["recorded_expanded"] ?? (node["role"] as? String == "AXDisclosureTriangle" ? sourceState["expanded"]! : NSNull()), "focused": isControl ? sourceState["focused"]! : NSNull(), "hovered": node["hovered"] ?? (pointerOutside ? false as Any : NSNull()), "unread": node["recorded_unread"] ?? NSNull(), "current": node["recorded_current"] ?? NSNull()]
            if ["scrollbar", "scrollbar-thumb"].contains(kind) {
                state["orientation"] = sourceState["orientation"] ?? NSNull()
                state["scroll_position"] = sourceState["scroll_position"] ?? NSNull()
            }
            if let actualControl = node["native_control_state"] as? [String: Any] {
                state.merge(actualControl, uniquingKeysWith: { _, measured in measured })
            }
            if let keyboard = node["native_keyboard_scroll"] as? [String: Any] {
                state["enabled"] = keyboard["enabled"] ?? NSNull()
                state["focused"] = keyboard["focused"] ?? NSNull()
            }
            if !pointerOutside && node["hovered"] == nil { unmeasured.append(id + ":state.hovered") }
            if !text.isEmpty && node["layout"] == nil { unmeasured.append(id + ":layout") }
            if let projection = node["projection"] as? [String: Any],
               projection["native_insertion_geometry"] != nil,
               projection["text_bounds_quantity"] as? String != "native-line-insertion-advance-range" {
                unmeasured.append(id + ":text.advance_geometry")
            }
            var evidence = node
            evidence["font_family"] = sourceStyle["fontFamily"] ?? NSNull()
            evidence["raw_node_id"] = id
            evidence["pointer_screen"] = ["x": pointer.x, "y": pointer.y]
            evidence["outline"] = (node["surface_evidence"] as? [String: Any])?["outline"] ?? NSNull()
            // A control's label receipt does not cover the control's own paint.
            // Only a retained TextKit span can supply its own absence evidence.
            if actualStyle["outline"] as? String == "none", let ownText = (node["projection"] as? [String: Any])?["native_text_outline"] {
                evidence["outline"] = ownText
            }
            if kind == "icon", actualStyle["outline"] as? String == "none",
               let ownIcon = (node["projection"] as? [String: Any])?["native_icon_outline"] {
                evidence["outline"] = ownIcon
            }
            let labelEvidence = node["projection"] as? [String: Any]
                ?? (node["owned_text_evidence"] as? [String: Any])?["projection"] as? [String: Any]
            var measuredLayout = node["layout"] as? [String: Any] ?? ["wrap": NSNull(), "truncation": NSNull(), "line_count": NSNull()]
            let textApplicable = !text.isEmpty || kind == "text"
            if textApplicable, let configuration = labelEvidence?["line_break_configuration"] {
                evidence["line_break_configuration"] = configuration
            } else {
                measuredLayout["break_strategy_version"] = 1
                measuredLayout["normal_break_strategy"] = NSNull(); measuredLayout["emergency_break_strategy"] = NSNull()
                var configuration: [String: Any] = ["source": "current native element measurement",
                    "owner": node["object_identity"] ?? (node["surface_evidence"] as? [String: Any])?["identity"] ?? id,
                    "applicable": textApplicable, "raw": ["native_kind": kind, "native_text": text]]
                if textApplicable { configuration["errors"] = ["No actual paragraph/container break configuration for this native element"] }
                else { configuration["reason"] = "This native element has neither visible text nor text kind under the shared applicability rule" }
                evidence["line_break_configuration"] = configuration
            }
            return ["id": id, "parent": emittedParent(node), "region": region, "order": order, "kind": kind, "text": text, "name": node["name"]!, "bounds": node["rect"]!, "visible_bounds": node["visibleRect"]!, "style": actualStyle, "state": state, "layout": measuredLayout, "icon": node["icon"] ?? NSNull(), "evidence": evidence]
        }
        let normalized: [String: Any] = ["schema_version": 1, "scene_id": item["id"].text, "client": "macos", "viewport": ["width": bitmap.pixelsWide, "height": bitmap.pixelsHigh, "scale": 1], "extraction_errors": captureErrors.map { ["type": "native_scene_action_failed", "detail": $0] }, "coverage": ["raw_nodes": raw.count, "emitted_elements": canonical.count, "unmeasured": unmeasured], "elements": canonical, "raw_tree": stem.appendingPathExtension("ax.json").lastPathComponent]
        // Preserve every measurement while avoiding multi-megabyte indentation
        // in each of the 660 cases. Presentation belongs to the HTML report.
        try JSONSerialization.data(withJSONObject: normalized, options: [.sortedKeys]).write(to: stem.appendingPathExtension("elements.json"))
        var audit = metadata; audit["nodes"] = raw; audit["regions"] = regions.map { ["name": $0.name, "rect": box($0.rect)] }
        audit["surface_probes"] = surfaces.map { surface in var value = surface; value.removeValue(forKey: "rectValue"); return value }
        audit["icon_probes"] = paint.map { sample in var value = sample; value.removeValue(forKey: "screenRect"); return value }
        audit["edge_probes"] = edgeSamples.map { sample in var value = sample; value.removeValue(forKey: "rectValue"); return value }
        try JSONSerialization.data(withJSONObject: audit, options: [.sortedKeys]).write(to: stem.appendingPathExtension("ax.json"))
    }
}

struct ElementRegionProbe: NSViewRepresentable {
    let name: String
    private static let live = NSHashTable<RegionView>.weakObjects()
    func makeNSView(context: Context) -> RegionView { let view = RegionView(); view.name = name; Self.live.add(view); return view }
    func updateNSView(_ view: RegionView, context: Context) { view.name = name }
    static func regions(in content: NSRect) -> [(name: String, rect: NSRect)] {
        live.allObjects.compactMap { view in
            guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor else { return nil }
            let screen = window.convertToScreen(view.convert(view.bounds, to: nil))
            return (view.name, ElementCapture.topLeft(screen, in: content))
        }
    }
    final class RegionView: NSView {
        var name = ""
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func isAccessibilityElement() -> Bool { false }
    }
}

private struct CaptureRegionKey: EnvironmentKey { static let defaultValue = "window" }
extension EnvironmentValues {
    var captureRegion: String { get { self[CaptureRegionKey.self] } set { self[CaptureRegionKey.self] = newValue } }
}
extension View {
    @ViewBuilder func measuredRegion(_ name: String, createsAccessibilityContainer: Bool = true) -> some View {
        let measured = background(ElementRegionProbe(name: name).frame(maxWidth: .infinity, maxHeight: .infinity))
            .environment(\.captureRegion, name)
        if createsAccessibilityContainer {
            measured.accessibilityElement(children: .contain).accessibilityIdentifier("relic-region/" + name)
        } else {
            // The production view already owns a named AX container. Adding
            // another container here duplicates its region and makes actual
            // surface ownership ambiguous. Keep the passive measuring view.
            measured
        }
    }
}
