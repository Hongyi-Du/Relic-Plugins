import AppKit

@MainActor enum EditableTextCapture {
    /// The input owns its actually drawn text. Retain its AX hit rectangle and
    /// raw draw; do not add another visible text element for the same glyphs.
    static func attach(to node: inout [String: Any], view: NSTextView, canvas: NSRect) {
        guard view.isEditable, !view.string.isEmpty, view.textLayoutManager == nil, let window = view.window else { return }
        defer {
            var errors: [[String: String]] = []
            node = CaptureMeasurements.jsonValue(node, errors: &errors) as! [String: Any]
            if !errors.isEmpty { node["native_measurement_errors"] = errors }
        }
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
        let lines: [[String: Double]] = run["lines"] as? [[String: Double]] ?? []
        var textBounds: [[String: Double]] = []
        for row in lines {
            let local = ElementCapture.rect(row)
            textBounds.append(ElementCapture.box(ElementCapture.topLeft(window.convertToScreen(view.convert(local, to: nil)), in: canvas)))
        }
        node["text_bounds"] = textBounds
        var projection = run
        projection.removeValue(forKey: "local_rect")
        projection["local_bounds"] = ElementCapture.box((run["local_rect"] as? NSValue)?.rectValue ?? .null)
        node["projection"] = projection
        node["projection_reason"] = "The actual editable input owns its single completed native text span; AX interaction bounds are retained"
    }
}
