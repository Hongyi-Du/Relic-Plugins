import AppKit

extension NSAttributedString.Key {
    static let relicLabelSpan = NSAttributedString.Key("RelicProductionLabelSpan")
}

enum NativeTextSpans {
    /// A uniform production label owns one visible text element even when
    /// TextKit resolves its arrow, Han characters and emoji to different fonts.
    /// Unmarked attributed text retains every independent attribute boundary.
    static func enumerate(_ storage: NSAttributedString,
                          body: @escaping ([NSAttributedString.Key: Any], NSRange, [[String: Any]], [NSFont]) -> Void) {
        storage.enumerateAttribute(.relicLabelSpan, in: NSRange(location: 0, length: storage.length)) { marker, span, _ in
            func visit(_ range: NSRange) {
                var actual: [[String: Any]] = [], fonts: [NSFont] = []
                storage.enumerateAttributes(in: range) { attributes, fragment, _ in
                    if let font = attributes[.font] as? NSFont { fonts.append(font) }
                    actual.append(["range": ["location": fragment.location, "length": fragment.length],
                        "attributes": Dictionary(uniqueKeysWithValues: attributes.map { ($0.key.rawValue, String(describing: $0.value)) })])
                }
                body(storage.attributes(at: range.location, effectiveRange: nil), range, actual, fonts)
            }
            if marker as? String == "uniform-production-label" { visit(span) }
            else { storage.enumerateAttributes(in: span) { _, range, _ in visit(range) } }
        }
    }
}
