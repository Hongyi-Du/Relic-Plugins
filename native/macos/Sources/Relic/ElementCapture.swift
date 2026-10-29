import AppKit
import SwiftUI
import RelicCore

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
        case "AXButton": return "button"
        case "AXStaticText": return "text"
        case "AXTextField", "AXTextArea", "AXSearchField": return "input"
        case "AXCheckBox": return "checkbox"
        case "AXRadioButton": return "radio"
        case "AXPopUpButton", "AXComboBox": return "dropdown"
        case "AXLink": return "link"
        case "AXImage": return "image"
        case "AXMenuItem": return "menu-item"
        case "AXMenu": return "menu"
        case "AXTabGroup": return "tabs"
        case "AXRow": return "row"
        case "AXList", "AXOutline", "AXTable": return "list"
        case "AXSplitter", "AXSplitGroup": return "divider"
        case "AXScrollArea": return "scroll-area"
        case "AXScrollBar": return "scrollbar"
        case "AXGroup", "AXLayoutArea": return "group"
        default: return "unknown"
        }
    }
    static func cssWeight(_ font: NSFont) -> Int {
        let traits = font.fontDescriptor.object(forKey: .traits) as? [NSFontDescriptor.TraitKey: Any]
        let value = (traits?[.weight] as? NSNumber)?.doubleValue ?? 0
        let weights: [(Double, Int)] = [(-0.8, 100), (-0.6, 200), (-0.4, 300), (0, 400), (0.23, 500), (0.3, 600), (0.4, 700), (0.56, 800), (0.62, 900)]
        return weights.min(by: { abs($0.0 - value) < abs($1.0 - value) })?.1 ?? 400
    }
    static func rgba(_ color: NSColor?) -> Any {
        guard let color = color?.usingColorSpace(.sRGB) else { return NSNull() }
        return [color.redComponent, color.greenComponent, color.blueComponent, color.alphaComponent].map(Double.init)
    }
    private static func string(_ value: Any?) -> String {
        if let value = value as? String { return value }
        if let value = value as? NSAttributedString { return value.string }
        return ""
    }
    private static func style(_ object: AnyObject, ax: any NSAccessibilityProtocol, text: String) -> [String: Any] {
        var result: [String: Any] = ["fontSize": NSNull(), "fontWeight": NSNull(), "fontFamily": NSNull(), "color": NSNull(), "backgroundColor": NSNull(), "borderColor": NSNull(), "borderWidth": NSNull(), "borderRadius": NSNull()]
        var font: NSFont?, foreground: NSColor?, background: NSColor?
        if let textView = object as? NSTextView { font = textView.font; foreground = textView.textColor; if textView.drawsBackground { background = textView.backgroundColor } }
        else if let field = object as? NSTextField { font = field.font; foreground = field.textColor; if field.drawsBackground { background = field.backgroundColor } }
        else if let control = object as? NSControl { font = control.font }
        if !text.isEmpty, let attributed = ax.accessibilityAttributedString(for: NSRange(location: 0, length: (text as NSString).length)), attributed.length > 0 {
            let attributes = attributed.attributes(at: 0, effectiveRange: nil)
            font = (attributes[.font] as? NSFont) ?? font
            foreground = (attributes[.foregroundColor] as? NSColor) ?? foreground
            background = (attributes[.backgroundColor] as? NSColor) ?? background
            if let axFont = attributes[NSAttributedString.Key("AXFont")] as? [String: Any] {
                result["fontSize"] = axFont["AXFontSize"] ?? NSNull()
                result["fontFamily"] = axFont["AXFontFamily"] ?? axFont["AXFontName"] ?? NSNull()
            }
            // Preserve all platform attributes separately for audit, including
            // attributes not yet understood by the common normalizer.
            result["rawTextAttributes"] = Dictionary(uniqueKeysWithValues: attributes.map { ($0.key.rawValue, String(describing: $0.value)) })
        }
        if let font { result["fontSize"] = Double(font.pointSize); result["fontWeight"] = cssWeight(font); result["fontFamily"] = font.familyName ?? font.fontName }
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
    static func write(window: NSWindow, png: URL, item: Node, language: String, theme: String) throws {
        guard let content = window.contentView, let bitmap = NSBitmapImageRep(data: try Data(contentsOf: png)) else { throw RelicError.message("Cannot inspect captured native image") }
        let contentScreen = window.convertToScreen(content.convert(content.bounds, to: nil))
        let viewport = NSRect(origin: .zero, size: content.bounds.size)
        var raw: [[String: Any]] = [], elements: [[String: Any]] = [], seen = Set<ObjectIdentifier>()
        let regions = ElementRegionProbe.regions(in: contentScreen)
        func region(_ rect: NSRect, fallback: String) -> String {
            let point = NSPoint(x: rect.midX, y: rect.midY)
            return regions.filter { $0.rect.contains(point) }.min(by: { $0.rect.width * $0.rect.height < $1.rect.width * $1.rect.height })?.name ?? fallback
        }
        func visit(_ value: Any, path: String, parent: String?, inheritedRegion: String, clip: NSRect) {
            guard let object = value as? NSObject, let ax = object as? any NSAccessibilityProtocol else { return }
            guard seen.insert(ObjectIdentifier(object)).inserted else { return }
            let role = ax.accessibilityRole()?.rawValue ?? "", rect = topLeft(ax.accessibilityFrame(), in: contentScreen)
            let visibleRect = rect.intersection(clip)
            let label = ax.accessibilityLabel() ?? "", title = ax.accessibilityTitle() ?? "", valueText = string(ax.accessibilityValue())
            let text = !valueText.isEmpty && ["AXStaticText", "AXTextField", "AXTextArea"].contains(role) ? valueText : !title.isEmpty ? title : label
            let assignedRegion = inheritedRegion == "dialog" || inheritedRegion == "menu" ? inheritedRegion : region(rect, fallback: inheritedRegion)
            let visible = !ax.isAccessibilityHidden() && !visibleRect.isNull && visibleRect.width > 0 && visibleRect.height > 0
            var node: [String: Any] = ["id": path, "parent": parent as Any? ?? NSNull(), "role": role, "subrole": ax.accessibilitySubrole()?.rawValue ?? "", "kind": kind(role), "text": text, "name": label, "title": title, "value": valueText, "placeholder": ax.accessibilityPlaceholderValue() ?? "", "identifier": ax.accessibilityIdentifier() ?? "", "help": ax.accessibilityHelp() ?? "", "region": assignedRegion, "rect": box(rect), "visibleRect": visibleRect.isNull ? NSNull() : box(visibleRect), "visible": visible, "axElement": ax.isAccessibilityElement(), "order": raw.count, "source": "NSAccessibilityProtocol", "class": String(describing: type(of: object))]
            node["state"] = ["disabled": !ax.isAccessibilityEnabled(), "focused": ax.isAccessibilityFocused(), "selected": ax.isAccessibilitySelected(), "expanded": ax.isAccessibilityExpanded(), "checked": ["AXCheckBox", "AXRadioButton"].contains(role) ? ((ax.accessibilityValue() as? NSNumber)?.intValue == 1) : false]
            node["style"] = style(object, ax: ax, text: text)
            node["pixelSamples"] = visible ? samples(visibleRect, bitmap: bitmap) : []
            raw.append(node)
            if visible && ax.isAccessibilityElement() { elements.append(node) }
            let childClip = role == "AXScrollArea" ? clip.intersection(rect) : clip
            for (index, child) in (ax.accessibilityChildren() ?? []).enumerated() { visit(child, path: path + "/" + String(index), parent: path, inheritedRegion: assignedRegion, clip: childClip) }
        }
        visit(content, path: "window", parent: nil, inheritedRegion: "window", clip: viewport)
        for (index, child) in NSApp.windows.filter({ $0 !== window && $0.isVisible && $0.contentView != nil }).enumerated() {
            visit(child.contentView!, path: "surface-" + String(index), parent: nil, inheritedRegion: child === window.attachedSheet ? "dialog" : "menu", clip: viewport)
        }
        guard !elements.isEmpty else { throw RelicError.message("Native accessibility extraction returned no visible elements") }
        let stem = png.deletingPathExtension()
        let metadata: [String: Any] = ["version": 1, "client": "macos", "caseId": item["id"].text, "scene": item["scene"].text, "language": language, "theme": theme, "viewport": ["width": bitmap.pixelsWide, "height": bitmap.pixelsHigh], "coordinateSpace": "content-top-left-logical-pixels", "screenshot": png.lastPathComponent]
        var normalized = metadata
        normalized["elements"] = elements
        normalized["extraction"] = ["source": "live-native-AX-and-PNG", "coverageComplete": false, "diagnostics": ["Paint-only SwiftUI decorations require supplemental view measurements", "Null style attributes are unmeasured and must not count as matches"], "rawNodes": raw.count, "visibleAXElements": elements.count]
        try JSONSerialization.data(withJSONObject: normalized, options: [.prettyPrinted, .sortedKeys]).write(to: stem.appendingPathExtension("elements.json"))
        var audit = metadata; audit["nodes"] = raw; audit["regions"] = regions.map { ["name": $0.name, "rect": box($0.rect)] }
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
