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
        let result = NativeTextStyle.contentSize(value, available: width, maximumLines: lines)
        if results.count >= 16 { results.removeAll(keepingCapacity: true) }
        results[key] = result; return result
    }
}
