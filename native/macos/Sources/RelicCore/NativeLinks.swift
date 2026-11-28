import Foundation

public struct FileReference: Equatable {
    public let path: String
    public let line: Int
    public var url: URL? {
        var parts = URLComponents(); parts.scheme = "relic-file"; parts.host = "preview"
        parts.queryItems = [.init(name: "path", value: path), .init(name: "line", value: String(line))]; return parts.url
    }
}

public enum NativeLinks {
    public static func file(_ text: String) -> FileReference? {
        guard text.range(of: #"^(?:[A-Za-z]:[\\/]|/(?!/))"#, options: .regularExpression) != nil, !text.contains("\n"), !text.contains("\r") else { return nil }
        guard let regex = try? NSRegularExpression(pattern: #"^(.*?)(?::(\d+))?(?::\d+)?$"#), let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)), let path = Range(match.range(at: 1), in: text) else { return nil }
        let line = Range(match.range(at: 2), in: text).flatMap { Int(text[$0]) } ?? 0
        return FileReference(path: String(text[path]), line: line)
    }
    public static func markdown(_ text: String) -> String {
        // Consume existing links and code before bare paths so URL suffixes never become local files.
        let pattern = #"\[[^\]\n]*\]\([^\)\n]*\)|`[^`\n]+`|https?://[^\s<>)）\]]+|\b[A-Za-z]:[\\/][^\s<>\"'|*?，。；：、（）)\]【】「」《》“”]+|(?<![\w./:\\])/(?!/)[^\s<>\"'`|*?，。；：、（）)\]【】「」《》“”]+"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
        var output = text
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).reversed() {
            guard let range = Range(match.range, in: output) else { continue }
            let token = String(output[range]); if token.hasPrefix("[") { continue }
            let code = token.hasPrefix("`"), value = code ? String(token.dropFirst().dropLast()) : token
            let core = code ? value : value.replacingOccurrences(of: #"[.,;:!?]+$"#, with: "", options: .regularExpression)
            if let path = file(core), let url = path.url {
                let label = core.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "[", with: "\\[").replacingOccurrences(of: "]", with: "\\]")
                output.replaceSubrange(range, with: "[" + (code ? "`" + core + "`" : label) + "](" + url.absoluteString + ")" + (code ? "" : String(value.dropFirst(core.count))))
            } else if !code && (core.hasPrefix("https://") || core.hasPrefix("http://")) {
                output.replaceSubrange(range, with: "[" + core + "](" + core + ")" + String(value.dropFirst(core.count)))
            }
        }
        return output
    }
}
