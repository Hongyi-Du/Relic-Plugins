import Foundation

public enum ReferenceText {
    /// Match the reference's macOS key-label transform before interpolation.
    /// User supplied message/path arguments must not be rewritten as shortcuts.
    public static func shortcutLabel(_ value: String) -> String {
        value.replacingOccurrences(of: "Ctrl+Y", with: "Cmd+Shift+Z")
            .replacingOccurrences(of: "Ctrl+", with: "Cmd+")
            .replacingOccurrences(of: "Alt+", with: "Option+")
    }
    /// HTML input maxlength counts UTF-16 code units. Preserve complete scalar
    /// values when enforcing the same limit in a native Unicode text field.
    public static func inputPrefix(_ value: String, utf16Limit: Int) -> String {
        var result = String.UnicodeScalarView(), count = 0
        for scalar in value.unicodeScalars {
            let units = scalar.value > 0xFFFF ? 2 : 1
            guard count + units <= max(0, utf16Limit) else { break }
            result.append(scalar); count += units
        }
        return String(result)
    }
    public static func clip(_ value: String, to length: Int) -> String {
        let normalized = value.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
        guard length > 0 else { return "" }
        let source = normalized as NSString
        return source.length > length ? source.substring(to: length - 1) + "…" : normalized
    }
}
