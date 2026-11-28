import AppKit

/// DOMRange measures text advance, whereas TextKit's glyph boundingRect also
/// includes ink overhang. Read insertion positions from the existing layout;
/// never reshape a replacement string or infer advances from the reference.
@MainActor enum NativeTextGeometry {
    struct Measurement {
        var rectangles: [NSRect] = []
        var lines: [[String: Any]] = []
        var complete = true
        var envelope: NSRect? { complete && !rectangles.isEmpty ? rectangles.reduce(NSRect.null) { $0.union($1) } : nil }
    }
    static func advances(_ manager: NSLayoutManager, container: NSTextContainer, characters: NSRange) -> Measurement {
        var result = Measurement()
        let glyphs = manager.glyphRange(forCharacterRange: characters, actualCharacterRange: nil)
        manager.enumerateLineFragments(forGlyphRange: glyphs) { fragment, used, _, lineGlyphs, _ in
            let lineCharacters = manager.characterRange(forGlyphRange: lineGlyphs, actualGlyphRange: nil)
            let range = NSIntersectionRange(characters, lineCharacters)
            guard range.length > 0 else { return }
            let truncated = manager.truncatedGlyphRange(inLineFragmentForGlyphAt: lineGlyphs.location)
            var row: [String: Any] = ["fragment": ElementCapture.box(fragment), "used_fragment": ElementCapture.box(used),
                "character_range": ["location": range.location, "length": range.length],
                "truncated_glyph_range": truncated.location == NSNotFound ? NSNull() : ["location": truncated.location, "length": truncated.length]]
            let count = manager.getLineFragmentInsertionPoints(forCharacterAt: range.location, alternatePositions: false, inDisplayOrder: false, positions: nil, characterIndexes: nil)
            guard count > 0, count <= lineCharacters.length + 1 else {
                row["error"] = "Native insertion-point count does not fit the actual line"; result.complete = false; result.lines.append(row); return
            }
            var positions = [CGFloat](repeating: 0, count: count), indexes = [Int](repeating: 0, count: count)
            let received = manager.getLineFragmentInsertionPoints(forCharacterAt: range.location, alternatePositions: false, inDisplayOrder: false, positions: &positions, characterIndexes: &indexes)
            row["positions"] = positions; row["character_indexes"] = indexes; row["received_count"] = received
            // TextKit places the caret after a paragraph terminator at the far
            // edge of the container. That editing position is not horizontal
            // advance painted by the source newline. Retain the source range,
            // and measure through the actual insertion point before CR/LF only.
            var advanceEnd = NSMaxRange(range)
            if let source = manager.textStorage?.string as NSString? {
                while advanceEnd > range.location && [UInt16(0x0a), 0x0d, 0x2028, 0x2029].contains(source.character(at: advanceEnd - 1)) { advanceEnd -= 1 }
            }
            row["advance_character_range"] = ["location": range.location, "length": advanceEnd - range.location]
            let selected = zip(indexes, positions).filter { $0.0 >= range.location && $0.0 <= advanceEnd }
            guard received == count, indexes.contains(range.location), indexes.contains(advanceEnd),
                  truncated.location == NSNotFound || truncated.length == 0,
                  let lower = selected.map({ $0.1 }).min(), let upper = selected.map({ $0.1 }).max() else {
                row["error"] = "Truncation or missing native insertion boundaries leaves text advance unmeasured"
                result.complete = false; result.lines.append(row); return
            }
            let rect = NSRect(x: fragment.minX + lower, y: used.minY, width: upper - lower, height: used.height)
            row["advance_bounds"] = ElementCapture.box(rect); result.rectangles.append(rect); result.lines.append(row)
        }
        return result
    }
}
