import Foundation

/// Immutable parsed content. AppKit font metrics and drawing stay on the main
/// thread; block parsing and inline/link recognition happen on this actor.
public struct PreparedMarkdown {
    public let source: String
    public let blocks: [MarkdownBlock]
    private let attributed: [String: AttributedString]
    private let lists: [String: [MarkdownListItem]]
    private let tables: [String: [[String]]]
    public func inline(_ text: String) -> AttributedString { attributed[text] ?? AttributedString(text) }
    public func list(_ block: MarkdownBlock) -> [MarkdownListItem] { lists[block.text] ?? [] }
    public func table(_ block: MarkdownBlock) -> [[String]] { tables[block.text] ?? [] }
    fileprivate init(_ text: String) {
        source = text; blocks = NativeMarkdown.blocks(text)
        var runs: [String: AttributedString] = [:], listRows: [String: [MarkdownListItem]] = [:], tableRows: [String: [[String]]] = [:]
        func add(_ value: String) { if runs[value] == nil { runs[value] = NativeMarkdown.attributed(value) } }
        for block in blocks {
            switch block.kind {
            case "code", "quote": break
            case "head": add(block.text.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression))
            case "list":
                let rows = NativeMarkdown.list(block); listRows[block.text] = rows
                for row in rows { add(row.text) }
            case "table":
                let rows = NativeMarkdown.table(block); tableRows[block.text] = rows
                for row in rows { for cell in row { add(cell) } }
            default: add(block.text)
            }
        }
        attributed = runs; lists = listRows; tables = tableRows
    }
}

public actor MarkdownPreparation {
    public static let shared = MarkdownPreparation()
    private var cache: [String: PreparedMarkdown] = [:], order: [String] = []
    private var bytes = 0
    public init() {}
    public func prepare(_ text: String) -> PreparedMarkdown {
        if let cached = cache[text] { return cached }
        let value = PreparedMarkdown(text), cost = text.utf8.count
        // Count and source-byte limits bound retained parsed histories. A single
        // oversized message is rendered but not retained by the shared cache.
        if cost <= 1_048_576 {
            while !order.isEmpty && (cache.count >= 128 || bytes + cost > 4_194_304) {
                let oldest = order.removeFirst(); bytes -= oldest.utf8.count; cache.removeValue(forKey: oldest)
            }
            cache[text] = value; order.append(text); bytes += cost
        }
        return value
    }
    public var retainedCount: Int { cache.count }
    public var retainedSourceBytes: Int { bytes }
}
