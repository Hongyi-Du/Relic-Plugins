import Foundation

public struct MarkdownBlock {
    public let kind: String
    public let lines: [String]
    public var text: String { lines.joined(separator: "\n") }
}

public struct MarkdownListItem {
    public let marker: String
    public let indented: Bool
    public var text: String
}

public enum NativeMarkdown {
    public static func list(_ block: MarkdownBlock) -> [MarkdownListItem] {
        guard let regex = try? NSRegularExpression(pattern: #"^(\s*)([-*•+]|\d+[.)])\s+(.*)$"#) else { return [] }
        var rows: [MarkdownListItem] = []
        for line in block.lines {
            if let match = regex.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)) {
                func part(_ n: Int) -> String { Range(match.range(at: n), in: line).map { String(line[$0]) } ?? "" }
                let bullet = part(2), marker = bullet.first?.isNumber == true ? bullet : "•"
                rows.append(MarkdownListItem(marker: marker, indented: part(1).count >= 2, text: part(3)))
            } else if !rows.isEmpty { rows[rows.count - 1].text += "\n" + line.trimmingCharacters(in: .whitespaces) }
        }
        return rows
    }
    public static func blocks(_ text: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        for (index, part) in text.components(separatedBy: "```").enumerated() {
            if index % 2 == 1 {
                var lines = part.components(separatedBy: "\n")
                if let first = lines.first, first.range(of: #"^[\w+.-]*$"#, options: .regularExpression) != nil { lines.removeFirst() }
                if lines.last == "" { lines.removeLast() }
                blocks.append(MarkdownBlock(kind: "code", lines: lines)); continue
            }
            var kind = "", run: [String] = []
            func flush() { if !run.isEmpty { blocks.append(MarkdownBlock(kind: kind, lines: run)); run = [] } }
            for line in part.components(separatedBy: "\n") {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty { flush(); kind = ""; continue }
                var next = "text"
                if trimmed.hasPrefix(">") { next = "quote" }
                else if line.range(of: #"^\s*([-*•+]|\d+[.)])\s+"#, options: .regularExpression) != nil { next = "list" }
                else if line.range(of: #"^#{1,6}\s"#, options: .regularExpression) != nil { next = "head" }
                else if trimmed.hasPrefix("|") && trimmed.hasSuffix("|") { next = "table" }
                else if kind == "list" && line.hasPrefix("  ") { next = "list" }
                if next != kind || next == "head" { flush(); kind = next }; run.append(line)
            }
            flush()
        }
        return blocks
    }
    public static func table(_ block: MarkdownBlock) -> [[String]] {
        block.lines.filter { $0.range(of: #"^\s*\|?\s*:?-{2,}"#, options: .regularExpression) == nil }.map { line in
            var value = line.trimmingCharacters(in: .whitespaces); if value.first == "|" { value.removeFirst() }; if value.last == "|" { value.removeLast() }
            return value.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        }
    }
}
