import Foundation

public enum ReferenceText {
    public static func clip(_ value: String, to length: Int) -> String {
        let normalized = value.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
        guard length > 0 else { return "" }
        let source = normalized as NSString
        return source.length > length ? source.substring(to: length - 1) + "…" : normalized
    }
}
