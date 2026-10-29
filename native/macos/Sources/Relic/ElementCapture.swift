import AppKit
import SwiftUI
import RelicCore
import RelicAX
import CoreText

// Measurements come from the live production accessibility/view tree and PNG.
// This exporter never reads the reference's element data or substitutes its values.
@MainActor enum ElementCapture {
    static func topLeft(_ screen: NSRect, in content: NSRect) -> NSRect {
        NSRect(x: screen.minX - content.minX, y: content.maxY - screen.maxY, width: screen.width, height: screen.height)
    }
    static func box(_ rect: NSRect) -> [String: Double] {
        ["x": Double(rect.minX), "y": Double(rect.minY), "width": Double(rect.width), "height": Double(rect.height)]
    }
    static func kind(_ role: String) -> String {
        switch role {
        case "AXButton", "AXDisclosureTriangle": return "button"
        case "AXStaticText": return "text"
        case "AXTextField", "AXTextArea", "AXSearchField": return "input"
        case "AXCheckBox": return "checkbox"
        case "AXRadioButton": return "tab"
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
        case "AXGroup", "AXLayoutArea": return "region"
        default: return "unknown"
        }
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
    static func renderedFonts(_ value: NSAttributedString) -> [[String: Any]] {
        let line = CTLineCreateWithAttributedString(value)
        return (CTLineGetGlyphRuns(line) as! [CTRun]).compactMap { run in
            let attributes = CTRunGetAttributes(run) as NSDictionary
            guard let rawFont = attributes[kCTFontAttributeName] else { return nil }
            let font = rawFont as! CTFont
            return ["family_name": CTFontCopyFamilyName(font) as String, "postscript_name": CTFontCopyPostScriptName(font) as String,
                    "glyph_count": CTRunGetGlyphCount(run), "provider": "CoreText shaping of the native attributed text"]
        }
    }
    private static func style(_ object: AnyObject, text: String) -> [String: Any] {
        var result: [String: Any] = ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull(), "backgroundColor": NSNull(), "borderColor": NSNull(), "borderWidth": NSNull(), "borderRadius": NSNull()]
        var font: NSFont?, foreground: NSColor?, background: NSColor?
        if let textView = object as? NSTextView { font = textView.font; foreground = textView.textColor; if textView.drawsBackground { background = textView.backgroundColor } }
        else if let field = object as? NSTextField { font = field.font; foreground = field.textColor; if field.drawsBackground { background = field.backgroundColor } }
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
            result["rendered_fonts"] = renderedFonts(NSAttributedString(string: text, attributes: [.font: font]))
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
            return ["x": x, "y": y, "rgba": rgba(bitmap.colorAt(x: x, y: y))]
        } }
    }
    static func textRuns(_ view: NSTextView) -> [[String: Any]] {
        var result: [[String: Any]] = []
        view.effectiveAppearance.performAsCurrentDrawingAppearance { result = measuredTextRuns(view) }
        return result
    }
    private static func measuredTextRuns(_ view: NSTextView) -> [[String: Any]] {
        guard let manager = view.layoutManager, let container = view.textContainer, let storage = view.textStorage else { return [] }
        manager.ensureLayout(for: container)
        var rows: [[String: Any]] = []
        storage.enumerateAttributes(in: NSRange(location: 0, length: storage.length), options: []) { attributes, range, _ in
            let text = (storage.string as NSString).substring(with: range)
            guard !text.isEmpty else { return }
            let glyphs = manager.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
            let rect = manager.boundingRect(forGlyphRange: glyphs, in: container).offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y)
            var lines: [[String: Double]] = []
            manager.enumerateLineFragments(forGlyphRange: glyphs) { fragment, used, _, lineRange, _ in
                let intersection = NSIntersectionRange(glyphs, lineRange)
                if intersection.length > 0 { lines.append(box(manager.boundingRect(forGlyphRange: intersection, in: container).offsetBy(dx: view.textContainerOrigin.x, dy: view.textContainerOrigin.y))) }
            }
            let paragraph = attributes[.paragraphStyle] as? NSParagraphStyle
            let mode = container.maximumNumberOfLines > 0 ? container.lineBreakMode : paragraph?.lineBreakMode ?? container.lineBreakMode
            let wrap = mode == .byCharWrapping ? "character" : mode == .byWordWrapping ? "word" : "none"
            let truncation = [.byTruncatingHead, .byTruncatingMiddle, .byTruncatingTail].contains(mode) ? "ellipsis" : mode == .byClipping ? "clip" : "none"
            let font = attributes[.font] as? NSFont ?? view.font
            rows.append(["text": text, "range": ["location": range.location, "length": range.length],
                "local_rect": NSValue(rect: rect), "lines": lines,
                "kind": attributes[.link] == nil ? "text" : "link",
                "layout": ["wrap": wrap, "truncation": truncation, "line_count": lines.count],
                "style": ["fontSize": font.map { Double($0.pointSize) } as Any? ?? NSNull(),
                          "fontWeight": font.map { cssWeight($0) } as Any? ?? NSNull(),
                          "fontFamily": font?.familyName as Any? ?? NSNull(),
                          "rendered_fonts": renderedFonts(storage.attributedSubstring(from: range)),
                          "color": rgba(attributes[.foregroundColor] as? NSColor ?? view.textColor),
                          "backgroundColor": rgba(attributes[.backgroundColor] as? NSColor ?? .clear),
                          "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0],
                          "opacity": (view as? ReferenceLabelView)?.measuredOpacity ?? (view as? QuoteTextView)?.measuredOpacity ?? Double(view.alphaValue),
                          "background_image": "none", "shadow": attributes[.shadow] == nil ? [] as Any : NSNull()],
                "attributes": Dictionary(uniqueKeysWithValues: attributes.map { ($0.key.rawValue, String(describing: $0.value)) })])
        }
        return rows
    }
    static func write(window: NSWindow, png: URL, item: Node, language: String, theme: String) throws {
        var result: Result<Void, Error>!
        (window.contentView?.effectiveAppearance ?? window.effectiveAppearance).performAsCurrentDrawingAppearance {
            result = Result { try writeMeasured(window: window, png: png, item: item, language: language, theme: theme) }
        }
        try result.get()
    }
    private static func writeMeasured(window: NSWindow, png: URL, item: Node, language: String, theme: String) throws {
        guard let content = window.contentView, let bitmap = NSBitmapImageRep(data: try Data(contentsOf: png)) else { throw RelicError.message("Cannot inspect captured native image") }
        let contentScreen = window.convertToScreen(content.convert(content.bounds, to: nil))
        let viewport = NSRect(origin: .zero, size: content.bounds.size)
        var raw: [[String: Any]] = [], elements: [[String: Any]] = [], seen = Set<ObjectIdentifier>()
        let regions = ElementRegionProbe.regions(in: contentScreen)
        func region(_ rect: NSRect, fallback: String) -> String {
            let point = NSPoint(x: rect.midX, y: rect.midY)
            return regions.filter { $0.rect.contains(point) }.min(by: { $0.rect.width * $0.rect.height < $1.rect.width * $1.rect.height })?.name ?? fallback
        }
        func visit(_ value: Any, path: String, parent: String?, inheritedRegion: String, clip: NSRect, suppressElements: Bool = false) {
            let object = value as AnyObject
            let attributes = RelicAXRead(object)
            let ax = Node(attributes)
            guard seen.insert(ObjectIdentifier(object)).inserted else { return }
            let role = ax["role"].text, rect = topLeft((attributes["frame"] as? NSValue)?.rectValue ?? .zero, in: contentScreen)
            let visibleRect = rect.intersection(clip)
            let label = ax["label"].text, title = ax["title"].text, valueText = string(attributes["value"])
            let isIcon = role == "AXButton" && ax["identifier"].text.hasPrefix("relic-icon-button/")
            let elementKind = isIcon ? "icon-button" : ax["identifier"].text.hasPrefix("relic-chart-node/") ? "chart-node" : ax["identifier"].text.hasPrefix("relic-tab/") ? "tab" : kind(role)
            let text: String
            if isIcon || ax["identifier"].text.hasPrefix("relic-row/") || ax["identifier"].text.hasPrefix("relic-org/") || ["region", "image", "divider", "chart-node"].contains(elementKind) { text = "" }
            else if elementKind == "input" { text = valueText.isEmpty ? ax["placeholder"].text : valueText }
            else { text = !valueText.isEmpty && role == "AXStaticText" ? valueText : !title.isEmpty ? title : label }
            let assignedRegion = path == "window" ? "window" : inheritedRegion == "dialog" || inheritedRegion == "menu" ? inheritedRegion : region(rect, fallback: inheritedRegion)
            let visible = !ax["hidden"].flag && !visibleRect.isNull && visibleRect.width > 0 && visibleRect.height > 0
            var node: [String: Any] = ["id": path, "parent": parent as Any? ?? NSNull(), "role": role, "subrole": ax["subrole"].text, "kind": elementKind, "text": text, "name": label, "title": title, "value": valueText, "placeholder": ax["placeholder"].text, "identifier": ax["identifier"].text, "help": ax["help"].text, "region": assignedRegion, "rect": box(rect), "visibleRect": visibleRect.isNull ? NSNull() : box(visibleRect), "visible": visible, "axElement": ax["element"].flag, "order": raw.count, "source": "live-AppKit-AX-selectors", "class": String(describing: type(of: object))]
            node["state"] = ["enabled": attributes["enabled"] ?? NSNull(), "focused": attributes["focused"] ?? NSNull(), "selected": attributes["selected"] ?? NSNull(), "expanded": attributes["expanded"] ?? NSNull(), "checked": ["AXCheckBox", "AXRadioButton"].contains(role) ? (attributes["value"] as? NSNumber).map { $0.intValue == 1 } as Any? ?? NSNull() : NSNull()]
            node["style"] = style(object, text: text)
            node["pixelSamples"] = visible ? samples(visibleRect, bitmap: bitmap) : []
            node["selectorEvidence"] = ["child_count": ax["child_count"].integer, "navigation_child_count": attributes["navigation_child_count"] ?? NSNull(), "child_classes": ax["child_classes"].rows.map(\.text), "errors": ax["errors"].rows.map(\.text), "element": attributes["element"] ?? NSNull()]
            let textView = (object as? NSTextView).flatMap { $0.isEditable ? nil : $0 }
            if textView != nil { node["projection_reason"] = "Read-only TextKit container; individual rendered attribute runs own the text" }
            if suppressElements { node["projection_reason"] = "Raw AX child retained; rendered text is owned by the TextKit run projection" }
            raw.append(node)
            if visible && ax["element"].flag && textView == nil && !suppressElements { elements.append(node) }
            if let textView, !suppressElements, let textWindow = textView.window {
                for (index, run) in textRuns(textView).enumerated() {
                    let screen = textWindow.convertToScreen(textView.convert((run["local_rect"] as! NSValue).rectValue, to: nil))
                    let boxRect = topLeft(screen, in: contentScreen), visible = boxRect.intersection(clip)
                    var projected: [String: Any] = ["id": path + "/text-" + String(index), "parent": path, "kind": run["kind"]!, "region": assignedRegion,
                        "text": run["text"]!, "name": "", "rect": box(boxRect), "visibleRect": visible.isNull ? NSNull() : box(visible),
                        "style": run["style"]!, "layout": run["layout"]!, "source": "live-TextKit-layout",
                        "state": ["enabled": textView.isSelectable, "focused": false, "selected": NSNull(), "expanded": NSNull(), "checked": NSNull()],
                        "visible": !visible.isNull && visible.width > 0 && visible.height > 0,
                        "pixelSamples": samples(visible, bitmap: bitmap)]
                    var evidence = run; evidence.removeValue(forKey: "local_rect"); evidence["local_bounds"] = box((run["local_rect"] as! NSValue).rectValue)
                    projected["projection"] = evidence
                    projected["text_bounds"] = (run["lines"] as! [[String: Double]]).map { line in
                        let local = NSRect(x: line["x"]!, y: line["y"]!, width: line["width"]!, height: line["height"]!)
                        return box(topLeft(textWindow.convertToScreen(textView.convert(local, to: nil)), in: contentScreen))
                    }
                    if let label = textView as? ReferenceLabelView, let owner = label.productionOwner { projected["production_owner"] = owner }
                    raw.append(projected)
                    if projected["visible"] as? Bool == true { elements.append(projected) }
                }
            }
            let childClip = role == "AXScrollArea" ? clip.intersection(rect) : clip
            for (index, child) in RelicAXChildren(object).enumerated() { visit(child, path: path + "/" + String(index), parent: path, inheritedRegion: assignedRegion, clip: childClip, suppressElements: suppressElements || textView != nil) }
            // Embedded AppKit controls can be absent from the hosting view's AX
            // children. Inspect their real view ancestry too; identity deduplication
            // prevents emitting a control twice when AX already exposed it.
            if let view = object as? NSView {
                for (index, child) in view.subviews.enumerated() {
                    visit(child, path: path + "/view-" + String(index), parent: path, inheritedRegion: assignedRegion, clip: childClip, suppressElements: suppressElements || textView != nil)
                }
            }
        }
        visit(content, path: "window", parent: nil, inheritedRegion: "window", clip: viewport)
        for (index, child) in NSApp.windows.filter({ $0 !== window && $0.isVisible && $0.contentView != nil }).enumerated() {
            visit(child.contentView!, path: "surface-" + String(index), parent: nil, inheritedRegion: child === window.attachedSheet ? "dialog" : "menu", clip: viewport)
        }
        // Ownership comes from the production button's identifier passed into its
        // native label. It is not inferred from an expected string or element count.
        let ownedLabels = elements.filter { $0["production_owner"] is String }
        elements.removeAll { $0["production_owner"] is String }
        for var label in ownedLabels.reversed() {
            if let owner = elements.firstIndex(where: { $0["identifier"] as? String == label["production_owner"] as? String }) {
                let identifier = label["production_owner"] as! String
                let simple = identifier.hasPrefix("relic-text-button/") || identifier.hasPrefix("relic-chip-button/")
                if simple && ownedLabels.filter({ $0["production_owner"] as? String == identifier }).count == 1 {
                    var style = elements[owner]["style"] as! [String: Any]
                    let textStyle = label["style"] as! [String: Any]
                    for key in ["fontSize", "fontWeight", "fontFamily", "rendered_fonts", "color"] { style[key] = textStyle[key] ?? NSNull() }
                    elements[owner]["style"] = style; elements[owner]["text"] = label["text"]!
                    elements[owner]["layout"] = label["layout"]!
                    elements[owner]["text_bounds"] = label["text_bounds"]!
                    elements[owner]["owned_text_id"] = label["id"]!
                    elements[owner]["projection_reason"] = "A native button's single simple label is owned by its control; raw TextKit node retained"
                } else {
                    label["parent"] = elements[owner]["id"]!
                    elements.insert(label, at: owner + 1)
                }
            } else { elements.append(label) }
        }
        var surfaceGaps: [String] = []
        func bounds(_ node: [String: Any]) -> NSRect {
            guard let rect = node["rect"] as? [String: Double], let x = rect["x"], let y = rect["y"], let width = rect["width"], let height = rect["height"] else { return .null }
            return NSRect(x: x, y: y, width: width, height: height)
        }
        let surfaces = SurfacePaintProbe.snapshots(in: contentScreen)
        for surface in surfaces {
            let rect = (surface["rectValue"] as! NSValue).rectValue, visible = rect.intersection(viewport)
            guard !visible.isNull && visible.width > 0 && visible.height > 0 else { continue }
            let owner = surface["owner"] as? String
            let candidates = elements.indices.filter { index in
                if let owner { return elements[index]["identifier"] as? String == owner }
                let other = bounds(elements[index])
                return ["button", "icon-button", "tab", "menu-item", "region", "card", "list-row"].contains(elements[index]["kind"] as? String ?? "") &&
                    abs(rect.minX - other.minX) < 0.5 && abs(rect.minY - other.minY) < 0.5 &&
                    abs(rect.width - other.width) < 0.5 && abs(rect.height - other.height) < 0.5
            }
            let style = surface["style"] as! [String: Any]
            if candidates.count == 1, let index = candidates.first {
                var existing = elements[index]["style"] as! [String: Any]
                existing.merge(style, uniquingKeysWith: { _, actual in actual }); elements[index]["style"] = existing
                elements[index]["surface_evidence"] = surface["evidence"]!
                if let kind = surface["kind"] as? String, elements[index]["kind"] as? String == "region" { elements[index]["kind"] = kind }
                if let hovered = surface["hovered"] as? Bool { elements[index]["hovered"] = hovered }
            } else if let kind = surface["kind"] as? String {
                var paintedStyle: [String: Any] = ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull()]
                paintedStyle.merge(style, uniquingKeysWith: { _, actual in actual })
                let node: [String: Any] = ["id": "surface-paint/" + String(elements.count), "parent": NSNull(), "kind": kind,
                    "text": "", "name": "", "region": region(rect, fallback: "window"), "rect": box(rect), "visibleRect": box(visible),
                    "visible": true, "style": paintedStyle, "source": "live-native-surface-probe", "surface_evidence": surface["evidence"]!,
                    "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()],
                    "pixelSamples": samples(visible, bitmap: bitmap)]
                raw.append(node); elements.append(node)
            } else {
                surfaceGaps.append("Unresolved production ButtonStyle paint ownership at " + String(describing: surface["bounds"]!) + "; candidates=" + String(candidates.count))
            }
        }
        let paint = ElementPaintProbe.snapshots(in: contentScreen)
        for sample in paint {
            let rect = topLeft((sample["screenRect"] as! NSValue).rectValue, in: contentScreen), visible = rect.intersection(viewport)
            guard !visible.isNull && visible.width > 0 && visible.height > 0 else { continue }
            let owner = (sample["owner"] as? String).flatMap { identifier in elements.firstIndex { $0["identifier"] as? String == identifier } }
            let parent = owner.map { elements[$0]["id"]! } ?? NSNull()
            var evidence = sample["evidence"] as! [String: Any]
            evidence["owner_accessibility_identifier"] = sample["owner"]!
            let node: [String: Any] = ["id": sample["id"]!, "parent": parent, "kind": "icon", "text": "", "name": "",
                "region": region(rect, fallback: "window"), "rect": box(rect), "visibleRect": box(visible),
                "visible": true, "source": "live-NSView-shape-probe", "projection": evidence,
                "style": ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": sample["foreground"]!,
                          "backgroundColor": [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0],
                          "opacity": sample["opacity"]!, "background_image": "none", "shadow": [], "stroke_width": 1.7 * ((sample["rect"] as? [String: Double])?["width"] ?? 0) / 24],
                "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()],
                "icon": sample["icon"]!, "pixelSamples": samples(visible, bitmap: bitmap)]
            raw.append(node)
            if let owner { elements.insert(node, at: owner + 1) } else { elements.append(node) }
        }

        var chartEdges: [[String: Any]] = []
        for sample in ChartEdgeProbe.snapshots(in: contentScreen) {
            let rect = (sample["rectValue"] as! NSValue).rectValue, width = sample["width"] as! Double
            // A vertical or horizontal path can have a zero-area geometric box
            // while its stroked paint is visible. Keep the actual path bounds.
            let painted = rect.insetBy(dx: -width / 2, dy: -width / 2).intersection(viewport)
            guard !painted.isNull && painted.width > 0 && painted.height > 0 else { continue }
            let evidence = sample["evidence"] as! [String: Any]
            let sx = evidence["scale_x"] as! Double, sy = evidence["scale_y"] as! Double
            if abs(sx - sy) > 0.0001 { surfaceGaps.append("Nonuniform chart edge transform needs directional stroke geometry: " + (sample["id"] as! String)) }
            let clipped = rect.intersection(viewport)
            let node: [String: Any] = ["id": sample["id"]!, "parent": NSNull(), "kind": "chart-edge", "text": "", "name": "", "region": region(rect, fallback: "dialog"), "rect": box(rect), "visibleRect": clipped.isNull ? NSNull() : box(clipped), "visible": true,
                "source": "live-native-chart-path", "projection": evidence, "icon": sample["icon"]!, "hovered": false,
                "style": ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": sample["color"]!, "backgroundColor": [0,0,0,0], "borderColor": [0,0,0,0], "borderWidth": 0, "borderRadius": 0,
                          "border_widths": [0,0,0,0], "border_colors": Array(repeating: [0,0,0,0], count: 4), "corner_radii": [0,0,0,0], "opacity": sample["opacity"]!, "background_image": "none", "shadow": [], "stroke_width": abs(sx - sy) > 0.0001 ? NSNull() : width as Any],
                "state": ["enabled": NSNull(), "selected": NSNull(), "checked": NSNull(), "expanded": NSNull(), "focused": NSNull()], "pixelSamples": samples(painted, bitmap: bitmap)]
            raw.append(node); chartEdges.append(node)
        }
        // ChartView's native ZStack draws edges before node controls. Preserve
        // that production layer order when supplementing AX with path paint.
        elements.insert(contentsOf: chartEdges, at: elements.firstIndex { $0["kind"] as? String == "chart-node" } ?? elements.count)

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
                             "border_widths": "border_widths", "border_colors": "border_colors", "corner_radii": "corner_radii", "opacity": "opacity", "background_image": "background_image", "shadow": "shadow"]
            var actualStyle: [String: Any] = [:]
            for (key, original) in styleKeys {
                let value = sourceStyle[original] ?? NSNull()
                let applicable = (!key.hasPrefix("font_") || !text.isEmpty) && (key != "foreground" || !text.isEmpty || ["icon", "chart-edge"].contains(kind))
                actualStyle[key] = applicable ? value : NSNull()
                if applicable && value is NSNull { unmeasured.append(id + ":style." + key) }
            }
            actualStyle["rendered_fonts"] = text.isEmpty ? NSNull() : sourceStyle["rendered_fonts"] ?? NSNull()
            if !text.isEmpty && sourceStyle["rendered_fonts"] == nil { unmeasured.append(id + ":style.rendered_fonts") }
            if ["icon", "chart-edge"].contains(kind) {
                actualStyle["stroke_width"] = sourceStyle["stroke_width"] ?? NSNull()
                if sourceStyle["stroke_width"] == nil { unmeasured.append(id + ":style.stroke_width") }
            }
            let isControl = ["button", "icon-button", "input", "checkbox", "tab", "dropdown", "link", "menu-item", "chart-node"].contains(kind)
            let order = orders[region, default: 0]; orders[region] = order + 1
            let pointer = NSEvent.mouseLocation
            let pointerOutside = !contentScreen.contains(pointer)
            let state: [String: Any] = ["enabled": isControl ? sourceState["enabled"]! : NSNull(), "selected": ["tab", "list-row"].contains(kind) ? sourceState["selected"]! : NSNull(), "checked": kind == "checkbox" ? sourceState["checked"]! : NSNull(), "expanded": node["role"] as? String == "AXDisclosureTriangle" ? sourceState["expanded"]! : NSNull(), "focused": isControl ? sourceState["focused"]! : NSNull(), "hovered": node["hovered"] ?? (pointerOutside ? false as Any : NSNull()), "unread": NSNull()]
            if !pointerOutside && node["hovered"] == nil { unmeasured.append(id + ":state.hovered") }
            if !text.isEmpty && node["layout"] == nil { unmeasured.append(id + ":layout") }
            var evidence = node
            evidence["font_family"] = sourceStyle["fontFamily"] ?? NSNull()
            evidence["raw_node_id"] = id
            evidence["pointer_screen"] = ["x": pointer.x, "y": pointer.y]
            return ["id": id, "parent": emittedParent(node), "region": region, "order": order, "kind": kind, "text": text, "name": node["name"]!, "bounds": node["rect"]!, "visible_bounds": node["visibleRect"]!, "style": actualStyle, "state": state, "layout": node["layout"] ?? ["wrap": NSNull(), "truncation": NSNull(), "line_count": NSNull()], "icon": node["icon"] ?? NSNull(), "evidence": evidence]
        }
        let normalized: [String: Any] = ["schema_version": 1, "scene_id": item["id"].text, "client": "macos", "viewport": ["width": bitmap.pixelsWide, "height": bitmap.pixelsHigh, "scale": 1], "extraction_errors": [], "coverage": ["raw_nodes": raw.count, "emitted_elements": canonical.count, "unmeasured": unmeasured], "elements": canonical, "raw_tree": stem.appendingPathExtension("ax.json").lastPathComponent]
        try JSONSerialization.data(withJSONObject: normalized, options: [.prettyPrinted, .sortedKeys]).write(to: stem.appendingPathExtension("elements.json"))
        var audit = metadata; audit["nodes"] = raw; audit["regions"] = regions.map { ["name": $0.name, "rect": box($0.rect)] }
        audit["surface_probes"] = surfaces.map { surface in var value = surface; value.removeValue(forKey: "rectValue"); return value }
        try JSONSerialization.data(withJSONObject: audit, options: [.prettyPrinted, .sortedKeys]).write(to: stem.appendingPathExtension("ax.json"))
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

extension View {
    func measuredRegion(_ name: String) -> some View { background(ElementRegionProbe(name: name).frame(maxWidth: .infinity, maxHeight: .infinity)) }
}
