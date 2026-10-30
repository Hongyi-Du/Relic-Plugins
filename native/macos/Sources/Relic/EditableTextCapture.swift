import AppKit

@MainActor enum EditableTextCapture {
    /// The input owns its actually drawn text. Retain its AX hit rectangle and
    /// raw draw; do not add another visible text element for the same glyphs.
    static func attach(to node: inout [String: Any], view: ComposerTextView, canvas: NSRect) {
        guard view.isEditable, !view.string.isEmpty, view.textLayoutManager == nil, let window = view.window else { return }
        let runs = ElementCapture.textRuns(view)
        node["native_editable_text_runs"] = runs.map { run in
            var value = run; value["local_rect"] = ElementCapture.box((run["local_rect"] as? NSValue)?.rectValue ?? .null)
            return value
        }
        guard runs.count == 1, let run = runs.first, run["text"] as? String == view.string else { return }
        var style = node["style"] as? [String: Any] ?? [:]
        let textStyle = run["style"] as? [String: Any] ?? [:]
        for key in ["fontSize", "fontWeight", "fontFamily", "rendered_fonts", "color"] { style[key] = textStyle[key] ?? NSNull() }
        node["style"] = style; node["layout"] = run["layout"]
        node["text_bounds"] = (run["lines"] as? [[String: Double]] ?? []).map { row in
            let local = ElementCapture.rect(row)
            return ElementCapture.box(ElementCapture.topLeft(window.convertToScreen(view.convert(local, to: nil)), in: canvas))
        }
        var projection = run
        projection.removeValue(forKey: "local_rect")
        projection["local_bounds"] = ElementCapture.box((run["local_rect"] as? NSValue)?.rectValue ?? .null)
        node["projection"] = projection
        node["projection_reason"] = "The actual editable input owns its single completed native text span; AX interaction bounds are retained"
    }
}
