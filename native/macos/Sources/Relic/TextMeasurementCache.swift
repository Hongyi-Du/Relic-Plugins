import AppKit

/// Unwrapped Markdown widths do not depend on the offered window width.
/// Reuse them across body updates (menus, dialogs, SSE) and keep the retained
/// attributed sources bounded. Copy keys so caller mutation cannot corrupt
/// the cache or silently reuse the previous font's measurement.
final class PreferredTextWidthCache {
    static let shared = PreferredTextWidthCache()
    private let values = NSCache<NSAttributedString, NSNumber>()
    init() { values.countLimit = 256; values.totalCostLimit = 4 * 1024 * 1024 }
    func width(_ source: NSAttributedString, measure: () -> CGFloat) -> CGFloat {
        if let value = values.object(forKey: source) { return CGFloat(value.doubleValue) }
        let result = measure()
        let cost = source.length * 8
        if cost <= values.totalCostLimit {
            values.setObject(NSNumber(value: Double(result)), forKey: NSAttributedString(attributedString: source), cost: cost)
        }
        return result
    }
}

/// Each visible native text view retains a small set of width proposals. A
/// content/style change invalidates the set. Never change the live text view's
/// container while SwiftUI is probing alternative widths.
final class TextMeasurementCache {
    private struct Key: Hashable { let width: CGFloat, lines: Int, mode: UInt, minimum: CGFloat, paths: Bool }
    private var source: NSAttributedString?
    private var results: [Key: CGSize] = [:]

    func label(_ value: NSAttributedString, width: CGFloat, lines: Int, mode: NSLineBreakMode,
               minimum: CGFloat, pathBreaks: PathLineBreaks) -> CGSize {
        if source == nil || !source!.isEqual(to: value) {
            source = NSAttributedString(attributedString: value); results.removeAll(keepingCapacity: true)
        }
        let key = Key(width: width, lines: lines, mode: UInt(mode.rawValue), minimum: minimum, paths: pathBreaks.enabled)
        if let cached = results[key] { return cached }
        // Reusing a layout manager across different truncated line limits can
        // keep stale glyph widths even after invalidateLayout. Retain measured
        // proposals, but make each new proposal an independent TextKit layout.
        let storage = NSTextStorage(attributedString: value), layout = NSLayoutManager()
        let container = NSTextContainer(containerSize: CGSize(width: max(0.01, width), height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0
        if pathBreaks.enabled { layout.delegate = pathBreaks }
        container.maximumNumberOfLines = lines; container.lineBreakMode = mode
        storage.addLayoutManager(layout); layout.addTextContainer(container)
        layout.ensureLayout(for: container)
        let used = layout.usedRect(for: container)
        let result = CGSize(width: min(width, ceil(used.width)), height: max(minimum, used.height))
        if results.count >= 16 { results.removeAll(keepingCapacity: true) }
        results[key] = result; return result
    }
}

final class PassageMeasurementCache {
    private struct Key: Hashable { let width: CGFloat, lines: Int }
    private var source: NSAttributedString?
    private var results: [Key: CGSize] = [:]
    func size(_ value: NSAttributedString, width: CGFloat, lines: Int) -> CGSize {
        if source == nil || !source!.isEqual(to: value) {
            source = NSAttributedString(attributedString: value); results.removeAll(keepingCapacity: true)
        }
        let key = Key(width: width, lines: lines)
        if let cached = results[key] { return cached }
        let result = SharedPassageSizes.shared.size(value, width: width, lines: lines) {
            NativeTextStyle.contentSize(value, available: width, maximumLines: lines)
        }
        if results.count >= 16 { results.removeAll(keepingCapacity: true) }
        results[key] = result; return result
    }
}

/// Rows are recreated when a chat is reopened or its bounded window moves.
/// Their passages keep the same text and widths, so reuse the measured size
/// instead of laying out the same paragraphs again. Bounded by source size.
final class SharedPassageSizes {
    static let shared = SharedPassageSizes()
    private final class Key: NSObject {
        let text: NSAttributedString, width: CGFloat, lines: Int
        init(_ text: NSAttributedString, width: CGFloat, lines: Int) { self.text = text; self.width = width; self.lines = lines }
        override var hash: Int { (text.string as NSString).hash ^ width.hashValue &* 31 ^ lines }
        override func isEqual(_ object: Any?) -> Bool {
            guard let other = object as? Key else { return false }
            return width == other.width && lines == other.lines && text.isEqual(to: other.text)
        }
    }
    private let values = NSCache<Key, NSValue>()
    init() { values.countLimit = 2048; values.totalCostLimit = 8 * 1024 * 1024 }
    func size(_ value: NSAttributedString, width: CGFloat, lines: Int, measure: () -> CGSize) -> CGSize {
        if let cached = values.object(forKey: Key(value, width: width, lines: lines)) { return cached.sizeValue }
        let result = measure()
        let cost = value.length * 2 + 64
        if cost <= values.totalCostLimit {
            values.setObject(NSValue(size: result), forKey: Key(NSAttributedString(attributedString: value), width: width, lines: lines), cost: cost)
        }
        return result
    }
}
