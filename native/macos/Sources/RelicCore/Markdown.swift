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

public struct MarkdownInline: Equatable {
    public let kind: String
    public let text: String
}

public enum NativeMarkdown {
    // The reference deliberately supports this small inline grammar. Feeding the
    // text to a general Markdown parser changes visible punctuation and links.
    public static func inline(_ text: String) -> [MarkdownInline] {
        let pattern = #"(\u0060[^\u0060\n]+\u0060|\*\*[^*\n]+\*\*|https?://[^\s<>)）\]]+|\b[A-Za-z]:[\\/][^\s<>"'|*?，。；：、（）)\]【】「」《》“”]+|(?<![\w./:\\])/(?!/)[^\s<>"'\u0060|*?，。；：、（）)\]【】「」《》“”]+)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [MarkdownInline(kind: "text", text: text)] }
        let value = text as NSString
        var output: [MarkdownInline] = [], last = 0
        for match in regex.matches(in: text, range: NSRange(location: 0, length: value.length)) {
            if match.range.location > last { output.append(MarkdownInline(kind: "text", text: value.substring(with: NSRange(location: last, length: match.range.location - last)))) }
            let token = value.substring(with: match.range)
            if token.first?.asciiValue == 96 { output.append(MarkdownInline(kind: "code", text: String(token.dropFirst().dropLast()))) }
            else if token.hasPrefix("**") { output.append(MarkdownInline(kind: "bold", text: String(token.dropFirst(2).dropLast(2)))) }
            else if NativeLinks.file(token) != nil {
                let core = token.replacingOccurrences(of: #"[.,;:!?]+$"#, with: "", options: .regularExpression)
                output.append(MarkdownInline(kind: "path", text: core))
                if core.count < token.count { output.append(MarkdownInline(kind: "text", text: String(token.dropFirst(core.count)))) }
            } else { output.append(MarkdownInline(kind: "url", text: token)) }
            last = match.range.location + match.range.length
        }
        if last < value.length { output.append(MarkdownInline(kind: "text", text: value.substring(from: last))) }
        return output
    }
    public static func attributed(_ text: String) -> AttributedString {
        var result = AttributedString()
        for token in inline(text) {
            var run = AttributedString(token.text)
            if token.kind == "bold" { run.inlinePresentationIntent = .stronglyEmphasized }
            if token.kind == "code" { run.inlinePresentationIntent = .code }
            if token.kind == "path" || token.kind == "code", let file = NativeLinks.file(token.text) { run.link = file.url }
            else if token.kind == "url" { run.link = URL(string: token.text) }
            result.append(run)
        }
        return result
    }
    public static func list(_ block: MarkdownBlock) -> [MarkdownListItem] {
        guard let regex = try? NSRegularExpression(pattern: #"^(\s*)([-*•+]|\d+[.)])\s+(.*)$"#) else { return [] }
        var rows: [MarkdownListItem] = []
        let first = block.lines.first ?? ""
        let start = first.range(of: #"^\s*\d+[.)]"#, options: .regularExpression).flatMap { Int(first[$0].trimmingCharacters(in: .whitespaces).dropLast()) }
        for line in block.lines {
            if let match = regex.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)) {
                func part(_ n: Int) -> String { Range(match.range(at: n), in: line).map { String(line[$0]) } ?? "" }
                let marker = start.map { String($0 + rows.count) + "." } ?? "•"
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
    public static func tableHasHeader(_ block: MarkdownBlock) -> Bool {
        block.lines.count > 1 && block.lines[1].range(of: #"^\s*\|?\s*:?-{2,}"#, options: .regularExpression) != nil
    }
}
