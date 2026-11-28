import AppKit

/// Horizontal advance and the font's typographic extent are distinct from the
/// paragraph line box and glyph ink. Measure both from the existing layout/draw.
@MainActor enum NativeTypographicGeometry {
    static func measure(advances: NativeTextGeometry.Measurement, draw: [String: Any],
                        characters: NSRange, origin: NSPoint) -> NativeTextGeometry.Measurement {
        var result = NativeTextGeometry.Measurement()
        func incomplete(_ reason: String) -> NativeTextGeometry.Measurement {
            result.complete = false; result.lines.append(["error": reason]); return result
        }
        guard advances.complete, !advances.rectangles.isEmpty,
              advances.lines.count == advances.rectangles.count,
              draw["draw_returned"] as? Bool == true,
              let calls = draw["callbacks"] as? [[String: Any]] else {
            return incomplete("No complete native insertion layout and completed glyph draw")
        }
        var tops = Array(repeating: Double.infinity, count: advances.lines.count)
        var bottoms = Array(repeating: -Double.infinity, count: advances.lines.count)
        var receipts = Array(repeating: [[String: Any]](), count: advances.lines.count)
        var ctm: [String: Double]?
        for (index, call) in calls.enumerated() {
            guard let source = call["source_character_range"] as? [String: Int],
                  let location = source["location"], let length = source["length"] else {
                return incomplete("A glyph callback has no source range")
            }
            let range = NSRange(location: location, length: length)
            guard NSIntersectionRange(range, characters).length > 0 else { continue }
            guard NSIntersectionRange(range, characters) == range,
                  let font = call["actual_font"] as? [String: Any],
                  let ascent = (font["ascent"] as? NSNumber)?.doubleValue, let descent = (font["descent"] as? NSNumber)?.doubleValue,
                  ascent.isFinite, descent.isFinite, ascent >= 0, descent >= 0,
                  let matrix = call["text_matrix"] as? [String: Double],
                  matrix["a"] == 1, matrix["b"] == 0, matrix["c"] == 0, matrix["d"] == -1,
                  let currentCTM = call["context_ctm"] as? [String: Double],
                  let positions = call["positions_user_space"] as? [[String: Any]], !positions.isEmpty else {
                return incomplete("Partial source coverage, unknown metrics or non-horizontal native text transform")
            }
            if let ctm, ctm != currentCTM { return incomplete("Glyph callbacks use different user-space transforms") }
            ctm = currentCTM
            var baselines: [Int: Set<Double>] = [:]
            for position in positions {
                guard let y = (position["y"] as? NSNumber)?.doubleValue, y.isFinite else { return incomplete("Unknown native glyph baseline") }
                let baseline = y - Double(origin.y)
                let owners = advances.lines.indices.filter {
                    let fragment = ElementCapture.rect(advances.lines[$0]["fragment"])
                    return !fragment.isNull && baseline >= Double(fragment.minY) && baseline < Double(fragment.maxY)
                }
                guard owners.count == 1, let line = owners.first else {
                    return incomplete("Actual glyph baseline has no unique native line-fragment owner")
                }
                baselines[line, default: []].insert(baseline)
                // showCGGlyphs positions are in user space. The text matrix
                // maps font ascent upward; its tx/ty are ignored by Quartz.
                tops[line] = min(tops[line], baseline - ascent)
                bottoms[line] = max(bottoms[line], baseline + descent)
            }
            for (line, values) in baselines {
                receipts[line].append(["callback_index": index, "baselines": values.sorted(),
                    "font": font["postscript_name"] ?? NSNull(), "ascent": ascent, "descent": descent])
            }
        }
        for index in advances.rectangles.indices {
            guard tops[index].isFinite, bottoms[index].isFinite, bottoms[index] >= tops[index] else {
                return incomplete("A native line has no attributable actual font draw")
            }
            let advance = advances.rectangles[index]
            let rect = NSRect(x: advance.minX, y: CGFloat(tops[index]), width: advance.width, height: CGFloat(bottoms[index] - tops[index]))
            result.rectangles.append(rect)
            result.lines.append(["insertion_line": advances.lines[index], "font_draws": receipts[index],
                "typographic_bounds": ElementCapture.box(rect),
                "quantity": "native insertion advance and actual glyph baseline plus CTFont ascent/descent; excludes paragraph leading"])
        }
        return result
    }
}
