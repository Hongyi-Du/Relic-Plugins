import AppKit
import CoreText

/// Read the font supplied to the real glyph drawing callback. A static face
/// has no wght variation axis; its OS/2 table records the weight class. Never
/// substitute the requested style, font name or an NSFont trait conversion.
enum NativeFontWeight {
    static let variationTag: UInt32 = 0x66766172 // fvar
    static let weightTag: UInt32 = 0x77676874 // wght

    static func staticWeight(table: Data?, availableTags: [UInt32]?, hasVariationAxes: Bool) -> Int? {
        guard let tags = availableTags, !tags.contains(variationTag), tags.contains(kCTFontTableOS2), !hasVariationAxes,
              let table, table.count >= 68 else { return nil }
        let version = Int(table[0]) << 8 | Int(table[1])
        let value = Int(table[4]) << 8 | Int(table[5])
        return version <= 5 && (1...1000).contains(value) ? value : nil
    }

    static func capture(_ font: CTFont) -> [String: Any] {
        let tags = (CTFontCopyAvailableTables(font, []) as? [NSNumber])?.map(\.uint32Value)
        let table = CTFontCopyTable(font, kCTFontTableOS2, []).map { $0 as Data }
        let variations = (CTFontCopyVariation(font) as? [NSNumber: NSNumber])?.reduce(into: [String: Double]()) { $0[$1.key.stringValue] = $1.value.doubleValue }
        let axes = (CTFontCopyVariationAxes(font) as? [[String: Any]])?.map { axis -> [String: Any] in
            ["tag": axis[kCTFontVariationAxisIdentifierKey as String] ?? NSNull(),
             "minimum": axis[kCTFontVariationAxisMinimumValueKey as String] ?? NSNull(),
             "default": axis[kCTFontVariationAxisDefaultValueKey as String] ?? NSNull(),
             "maximum": axis[kCTFontVariationAxisMaximumValueKey as String] ?? NSNull()]
        }
        var receipt: [String: Any] = ["version": 1, "source": "CTFont tables and variations of the actual showCGGlyphs font",
            "postscript_name": CTFontCopyPostScriptName(font) as String,
            "available_table_tags": tags as Any? ?? NSNull(), "variation_axes": axes as Any? ?? NSNull(),
            "actual_variations": variations as Any? ?? NSNull(), "os2_base64": table?.base64EncodedString() as Any? ?? NSNull(),
            "status": "unmeasured", "value": NSNull(), "quantity": NSNull()]
        if let value = variations?[String(weightTag)], value.isFinite, (1...1000).contains(value) {
            receipt["status"] = "measured"; receipt["value"] = value; receipt["quantity"] = "actual-wght-coordinate"
        } else if let value = staticWeight(table: table, availableTags: tags,
                    hasVariationAxes: !(axes ?? []).isEmpty || !(variations ?? [:]).isEmpty) {
            receipt["status"] = "measured"; receipt["value"] = value; receipt["quantity"] = "static-face-os2-usWeightClass"
        } else {
            receipt["reason"] = "No measured wght coordinate or independently proven non-variable OS/2 face"
        }
        return receipt
    }
}
