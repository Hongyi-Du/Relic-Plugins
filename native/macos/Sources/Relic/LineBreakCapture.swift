import AppKit

@MainActor enum NativeLineBreaks {
    static func inspect(_ view: NSTextView, range: NSRange) -> (layout: [String: Any], evidence: [String: Any]) {
        var layout: [String: Any] = ["break_strategy_version": 1,
            "normal_break_strategy": NSNull(), "emergency_break_strategy": NSNull()]
        var evidence: [String: Any] = ["source": "current production NSTextView/TextKit1 configuration",
            "owner": String(describing: ObjectIdentifier(view)),
            "character_range": ["location": range.location, "length": range.length],
            "actual_line_fragments_proven": false]
        // Reading a TextKit2 layoutManager changes that renderer. Preserve it.
        guard view.textLayoutManager == nil, let container = view.textContainer,
              let storage = view.textStorage, range.location < storage.length else {
            evidence["reason"] = "No measured TextKit1 paragraph/container configuration"
            return (layout, evidence)
        }
        let paragraph = storage.attribute(.paragraphStyle, at: range.location, effectiveRange: nil) as? NSParagraphStyle
            ?? view.defaultParagraphStyle ?? NSParagraphStyle.default
        let mode = container.maximumNumberOfLines == 1 ? container.lineBreakMode : paragraph.lineBreakMode
        evidence["paragraph_mode"] = paragraph.lineBreakMode.rawValue
        evidence["paragraph_strategy"] = paragraph.lineBreakStrategy.rawValue
        evidence["container_mode"] = container.lineBreakMode.rawValue
        evidence["maximum_lines"] = container.maximumNumberOfLines
        evidence["effective_mode"] = mode.rawValue
        evidence["container_identity"] = String(describing: ObjectIdentifier(container))
        evidence["container_size"] = ["width": container.containerSize.width, "height": container.containerSize.height]
        if let delegate = view.layoutManager?.delegate {
            evidence["layout_delegate"] = String(describing: type(of: delegate))
            guard let paths = delegate as? PathLineBreaks else {
                evidence["reason"] = "An unmeasured layout delegate can override line break opportunities"
                return (layout, evidence)
            }
            evidence["slash_word_break_suppression"] = paths.enabled
        }
        switch mode {
        case .byWordWrapping:
            // AppKit wraps at word boundaries unless the word cannot fit on a
            // whole line. This is distinct from character-first wrapping.
            layout["normal_break_strategy"] = "word"
            layout["emergency_break_strategy"] = "break-unbreakable"
        case .byCharWrapping:
            layout["normal_break_strategy"] = "character"
            layout["emergency_break_strategy"] = "none"
        case .byClipping, .byTruncatingHead, .byTruncatingMiddle, .byTruncatingTail:
            layout["normal_break_strategy"] = "none"
            layout["emergency_break_strategy"] = "none"
        @unknown default:
            evidence["reason"] = "Unknown native line-break mode"
        }
        return (layout, evidence)
    }
}
