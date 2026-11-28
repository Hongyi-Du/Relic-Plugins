import Foundation

public enum FilePresentation {
    public static func size(_ bytes: Int) -> String {
        if bytes < 1024 { return String(bytes) + " B" }
        if bytes < 1_048_576 { return String(format: "%.1f KB", locale: Locale(identifier: "en_US_POSIX"), Double(bytes) / 1024) }
        return String(format: "%.1f MB", locale: Locale(identifier: "en_US_POSIX"), Double(bytes) / 1_048_576)
    }
    public static func relative(_ path: String, root: String) -> String {
        let normalized = path.replacingOccurrences(of: "\\", with: "/")
        var base = root.replacingOccurrences(of: "\\", with: "/")
        if base.hasSuffix("/") { base.removeLast() }
        return normalized.lowercased().hasPrefix(base.lowercased() + "/") ? String(normalized.dropFirst(base.count + 1)) : path
    }
    public static func name(_ path: String) -> String { path.replacingOccurrences(of: "\\", with: "/").components(separatedBy: "/").last ?? path }
    public static func status(_ status: String) -> String { status == "??" ? "U" : String(status.prefix(1)) }
    public static func lines(_ text: String) -> [String] { text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n").components(separatedBy: "\n") }
}
